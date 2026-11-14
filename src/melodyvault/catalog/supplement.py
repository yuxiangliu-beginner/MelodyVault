"""Targeted pending-item enrichment, resumable and independent from manual decisions."""
from melodyvault.catalog.models import CatalogError, Progress
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.grouping import group_recordings
from melodyvault.catalog.identity import build_identity_links
from melodyvault.database import connect
from melodyvault.catalog.normalize import normalized_isrc
import time

PROFILE='pending-recording-releases-v1'
INC='artist-credits+isrcs+work-rels+recording-rels+releases+release-groups'


def supplement_pending(repository,client,artist,progress):
    def rebuild():
        records=repository.recordings(artist.mbid)
        links=build_identity_links(artist,records,repository.works(),repository.related(),repository.recording_redirects())
        repository.replace_identity_links(artist,links)
        return repository.recordings(artist.mbid)
    records=rebuild()
    before=group_recordings(artist,records,repository.works())
    pending_ids=sorted({r.mbid for song in before if song.pending_confirmation for r in song.recordings})
    with connect(repository.path) as db:
        releases={row[0] for row in db.execute('SELECT mbid FROM catalog_releases')}
        fresh={(row[0],row[1]) for row in db.execute('SELECT recording_mbid,profile FROM catalog_evidence_fetches WHERE fetched_at>?',(time.time()-7*86400,))}
    related=repository.related()
    stats={'targeted_pending_count':len(pending_ids),'targeted_fetched':0,'targeted_reused':0,'new_release_contexts':0,'lookup_not_found':0}
    def lookup(mbid,with_releases=True):
        try:
            data=client.get_json(f'recording/{mbid}',{'inc':INC if with_releases else 'artist-credits+isrcs+work-rels+recording-rels'})
        except CatalogError as error:
            if 'HTTP 404' not in str(error):raise
            stats['lookup_not_found']+=1
            client.notice(str(error)+'；原始录音保留，仍待确认')
            return None,str(error)
        if data['id']!=mbid and repository.recording_redirects().get(mbid)!=data['id']:
            raise CatalogError(f'补证 Recording MBID 不一致：{mbid}')
        repository.save_details([data]);repository.save_related([data],'official pending lookup')
        related[mbid]=data
        return data,None
    for index,mbid in enumerate(pending_ids,1):
        check_cancel(client.cancel)
        progress(Progress('pending_evidence',index-1,len(pending_ids),f'待确认录音定向补证 {index}/{len(pending_ids)}；成功项可恢复',artist))
        if not client.force_refresh and (mbid,PROFILE) in fresh:
            stats['targeted_reused']+=1;continue
        data,error=lookup(mbid)
        if data:
            stats['targeted_fetched']+=1
            for release in data.get('releases',[]):
                release_id=release['id']
                if release_id in releases:continue
                full=client.get_json(f'release/{release_id}',{'inc':'recordings+artist-credits+release-groups+isrcs'})
                if (full.get('status') or '').casefold()=='official':
                    repository.save_releases(artist,[full]);stats['new_release_contexts']+=1
                releases.add(release_id)
            for relation in data.get('relations',[]):
                other=relation.get('recording',{}).get('id')
                if relation.get('type') in {'music video','remaster','edit','remix','re-recording'} and other and other not in related:
                    lookup(other,False)
        repository.mark_evidence_fetch(mbid,PROFILE,error)
    # ISRC lookup can expose an auxiliary/duplicate entity outside the artist
    # browse result; these entities remain evidence-only, never extra UI versions.
    owners={}
    for recording in repository.recordings(artist.mbid):
        if recording.mbid not in pending_ids:continue
        for raw in set(recording.payload.get('isrcs',[]))|set(recording.details.get('isrcs',[])):
            code=normalized_isrc(raw)
            if code:owners.setdefault(code,recording.mbid)
    stats.update({'isrc_lookup_count':0,'isrc_lookup_reused':0,'isrc_not_found':0})
    for index,(code,owner) in enumerate(sorted(owners.items()),1):
        check_cancel(client.cancel)
        profile='isrc-related-v1:'+code
        progress(Progress('isrc_evidence',index-1,len(owners),f'ISRC重复建档/作品补证 {index}/{len(owners)}',artist))
        if not client.force_refresh and (owner,profile) in fresh:
            stats['isrc_lookup_reused']+=1;continue
        error=None
        try:
            response=client.get_json(f'isrc/{code}',{'inc':'artist-credits+isrcs+work-rels+recording-rels'})
            items=response['recordings']
            new_items=[item for item in items if item['id'] not in related]
            repository.save_related(new_items,'official ISRC lookup')
            related.update({item['id']:item for item in new_items})
            for item in new_items:
                if 'relations' not in item:lookup(item['id'],False)
            stats['isrc_lookup_count']+=1
        except CatalogError as failure:
            if 'HTTP 404' not in str(failure):raise
            client.notice(str(failure)+'；未找到ISRC关联，未自动归并')
            error=str(failure);stats['isrc_not_found']+=1
        repository.mark_evidence_fetch(owner,profile,error)
    works=repository.works()
    for data in related.values():
        for relation in data.get('relations',[]):
            work=relation.get('work')
            if relation.get('type')=='performance' and work and work['id'] not in works:
                full=client.get_json(f'work/{work["id"]}',{'inc':'aliases+artist-rels+recording-rels'})
                repository.save_works([full]);works[full['id']]=full
    rebuild()
    stats['canonical_recording_redirect_count']=len(set(repository.recording_redirects()) & {r.mbid for r in records})
    progress(Progress('pending_evidence',len(pending_ids),len(pending_ids),'待确认证据补充完成；仅强证据进入自动归并',artist))
    return stats
