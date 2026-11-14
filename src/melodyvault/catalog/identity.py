"""Explicit reverse Work, same-ISRC and recording-derivation evidence only."""
from collections import defaultdict
from melodyvault.catalog.models import Artist, Recording, credit_ids
from melodyvault.catalog.grouping import performance_relations, work_ids, work_keys, _artist_signature, version_kind, identity_work_ids
from melodyvault.catalog.normalize import title_key,normalized_isrc


def build_identity_links(artist: Artist, recordings: list[Recording], works: dict[str,dict], related: dict[str,dict], redirects=None) -> dict[str,list[dict]]:
    links=defaultdict(list)
    reverse=defaultdict(set)
    for work_id,work in works.items():
        for relation in work.get('relations',[]):
            if relation.get('type')=='performance' and relation.get('target-type')=='recording' and relation.get('recording',{}).get('id'):
                reverse[relation['recording']['id']].add(work_id)
    aux={}
    for mbid,payload in related.items():
        if not payload.get('title'):
            continue
        item=Recording.from_payload(payload); item.details=payload
        aux[mbid]=item
    for recording in recordings:
        aux[recording.mbid]=recording
    by_isrc=defaultdict(set)
    for mbid,item in aux.items():
        for isrc in set(item.payload.get('isrcs',[])) | set(item.details.get('isrcs',[])):
            code=normalized_isrc(isrc)
            if code:by_isrc[code].add(mbid)
    for recording in recordings:
        if not _artist_signature(recording,artist.mbid):
            continue
        for work_id in reverse[recording.mbid]:
            links[recording.mbid].append({'rule':'work_reverse_performance','verified':True,'work_id':work_id,
                'recording_mbid':recording.mbid,'source':f'https://musicbrainz.org/ws/2/work/{work_id}?inc=recording-rels'})
        possible=[]
        canonical=(redirects or {}).get(recording.mbid)
        if canonical and canonical in aux:
            if _artist_signature(aux[canonical],artist.mbid)==_artist_signature(recording,artist.mbid):
                links[recording.mbid].append({'rule':'recording_redirect','verified':True,'canonical_recording_mbid':canonical,
                    'source':f'https://musicbrainz.org/ws/2/recording/{recording.mbid}'})
            possible.append((aux[canonical],'recording_redirect',canonical))
        own_isrcs=set(recording.payload.get('isrcs',[])) | set(recording.details.get('isrcs',[]))
        for isrc in own_isrcs:
            code=normalized_isrc(isrc)
            if not code:continue
            for mbid in by_isrc[code] - {recording.mbid}:
                possible.append((aux[mbid],'same_isrc_work',isrc))
        for relation in (recording.details or recording.payload).get('relations',[]):
            if relation.get('target-type')=='recording' and relation.get('type') in {'music video','remaster','edit','remix','re-recording'}:
                other=aux.get(relation.get('recording',{}).get('id'))
                if other:
                    possible.append((other,'recording_derivation_work',relation['type']))
        # Links can be supplied in either direction, including video->audio.
        for other in aux.values():
            for relation in (other.details or other.payload).get('relations',[]):
                if relation.get('target-type')=='recording' and relation.get('type') in {'music video','remaster','edit','remix','re-recording'} and relation.get('recording',{}).get('id')==recording.mbid:
                    possible.append((other,'recording_derivation_work',relation['type']))
        for other,rule,key in possible:
            kinds=(version_kind(recording)[0],version_kind(other)[0])
            if rule=='same_isrc_work' and 'unknown' not in kinds and kinds[0]!=kinds[1]:
                continue  # A reused ISRC with conflicting version metadata is not a safe identity bridge.
            other_works=work_ids(other) | frozenset(reverse[other.mbid])
            if len(other_works)!=1 or version_kind(other)[0]=='medley':
                continue
            if _artist_signature(other,artist.mbid)!=_artist_signature(recording,artist.mbid):
                continue
            work_id=next(iter(other_works))
            candidate_keys={title_key(other.title)} | work_keys(works.get(work_id,{}))
            if rule!='recording_redirect' and (not title_key(recording.title) or title_key(recording.title) not in candidate_keys):
                continue
            # Different explicit Work evidence is retained as a conflict, not discarded.
            links[recording.mbid].append({'rule':rule,'verified':True,'work_id':work_id,'related_recording_mbid':other.mbid,
                'key':key,'source':f'https://musicbrainz.org/ws/2/recording/{other.mbid}?inc=work-rels+isrcs+recording-rels',
                'conflict':bool(work_ids(recording) and work_id not in work_ids(recording))})
    return dict(links)
