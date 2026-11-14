"""Conservative, explainable Song identity. A title match alone NEVER creates an edge."""
from collections import defaultdict
from itertools import combinations
import re
from uuid import NAMESPACE_URL, uuid5

from melodyvault.catalog.models import Artist, Recording, Song, credit_ids
from melodyvault.catalog.normalize import base_title, display_name, title_key, normalized_isrc

RULE_VERSION = 'song-evidence-v2'


def performance_relations(recording: Recording) -> list[dict]:
    data = recording.details or recording.payload
    return [relation for relation in data.get('relations', [])
            if relation.get('target-type') == 'work' and relation.get('type') == 'performance'
            and relation.get('work', {}).get('id')]


def work_ids(recording: Recording) -> frozenset[str]:
    return frozenset(relation['work']['id'] for relation in performance_relations(recording))


def identity_work_ids(recording: Recording) -> frozenset[str]:
    return work_ids(recording) | frozenset(link['work_id'] for link in recording.identity_links if link.get('verified') and link.get('work_id'))


def work_keys(work: dict) -> set[str]:
    return {title_key(name) for name in [work.get('title',''), *[a.get('name','') for a in work.get('aliases',[])]] if name}


def version_kind(recording: Recording) -> tuple[str, list[str]]:
    """Studio requires positive release/annotation evidence, not absence of 'live'."""
    attributes = {a.casefold() for relation in performance_relations(recording) for a in relation.get('attributes', [])}
    annotation = display_name((recording.details or recording.payload).get('disambiguation',recording.version) or '').casefold()
    current_title=display_name(recording.details.get('title',recording.original_title))
    bracketed = ' '.join(re.findall(r'[（(\[]([^()（）\[\]]*)[）)\]]', current_title))
    suffix = re.search(r'\s+[-–—]\s+(.+)$', current_title)
    if suffix:
        bracketed += ' ' + suffix[1]
    text = annotation + ' ' + bracketed.casefold()
    secondary = {str(t).casefold() for context in recording.contexts for t in context.get('secondary_types', [])}
    for kind, pattern in (
        ('medley', r'\bmedley\b|串烧|串燒'), ('partial', r'\bpartial\b|片段'),
        ('live', r'\blive\b|现场|演唱会'), ('remix', r'\bremix\b|\bmix\b|混音'),
        ('demo', r'\bdemo\b|小样'), ('karaoke', r'\bkaraoke\b|卡拉|伴奏'),
        ('rerecording', r'\bre-record(?:ing|ed)\b|重新录制|重录'),
        ('instrumental', r'\binstrumental\b|演奏|纯音乐'), ('edit', r'\bedit\b|剪辑'),
    ):
        if kind in attributes or kind in secondary or re.search(pattern, text, re.I):
            return kind, [f'关系属性/版本标注/发行组类型：{kind}']
    if re.search(r'\bstudio\b|录音室', text):
        return 'studio', ['明确 studio/录音室版本标注']
    contexts = [context for context in recording.contexts
                if (context.get('status') or '').casefold() == 'official'
                and context.get('primary_type') in {'Album','Single','EP'}
                and not {str(t).casefold() for t in context.get('secondary_types', [])}
                    & {'live','remix','demo','compilation','dj-mix'}]
    if recording.official and contexts:
        return 'studio', ['Official Album/Single/EP 非现场发行上下文（录音室推定）']
    return 'unknown', ['无足够录音室/现场/混音版本证据']


def _artist_signature(recording: Recording, target: str) -> frozenset[str]:
    ids = credit_ids(recording.credits)
    if target in ids:
        return frozenset(ids)
    signatures = [credit_ids(c.get('credits',[])) for c in recording.contexts]
    return frozenset(next((ids for ids in signatures if target in ids), set()))


def _compound(recording: Recording) -> bool:
    return len(identity_work_ids(recording)) > 1 or version_kind(recording)[0] == 'medley'


