"""Conservative suggestions and replayable human decisions, without network or Qt."""
from dataclasses import replace
from difflib import SequenceMatcher
from uuid import uuid4,uuid5,NAMESPACE_URL

from melodyvault.catalog.models import CatalogError, CatalogResult, Song
from melodyvault.catalog.grouping import (RULE_VERSION,group_recordings,grouping_statistics,identity_work_ids,
    _artist_signature,version_kind,work_keys)
from melodyvault.catalog.normalize import title_key,normalized_isrc
from melodyvault.database.catalog import utc_now
from melodyvault.database.reviews import ReviewRepository


def recording_set(song):
    return {r.mbid for r in song.recordings}


def merge_conflict(artist,source_records,target):
    ids={wid for r in source_records+target.recordings for wid in identity_work_ids(r)} | set(target.work_ids)
    if len(ids)>1:return '存在不同的明确 Work ID；禁止把不同作品手动合并。'
    if any(version_kind(r)[0]=='medley' for r in source_records+target.recordings):
        return '串烧/多作品记录不能归入单一作品，可选择保持独立。'
    if any(not _artist_signature(r,artist.mbid) and 'recordings' not in r.origins for r in source_records+target.recordings):
        return '缺少与目标歌手的演唱关联，不能把不同演唱者混入该作品。'
    return None


def suggestions(artist,source,songs,works):
    source_keys={title_key(r.title) for r in source.recordings}|{title_key(source.title)}
    own_isrc={code for r in source.recordings for x in list(r.payload.get('isrcs',[]))+list(r.details.get('isrcs',[])) if (code:=normalized_isrc(x))}
    source_works={wid for r in source.recordings for wid in identity_work_ids(r)}
    result=[]
    for target in songs:
        if target.id==source.id:continue
        keys={title_key(target.title)}|{title_key(r.title) for r in target.recordings}
        for wid in target.work_ids:keys|=work_keys(works.get(wid,{}))
        overlap=bool((source_keys-{''}) & (keys-{''}))
        similarity=max((SequenceMatcher(None,a,b).ratio() for a in source_keys for b in keys if a and b),default=0)
        isrc=own_isrc & {code for r in target.recordings for x in list(r.payload.get('isrcs',[]))+list(r.details.get('isrcs',[])) if (code:=normalized_isrc(x))}
        shared=source_works & set(target.work_ids)
        if not overlap and not shared and not isrc and similarity<0.72:continue
        reasons=[]
        if shared:reasons.append('明确共同 Work：'+', '.join(sorted(shared)))
        if isrc:reasons.append('相同 ISRC：'+', '.join(sorted(isrc))+'；仅作为录音建档核对，不删除版本')
        if overlap:reasons.append('规范化标题/官方别名一致（单独属于弱证据）')
        elif similarity>=0.72:reasons.append('标题相似，仅生成建议，不自动归并')
        lengths=[abs(a.length_ms-b.length_ms) for a in source.recordings for b in target.recordings if a.length_ms is not None and b.length_ms is not None]
        if lengths and min(lengths)<=2000:reasons.append(f'最小时长差 {min(lengths)}ms（弱证据，不能证明同一作品）')
        conflict=merge_conflict(artist,source.recordings,target)
        confidence='冲突' if conflict else '高：明确作品关系' if shared else '中：ISRC线索，需人工核对' if isrc else '低：仅名称/时长线索'
        result.append({'target_song_id':target.id,'target_title':target.title,'confidence':confidence,
            'allowed':not conflict,'reasons':reasons,'warning':conflict or '只合并作品分组，现场/重录等不同 Recording 仍全部保留。',
            'priority':(bool(conflict),not bool(shared),not bool(isrc),not overlap,-similarity)})
    return sorted(result,key=lambda x:(x['priority'],x['target_song_id']))[:30]


def _copy_songs(songs):
    return [replace(s,recordings=list(s.recordings),evidence=list(s.evidence)) for s in songs]


