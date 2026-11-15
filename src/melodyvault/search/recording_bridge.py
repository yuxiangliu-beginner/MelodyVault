"""Only use a saved MusicBrainz recording when it explicitly links the selected item."""
import json
from melodyvault.database import connect
from melodyvault.catalog.normalize import name_key,title_key
from melodyvault.sources.matching import version_from_text

def linked_recording(path,song):
    url=song.get('source_url','')
    if not url:return None
    with connect(path) as db:
        rows=db.execute('''SELECT r.mbid,r.title,r.payload_json,d.payload_json AS detail,a.payload_json AS artist
          FROM catalog_recordings r JOIN catalog_recording_details d ON d.mbid=r.mbid
          JOIN catalog_artist_recordings ar ON ar.recording_mbid=r.mbid
          JOIN catalog_artists a ON a.mbid=ar.artist_mbid
          WHERE d.payload_json LIKE ?''',('%'+url+'%',)).fetchall()
    matches={}
    for row in rows:
        try:payload=json.loads(row['payload_json']);detail=json.loads(row['detail']);artist=json.loads(row['artist'])
        except (TypeError,ValueError):continue
        if not all(isinstance(v,dict) for v in (payload,detail,artist)):continue
        names=[artist.get('name','')]+[a.get('name','') for a in artist.get('aliases',[]) if isinstance(a,dict)]
        if name_key(song['artist']) not in {name_key(n) for n in names}:continue
        if title_key(song['title'])!=title_key(row['title']):continue
        if version_from_text(song['title'])!=version_from_text(row['title']):continue
        relations=detail.get('relations',[])
        urls=[x['url']['resource'] for x in relations if x.get('url',{}).get('resource')]
        if url not in urls:continue
        duration=(detail.get('length') or payload.get('length') or 0)/1000
        if duration and song.get('duration') and abs(duration-song['duration'])>2:continue
        matches[row['mbid']]={'recording_id':row['mbid'],'namespace':'musicbrainz','artist':artist,
            'recording_title':row['title'],'duration':duration or song.get('duration'),
            'isrcs':detail.get('isrcs',[]),'urls':urls,'recording_payload':{**payload,**detail}}
    return next(iter(matches.values())) if len(matches)==1 else None