def group_recordings(artist: Artist, recordings: list[Recording], works: dict[str, dict]) -> list[Song]:
    by_id = {}
    for recording in recordings:
        if recording.mbid in by_id:
            by_id[recording.mbid].merge(recording)
        else:
            by_id[recording.mbid] = recording
    records = sorted(by_id.values(), key=lambda r: r.mbid)
    direct = {r.mbid: identity_work_ids(r) for r in records}
    associated = {r.mbid: bool(_artist_signature(r,artist.mbid)) or 'recordings' in r.origins for r in records}
    keys = {}
    for recording in records:
        keys[recording.mbid] = {title_key(recording.original_title)}
        for work_id in direct[recording.mbid]:
            work = works.get(work_id) or next((rel['work'] for rel in performance_relations(recording) if rel['work']['id'] == work_id), {})
            keys[recording.mbid].update(work_keys(work))
    parents = {r.mbid:r.mbid for r in records}
    def root(mbid):
        while parents[mbid] != mbid:
            parents[mbid] = parents[parents[mbid]]
            mbid = parents[mbid]
        return mbid
    def union(left, right):
        left, right = root(left), root(right)
        if left != right:
            parents[max(left,right)] = min(left,right)

    # Strong fallback edges are considered together, so an unknown record cannot
    # transitively bridge two conflicting Work IDs depending on traversal order.
    buckets = defaultdict(set)
    for recording in records:
        if _compound(recording) or not associated[recording.mbid]:
            continue
        signature = _artist_signature(recording, artist.mbid)
        if not signature:
            continue
        buckets[('canonical_recording',recording.mbid,tuple(sorted(signature)))].add(recording.mbid)
        for link in recording.identity_links:
            if link.get('rule')=='recording_redirect' and link.get('verified') and link.get('canonical_recording_mbid'):
                buckets[('canonical_recording',link['canonical_recording_mbid'],tuple(sorted(signature)))].add(recording.mbid)
        for isrc in set(recording.payload.get('isrcs',[])) | set(recording.details.get('isrcs',[])):
            code=normalized_isrc(isrc)
            if code:buckets[('isrc', code, tuple(sorted(signature)))].add(recording.mbid)
        for context in recording.contexts:
            if context.get('release_group_mbid') and context.get('medium_position') is not None and context.get('position') is not None:
                buckets[('release_slot', context['release_group_mbid'], context['medium_position'], context['position'], tuple(sorted(signature)))].add(recording.mbid)
    edges = []
    for bucket, ids in sorted(buckets.items(), key=lambda pair:str(pair[0])):
        for left, right in combinations(sorted(ids), 2):
            kinds=(version_kind(by_id[left])[0],version_kind(by_id[right])[0])
            if bucket[0]=='isrc' and 'unknown' not in kinds and kinds[0]!=kinds[1]:
                continue
            if (keys[left] & keys[right]) or bucket[0]=='canonical_recording':
                edges.append({'rule':bucket[0], 'left':left,'right':right,'key':list(bucket[1:])})
                union(left,right)
    # A reissue/box-set may use another release-group or renumber its discs.
    # Require the ENTIRE official medium sequence, performer signatures and
    # durations to agree; a single same-titled track is never enough.
    media = defaultdict(dict)
    for recording in records:
        for context in recording.contexts:
            if (context.get('status') or '').casefold() == 'official':
                media[(context['release_mbid'],context.get('medium_position'))][context.get('position')] = (recording,context)
    fingerprints = defaultdict(list)
    for medium_id, tracks in media.items():
        if None in tracks or len(tracks) < 3:
            continue
        ordered = [tracks[position] for position in sorted(tracks)]
        if any(context.get('medium_track_count') != len(ordered) for _,context in ordered):
            continue
        signatures = [_artist_signature(recording,artist.mbid) for recording,_ in ordered]
        if not all(signatures):
            continue
        fingerprint = tuple((title_key(context.get('track_title') or recording.original_title),tuple(sorted(signature)))
                            for (recording,context),signature in zip(ordered,signatures))
        fingerprints[fingerprint].append((medium_id,ordered))
    for matching_media in fingerprints.values():
        for (left_id,left_tracks),(right_id,right_tracks) in combinations(matching_media,2):
            compared = [(left.length_ms,right.length_ms) for (left,_),(right,_) in zip(left_tracks,right_tracks)
                        if left.length_ms is not None and right.length_ms is not None]
            if len(compared) < 0.8*len(left_tracks) or any(abs(a-b)>2000 for a,b in compared):
                continue
            for (left,_),(right,_) in zip(left_tracks,right_tracks):
                if left.mbid != right.mbid and not _compound(left) and not _compound(right):
                    edge = {'rule':'official_medium_reissue','left':left.mbid,'right':right.mbid,
                            'media':[list(left_id),list(right_id)],'track_count':len(left_tracks),'duration_tolerance_ms':2000}
                    edges.append(edge)
                    union(left.mbid,right.mbid)
    components = defaultdict(list)
    for recording in records:
        components[root(recording.mbid)].append(recording)
    assigned = defaultdict(list)
    evidence = defaultdict(list)
    pending = {}
    for members in components.values():
        anchors = {wid for r in members for wid in direct[r.mbid]}
        usable = [r for r in members if not _compound(r)]
        for recording in members:
            ids = direct[recording.mbid]
            if not associated[recording.mbid]:
                key = ('recording',recording.mbid)
                pending[key] = True
                reason = {'rule':'independent_pending','recording':recording.mbid,'reason':'缺少与目标歌手的演唱/曲目署名关联'}
            elif _compound(recording):
                key = ('recording', recording.mbid)
                pending[key] = True
                reason = {'rule':'independent_pending','recording':recording.mbid,'reason':'多作品串烧/片段关系，不以其中一个 Work 吞并其他作品'}
            elif len(ids) == 1:
                key = ('work', next(iter(ids)))
                pending.setdefault(key, False)
                reason = {'rule':'direct_work' if work_ids(recording) else 'verified_identity_link','recording':recording.mbid,'work_id':key[1]}
            elif len(anchors) == 1 and len(usable) == len(members):
                key = ('work', next(iter(anchors)))
                pending.setdefault(key, False)
                reason = {'rule':'anchored_isrc_or_release_slot','recording':recording.mbid,'work_id':key[1]}
            elif not anchors and len(members) > 1:
                key = ('context', min(r.mbid for r in members))
                pending[key] = True
                reason = {'rule':'context_cluster_pending','recording':recording.mbid,'reason':'有相同ISRC/发行曲目位置证据，但尚无可靠 Work 身份'}
            else:
                key = ('recording', recording.mbid)
                pending[key] = True
                reason = {'rule':'independent_pending','recording':recording.mbid,
                          'reason':'缺少作品关联证据' if not anchors else '候选关联同时涉及不同 Work，禁止传递合并',
                          'candidate_work_ids':sorted(anchors)}
            assigned[key].append(recording)
            evidence[key].append(reason)
            evidence[key].extend(recording.identity_links)
            for edge in edges:
                if recording.mbid in (edge['left'], edge['right']):
                    evidence[key].append(edge)
    # Title/alias matches are review hints only. They never union components.
    catalog_work_keys = {wid:work_keys(work) for wid,work in works.items()}
    result = []
    for key, members in sorted(assigned.items()):
        ids = (key[1],) if key[0] == 'work' else tuple(sorted({wid for r in members for wid in direct[r.mbid]}))
        title = display_name(works.get(ids[0],{}).get('title','')) if len(ids) == 1 else ''
        title = title or base_title(sorted(members, key=lambda r:(not r.official,r.mbid))[0].original_title)
        if pending[key]:
            candidates = sorted({wid for r in members for wid,wkeys in catalog_work_keys.items() if keys[r.mbid] & wkeys})
            if candidates:
                evidence[key].append({'rule':'title_alias_candidates_only','work_ids':candidates,'auto_merge':False})
        song = Song(str(uuid5(NAMESPACE_URL, f'MelodyVault:{artist.mbid}:{key[0]}:{key[1]}')),
                    title, sorted(members,key=lambda r:r.mbid),ids,pending[key],evidence[key])
        eligible = [r for r in members if r.official and not _compound(r) and version_kind(r)[0] == 'studio']
        if eligible:
            def priority(r):
                dates = [c['date'] for c in r.contexts if c.get('date')]
                return (not bool(work_ids(r)), not bool(r.payload.get('isrcs') or r.details.get('isrcs')),
                        min(dates, default='9999'), r.mbid)
            primary = sorted(eligible,key=priority)[0]
            song.primary_recording_mbid = primary.mbid
            song.primary_reason = '; '.join(version_kind(primary)[1])
        result.append(song)
    return sorted(result,key=lambda song:(title_key(song.title),song.id))