def _ensure_primary(song):
    eligible=[r for r in song.recordings if r.official and len(identity_work_ids(r))<=1 and version_kind(r)[0]=='studio']
    if song.primary_recording_mbid in {r.mbid for r in eligible}:return
    if not eligible:
        song.primary_recording_mbid=None;song.primary_reason='没有足够正式录音室证据，不指定主版本';return
    chosen=sorted(eligible,key=lambda r:(not bool(identity_work_ids(r)),not bool(r.payload.get('isrcs') or r.details.get('isrcs')),r.mbid))[0]
    song.primary_recording_mbid=chosen.mbid;song.primary_reason='人工作品决定；主录音仍依据正式非现场发行/明确录音室标注'


def replay_reviews(artist,automatic,events):
    songs=_copy_songs(automatic)
    all_records={r.mbid:r for s in songs for r in s.recordings}
    undone={e.get('undo_of') for e in events if e['action']=='undo'}
    statuses={}
    applied=[]
    def extract(ids):
        for s in list(songs):
            if recording_set(s)&ids:
                s.recordings=[r for r in s.recordings if r.mbid not in ids]
                if not s.recordings:songs.remove(s)
                elif s.primary_recording_mbid not in recording_set(s):
                    s.primary_recording_mbid=None;s.primary_reason='原主版本已由人工决定移出'
        return [all_records[mbid] for mbid in sorted(ids)]
    def standalone(event,ids,confirmed):
        records=extract(ids)
        payload=event['payload']
        s=Song(str(uuid5(NAMESPACE_URL,f"MelodyVault.review:{artist.mbid}:{','.join(sorted(ids))}")),
            payload['source_title'],records,tuple(sorted({w for r in records for w in identity_work_ids(r)})),not confirmed,
            [{'rule':'manual_'+event['action'],'event_id':event['id'],'reason':event['reason']}],reviewed=True,review_action=event['action'])
        _ensure_primary(s)
        songs.append(s)
        return s
    for event in events:
        eid=event['id'];action=event['action']
        if action=='undo':statuses[eid]={'status':'undo','message':'撤销事件保留'};continue
        if eid in undone:statuses[eid]={'status':'undone','message':'已撤销，原始事件未删除'};continue
        payload=event['payload'];ids=set(payload['source_recordings']);targets=set(payload.get('target_recordings',[]))
        try:
            if not ids or not ids<=set(all_records):raise CatalogError('部分源记录不在该歌手目录，需重新审核')
            owners=[s for s in songs if recording_set(s)&targets]
            if action=='merge':
                if ids&targets or len(owners)!=1 or not targets<=recording_set(owners[0]):
                    raise CatalogError('目标分组已拆分/变化或依赖的前序决定被撤销，需重新审核')
                target=owners[0]
                source_records=[all_records[mbid] for mbid in ids]
                conflict=merge_conflict(artist,source_records,target)
                if conflict:raise CatalogError(conflict)
                records=extract(ids)
                target.recordings=list({r.mbid:r for r in target.recordings+records}.values())
                target.pending_confirmation=False;target.reviewed=True;target.review_action='merge'
                target.work_ids=tuple(sorted({w for r in target.recordings for w in identity_work_ids(r)}|set(target.work_ids)))
                target.evidence.append({'rule':'manual_merge','event_id':eid,'reason':event['reason'],'source_recordings':sorted(ids)})
                _ensure_primary(target)
            elif action=='independent':
                standalone(event,ids,True)
            elif action=='reject':
                overlap=any(recording_set(s)&ids and recording_set(s)&targets for s in songs)
                if overlap:standalone(event,ids,False)
                else:
                    for s in songs:
                        if recording_set(s)&ids:
                            s.reviewed=True;s.review_action='reject'
                            s.evidence.append({'rule':'manual_reject','event_id':eid,'reason':event['reason'],'rejected_target_recordings':sorted(targets)})
            else:raise CatalogError('未知审核动作')
            statuses[eid]={'status':'applied','message':'已应用（所有录音版本保留）'};applied.append(event)
        except CatalogError as error:
            statuses[eid]={'status':'stale','message':str(error)}
    assigned=[r.mbid for s in songs for r in s.recordings]
    if len(assigned)!=len(set(assigned)) or set(assigned)!=set(all_records):
        raise CatalogError('审核重建违反录音唯一分配约束；未提交')
    return songs,statuses,applied


