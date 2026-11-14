"""Derived local index and typed query caches. Raw catalog rows are never replaced."""
import json,time
from dataclasses import replace
from melodyvault.database import connect
from melodyvault.database.catalog import encode
from melodyvault.catalog.models import Artist,Recording,CatalogError
from melodyvault.catalog.grouping import version_kind
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.search.models import identity_key,song_key,pinyin_key,SearchResult


class SearchRepository:
    def __init__(self,catalog):self.catalog=catalog;self.path=catalog.path
    def ensure_index(self,cancel):
        for _ in range(4):
            check_cancel(cancel)
            with connect(self.path) as db:
                db.execute('BEGIN')
                revision=int(db.execute("SELECT value FROM app_metadata WHERE key='unified_revision'").fetchone()[0])
                indexed=db.execute('SELECT revision FROM unified_index_meta WHERE id=1').fetchone()
                format_row=db.execute("SELECT value FROM app_metadata WHERE key='unified_index_format'").fetchone()
                if indexed and indexed[0]==revision and format_row and format_row[0]=='2':return
                artists={row[0]:json.loads(row[1]) for row in db.execute('SELECT mbid,payload_json FROM catalog_artists')}
                works={row[0]:json.loads(row[1]) for row in db.execute('SELECT mbid,payload_json FROM catalog_works')}
                rows=db.execute('SELECT s.song_id,s.artist_mbid,s.title,s.pending,s.reviewed,s.work_ids_json,s.primary_recording_mbid,s.primary_reason,r.mbid,r.payload_json,d.payload_json AS details FROM catalog_songs s JOIN catalog_song_recordings sr ON sr.song_id=s.song_id JOIN catalog_recordings r ON r.mbid=sr.recording_mbid LEFT JOIN catalog_recording_details d ON d.mbid=r.mbid').fetchall()
            artist_rows=[];record_rows=[];keys=set()
            for mbid,payload in artists.items():
                artist=Artist.from_payload(payload)
                artist_rows.append((mbid,encode(payload),encode(sorted({identity_key(n) for n in (artist.name,*artist.aliases)}))))
            for row in rows:
                check_cancel(cancel)
                raw=json.loads(row['payload_json']);details=json.loads(row['details']) if row['details'] else {}
                record=Recording.from_payload(raw);record.details=details
                wid=json.loads(row['work_ids_json']);kind=version_kind(record)[0]
                if kind=='unknown' and row['primary_recording_mbid']==record.mbid and any(x in row['primary_reason'] for x in ('Official','正式','录音室')):kind='studio'
                titles=[row['title'],raw['title'],details.get('title','')]
                for item in (raw,details):titles.extend(a.get('name','') for a in item.get('aliases',[]))
                for work_id in wid:
                    work=works.get(work_id,{})
                    titles += [work.get('title',''),*[a.get('name','') for a in work.get('aliases',[])]]
                data={'song_id':row['song_id'],'recording_mbid':record.mbid,'title':details.get('title') or raw['title'],
                    'work_ids':wid,'version':kind,'length_ms':details.get('length',raw.get('length')),
                    'pending':bool(row['pending']),'reviewed':bool(row['reviewed']),
                    'performers':[c['artist'] for c in record.credits if isinstance(c,dict) and c.get('artist')]}
                record_rows.append((row['artist_mbid'],record.mbid,encode(data)))
                keys.update((song_key(t),row['artist_mbid'],record.mbid) for t in titles if t)
                keys.update((pinyin_key(t),row['artist_mbid'],record.mbid) for t in titles if t and pinyin_key(t))
            with self.catalog.transaction() as db:
                current=int(db.execute("SELECT value FROM app_metadata WHERE key='unified_revision'").fetchone()[0])
                if current!=revision:continue
                check_cancel(cancel)
                for table in ('unified_artist_index','unified_recording_index','unified_title_keys'):db.execute('DELETE FROM '+table)
                db.executemany('INSERT INTO unified_artist_index VALUES (?,?,?)',artist_rows)
                db.executemany('INSERT INTO unified_recording_index VALUES (?,?,?)',record_rows)
                db.executemany('INSERT INTO unified_title_keys VALUES (?,?,?)',sorted(keys))
                db.execute('INSERT INTO unified_index_meta VALUES (1,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision',(revision,))
                db.execute("INSERT INTO app_metadata VALUES ('unified_index_format','2') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
                return
        raise CatalogError('目录正在更新，本地索引未稳定；请稍后重试')
    def artists(self):
        with connect(self.path) as db:rows=db.execute('SELECT payload_json FROM unified_artist_index').fetchall()
        return [Artist.from_payload(json.loads(r[0])) for r in rows]
    def revision(self):
        with connect(self.path) as db:return int(db.execute("SELECT value FROM app_metadata WHERE key='unified_revision'").fetchone()[0])
    def title_rows(self,title):
        key=song_key(title)
        with connect(self.path) as db:
            rows=db.execute('SELECT r.artist_mbid,r.payload_json,0 AS kind FROM unified_recording_index r JOIN unified_title_keys k ON k.artist_mbid=r.artist_mbid AND k.recording_mbid=r.recording_mbid WHERE k.title_key=? UNION ALL SELECT r.artist_mbid,r.payload_json,1 AS kind FROM unified_recording_index r JOIN unified_user_aliases k ON k.artist_mbid=r.artist_mbid AND k.recording_mbid=r.recording_mbid WHERE k.title_key=? UNION ALL SELECT r.artist_mbid,r.payload_json,2 AS kind FROM unified_recording_index r JOIN unified_title_keys k ON k.artist_mbid=r.artist_mbid AND k.recording_mbid=r.recording_mbid WHERE k.title_key=? ORDER BY kind',(key,key,'pinyin:'+key if key.isascii() else '')).fetchall()
        return [(row[0],json.loads(row[1]),row[2]) for row in rows]
    def recording_rows(self,mbids):
        if not mbids:return []
        with connect(self.path) as db:
            rows=db.execute('SELECT artist_mbid,payload_json FROM unified_recording_index WHERE recording_mbid IN ('+','.join('?' for _ in mbids)+')',list(mbids)).fetchall()
        return [(r[0],json.loads(r[1])) for r in rows]
    def cached(self,request):
        with connect(self.path) as db:row=db.execute('SELECT payload_json,checked_at FROM unified_search_cache WHERE cache_key=?',(request.cache_key(),)).fetchone()
        if not row:return None
        result=SearchResult.from_dict(json.loads(row[0]));ttl=7*86400 if result.artists or result.songs else 6*3600
        if time.time()-row[1]>ttl or result.catalog_revision!=self.revision():return None
        if request.artist_ids and tuple(result.request.artist_ids)!=tuple(request.artist_ids):return None
        result.request=replace(request,artist_ids=result.request.artist_ids);result.cache_hit=True;result.scope='search_cache';result.api_requests=0;result.retries=0
        return result
    def save_cache(self,result,lookup_request=None):
        if result.errors:return
        with connect(self.path) as db:
            db.execute('INSERT INTO unified_search_cache VALUES (?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json,checked_at=excluded.checked_at',
                ((lookup_request or result.request).cache_key(),result.request.mode,encode(sorted(set(result.request.artist_ids)|{a.mbid for a in result.artists}|{s.artist.mbid for s in result.songs})),encode(result.to_dict()),time.time()))
