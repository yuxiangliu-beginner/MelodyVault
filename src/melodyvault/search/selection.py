"""User target selection links IDs without replaying or replacing human grouping."""
import json
from dataclasses import replace
from uuid import uuid4,uuid5,NAMESPACE_URL
from melodyvault.catalog.models import Artist,Recording,CatalogError,CatalogResult
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.grouping import group_recordings,grouping_statistics,version_kind
from melodyvault.catalog.normalize import name_key
from melodyvault.database import connect
from melodyvault.database.catalog import encode,utc_now
from melodyvault.search.models import song_key


class SongSelectionService:
    def __init__(self,repository,client):self.repository=repository;self.client=client
    def confirm(self,candidate,request,title_query):
        check_cancel(self.client.cancel);artist=candidate.artist
        with connect(self.repository.path) as db:
            row=db.execute('SELECT payload_json FROM catalog_artists WHERE mbid=?',(artist.mbid,)).fetchone()
        if row:artist=Artist.from_payload(json.loads(row[0]))
        existing=self.repository.songs(artist.mbid) if row else []
        owner=next((s for s in existing if any(r.mbid==candidate.recording_mbid for r in s.recordings)),None)
        if owner is None:
            fresh=self.client.get_json('recording/'+candidate.recording_mbid,{'inc':'artist-credits+isrcs+work-rels+recording-rels'})
            if fresh['id']!=candidate.recording_mbid and self.repository.recording_redirects().get(candidate.recording_mbid)!=fresh['id']:
                raise CatalogError('Recording身份已变化，未保存选择')
            credits=[c['artist']['id'] for c in fresh.get('artist-credit',[]) if isinstance(c,dict) and c.get('artist')]
            if artist.mbid not in credits:raise CatalogError('官方Recording署名不属于所选歌手；请修正候选')
            canonical_owner=next((s for s in existing if any(r.mbid==fresh['id'] for r in s.recordings)),None)
            if canonical_owner is not None:
                revised=replace(candidate,recording_mbid=fresh['id'],payload={**candidate.payload,'original_selected_recording_mbid':candidate.recording_mbid})
                return self.confirm(revised,request,title_query)
            record=Recording.from_payload(fresh);record.details=fresh
            if candidate.version!='unknown' and version_kind(record)[0] not in {'unknown',candidate.version}:
                raise CatalogError('官方版本信息与候选不同，请更新候选后重新确认')
            if not row:
                verified=self.client.get_json('artist/'+artist.mbid,{'inc':'aliases'})
                if verified['id']!=artist.mbid:raise CatalogError('歌手MBID校验失败')
                artist=Artist.from_payload(verified)
            # A shared Recording may already belong to another artist/manual group.
            # Reuse its immutable observation and existing details instead of replacing them.
            with connect(self.repository.path) as db:
                saved=db.execute('SELECT r.payload_json,d.payload_json FROM catalog_recordings r LEFT JOIN catalog_recording_details d ON d.mbid=r.mbid WHERE r.mbid=?',(record.mbid,)).fetchone()
            if saved:
                record=Recording.from_payload(json.loads(saved[0]));record.details=json.loads(saved[1]) if saved[1] else {}
            works=self.repository.works()
            for rel in fresh.get('relations',[]):
                if rel.get('type')=='performance' and rel.get('work'):works.setdefault(rel['work']['id'],rel['work'])
            derived=group_recordings(artist,[record],works)[0]
            target=next((s for s in existing if s.id==derived.id and not s.reviewed),None)
            if any(s.id==derived.id and s.reviewed for s in existing):
                derived.id=str(uuid5(NAMESPACE_URL,'MelodyVault.search-selection:'+artist.mbid+':'+record.mbid))
                derived.pending_confirmation=True
                derived.evidence.append({'rule':'selection_does_not_modify_reviewed_song'})
            check_cancel(self.client.cancel)
            with self.repository.transaction() as db:
                db.execute('INSERT OR IGNORE INTO catalog_artists VALUES (?,?,?,?)',(artist.mbid,artist.name,encode(artist.payload),utc_now()))
                db.execute('INSERT OR IGNORE INTO catalog_queries VALUES (?,?)',(name_key(artist.name),artist.mbid))
                raw=encode(fresh)
                from hashlib import sha256
                db.execute('INSERT OR IGNORE INTO catalog_recordings VALUES (?,?,?,?,?)',(record.mbid,record.original_title,name_key(record.title),raw,utc_now()))
                db.execute('INSERT OR IGNORE INTO catalog_recording_snapshots VALUES (?,?,?,?)',(record.mbid,sha256(raw.encode()).hexdigest(),raw,utc_now()))
                db.execute('INSERT OR IGNORE INTO catalog_recording_details VALUES (?,?,?)',(record.mbid,raw,utc_now()))
                db.execute('INSERT OR IGNORE INTO catalog_artist_recordings VALUES (?,?,0,?)',(artist.mbid,record.mbid,encode(['user_song_selection'])))
                for wid in derived.work_ids:
                    w=works.get(wid,{})
                    db.execute('INSERT OR IGNORE INTO catalog_works VALUES (?,?,?,?)',(wid,w.get('title',record.title),encode(w),utc_now()))
                if target:
                    db.execute('INSERT OR IGNORE INTO catalog_song_recordings VALUES (?,?)',(target.id,record.mbid));owner_id=target.id
                else:
                    db.execute('INSERT INTO catalog_songs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(derived.id,artist.mbid,derived.title,int(derived.pending_confirmation),encode(derived.work_ids),
                        derived.primary_recording_mbid,derived.primary_reason,encode(derived.evidence),'search-selection-v1',utc_now(),0,''))
                    db.execute('INSERT INTO catalog_song_recordings VALUES (?,?)',(derived.id,record.mbid));owner_id=derived.id
            owner=next(s for s in self.repository.songs(artist.mbid) if s.id==owner_id)
        record=next(r for r in owner.recordings if r.mbid==candidate.recording_mbid or self.repository.recording_redirects().get(candidate.recording_mbid)==r.mbid)
        check_cancel(self.client.cancel)
        with self.repository.transaction() as db:
            db.execute('INSERT INTO unified_confirmations VALUES (?,?,?,?,?,?,?)',(str(uuid4()),encode(request.__dict__),artist.mbid,record.mbid,owner.id,encode(candidate.to_dict()),utc_now()))
            inserted=db.execute('INSERT OR IGNORE INTO unified_user_aliases VALUES (?,?,?)',(song_key(title_query),artist.mbid,record.mbid))
            if inserted.rowcount:db.execute("UPDATE app_metadata SET value=CAST(value AS INTEGER)+1 WHERE key='unified_revision'")
        selected=replace(owner,recordings=[record],evidence=[*owner.evidence,{'rule':'user_selected_search_alias','title':title_query,'not_identity_proof':True}],primary_recording_mbid=owner.primary_recording_mbid if owner.primary_recording_mbid==record.mbid else None)
        summary={**grouping_statistics([record],[selected]),'api_requests':self.client.requests,'cache_hits':self.client.cache_hits,
            'selection_scope':'recording','selected_recording_mbid':record.mbid,'manually_reviewed_item_count':0}
        return CatalogResult(artist,[selected],summary,[record])