class ReviewService:
    def __init__(self,repository,actor='local_user'):
        self.repository=repository;self.audit=ReviewRepository(repository);self.actor=actor

    def _build(self,artist,recordings=None,automatic=None,events=None):
        records=recordings if recordings is not None else self.repository.recordings(artist.mbid)
        works=self.repository.works()
        base=automatic if automatic is not None else group_recordings(artist,records,works)
        events=self.audit.events(artist.mbid) if events is None else events
        songs,statuses,applied=replay_reviews(artist,base,events)
        summary={**grouping_statistics(records,songs),'api_requests':0,'cache_hits':0,
            'artist_mbid':artist.mbid,'manually_reviewed_item_count':len({tuple(sorted(e['payload']['source_recordings'])) for e in applied}),
            'manually_reviewed_recording_count':len({r for e in applied for r in e['payload']['source_recordings']}),
            'stale_review_count':sum(v['status']=='stale' for v in statuses.values())}
        return {'result':CatalogResult(artist,songs,summary,records),'events':events,'statuses':statuses,'works':works,'automatic':base}

    def load(self,artist,recordings=None,automatic=None):
        snapshot=self._build(artist,recordings,automatic)
        events=snapshot['events'];head=events[-1]['id'] if events else None
        self.audit.commit(artist,snapshot['result'].songs,RULE_VERSION,head,summary=snapshot['result'].summary)
        return snapshot

    def decide(self,artist,action,source_song_id=None,target_song_id=None,reason='',undo_of=None):
        if action not in {'merge','reject','independent','undo'}:raise CatalogError('不支持的审核动作')
        if not reason.strip():raise CatalogError('请填写审核理由，保留可追溯审计')
        snapshot=self._build(artist);events=snapshot['events'];head=events[-1]['id'] if events else None
        event={'id':str(uuid4()),'artist_mbid':artist.mbid,'action':action,'payload':{},'reason':reason.strip(),
               'actor':self.actor,'created_at':utc_now(),'undo_of':undo_of}
        if action=='undo':
            target=next((e for e in events if e['id']==undo_of and e['action']!='undo'),None)
            if not target or any(e.get('undo_of')==undo_of for e in events):raise CatalogError('该决定不存在或已经撤销')
            event['payload']={'undone_action':target['action']}
        else:
            source=next((s for s in snapshot['result'].songs if s.id==source_song_id),None)
            target=next((s for s in snapshot['result'].songs if s.id==target_song_id),None)
            if source is None:raise CatalogError('源条目已变化，请刷新审核列表')
            if action in {'merge','reject'} and (target is None or target.id==source.id):raise CatalogError('请选择不同的建议归并对象')
            if action=='merge':
                conflict=merge_conflict(artist,source.recordings,target)
                if conflict:raise CatalogError(conflict)
            candidate=next((c for c in suggestions(artist,source,snapshot['result'].songs,snapshot['works']) if target and c['target_song_id']==target.id),None)
            event['payload']={'source_title':source.title,'source_recordings':sorted(recording_set(source)),
                'target_recordings':sorted(recording_set(target)) if target else [],'target_title':target.title if target else None,
                'candidate_evidence':candidate,'source_work_ids':list(source.work_ids),'target_work_ids':list(target.work_ids) if target else []}
        updated=self._build(artist,recordings=snapshot['result'].recordings,automatic=snapshot['automatic'],events=events+[event])
        if action!='undo' and updated['statuses'][event['id']]['status']!='applied':
            raise CatalogError(updated['statuses'][event['id']]['message'])
        self.audit.commit(artist,updated['result'].songs,RULE_VERSION,head,event,summary=updated['result'].summary)
        return updated