def grouping_statistics(recordings: list[Recording], songs: list[Song]) -> dict:
    occurrences = {(r.mbid,c['release_mbid'],c.get('medium_position'),c.get('position')) for r in recordings for c in r.contexts}
    released_ids = {item[0] for item in occurrences}
    isrc_buckets=defaultdict(list)
    for recording in recordings:
        for code in set(recording.payload.get('isrcs',[]))|set(recording.details.get('isrcs',[])):
            normalized=normalized_isrc(code)
            if normalized:isrc_buckets[normalized].append(recording)
    suspected=set();conflicts=set()
    for bucket in isrc_buckets.values():
        for left,right in combinations(bucket,2):
            if left.mbid==right.mbid or credit_ids(left.credits)!=credit_ids(right.credits):continue
            pair=tuple(sorted((left.mbid,right.mbid)))
            kinds=(version_kind(left)[0],version_kind(right)[0])
            if (len(identity_work_ids(left)|identity_work_ids(right))>1 or ('unknown' not in kinds and kinds[0]!=kinds[1])):
                conflicts.add(pair)
            else:suspected.add(pair)
    return {'raw_recording_count':len(recordings),'independent_song_count':sum(not s.pending_confirmation for s in songs),
            'work_verified_song_count':len({s.work_ids[0] for s in songs if not s.pending_confirmation and len(s.work_ids)==1}),
            'human_confirmed_without_work_song_count':sum(s.reviewed and not s.pending_confirmation and not s.work_ids for s in songs),
            'song_entry_count':len(songs),
            'duplicate_release_count':len(occurrences)-len(released_ids),
            'release_occurrence_count':len(occurrences),'version_count':sum(len(s.recordings) for s in songs),
            'additional_version_count':sum(max(0,len(s.recordings)-1) for s in songs),
            'pending_song_count':sum(s.pending_confirmation for s in songs),
            'pending_recording_count':sum(len(s.recordings) for s in songs if s.pending_confirmation),
            'direct_work_recording_count':sum(bool(work_ids(r)) for r in recordings),
            'additional_identity_recording_count':sum(bool(r.identity_links) and not work_ids(r) for r in recordings),
            'manually_reviewed_song_count':sum(s.reviewed for s in songs),
            'suspected_duplicate_recording_pairs':len(suspected-conflicts),'isrc_conflict_pairs':len(conflicts),
            'primary_studio_version_count':sum(s.primary_recording_mbid is not None for s in songs),
            'grouping_rule_version':RULE_VERSION}
