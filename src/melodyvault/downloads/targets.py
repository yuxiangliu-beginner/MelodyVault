"""Immutable selected-recording snapshots; no reinterpretation of artist identity."""
from melodyvault.catalog.models import Artist,Recording,Song
from melodyvault.catalog.grouping import version_kind


def from_song(artist,song,explicit=False):
    recording=next((r for r in song.recordings if r.mbid==song.primary_recording_mbid),None)
    if explicit and len(song.recordings)==1:recording=song.recordings[0]
    if recording is None:recording=song.recordings[0] if song.recordings else None
    if recording is None:raise ValueError('歌曲没有录音数据')
    detail={**recording.payload,**recording.details}
    urls=[r['url']['resource'] for r in detail.get('relations',[]) if r.get('url',{}).get('resource')]
    return {'song_id':song.id,'recording_id':recording.mbid,'namespace':'musicbrainz','artist':artist.payload or {'id':artist.mbid,'name':artist.name},
        'title':song.title,'recording_title':recording.original_title,'version':version_kind(recording)[0],
        'duration':(recording.length_ms/1000 if recording.length_ms else None),'isrcs':detail.get('isrcs',[]),'urls':urls,
        'confirmed':bool(explicit or not song.pending_confirmation and song.primary_recording_mbid),
        'recording_payload':detail,'work_ids':list(song.work_ids),
        'search_aliases':[e['title'] for e in song.evidence if e.get('rule')=='user_selected_search_alias' and e.get('title')]}


def search_values(target):
    artist=Artist.from_payload(target['artist'])
    record=Recording.from_payload(target['recording_payload']);record.details=target['recording_payload']
    aliases=[{'rule':'user_selected_search_alias','title':title,'not_identity_proof':True} for title in target.get('search_aliases',[])]
    song=Song(target['song_id'],target['title'],[record],tuple(target.get('work_ids',[])),not target['confirmed'],aliases,record.mbid)
    return artist,song
