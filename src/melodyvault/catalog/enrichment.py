"""Read official Work relationships without changing original Recording payloads."""
from melodyvault.catalog.models import Artist, CatalogError, Progress
from melodyvault.catalog.musicbrainz import MusicBrainzClient, check_cancel
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.evidence import fresh_checks, save_checks


def enrich_recordings(repository: CatalogRepository, client: MusicBrainzClient, artist: Artist, progress) -> None:
    def pages(endpoint, params, key, label):
        offset = 0
        signatures = set()
        while True:
            check_cancel(client.cancel)
            data = client.get_json(endpoint, {**params, 'limit': 100, 'offset': offset})
            items, total = data[key], data[f'{endpoint}-count']
            signature = tuple(item['id'] for item in items)
            if data.get(f'{endpoint}-offset', offset) != offset or (not items and offset < total) or (items and signature in signatures):
                raise CatalogError(f'MusicBrainz {endpoint} 证据分页异常，offset={offset}, total={total}')
            signatures.add(signature)
            yield items
            offset += len(items)
            progress(Progress('work_evidence', offset, total, f'{label}：{offset}/{total}', artist))
            if offset >= total:
                return

    progress(Progress('work_evidence', 0, None, '读取官方 Recording → Work 关系（保留原始录音）', artist))
    seen = set()
    def mark(items):
        save_checks(repository,'recording','work-relations-v1',[(item['id'],
            'has_work' if any(r.get('type')=='performance' and r.get('work') for r in item.get('relations',[])) else 'no_work',
            {'work_ids':[r['work']['id'] for r in item.get('relations',[]) if r.get('type')=='performance' and r.get('work')]}) for item in items])
    for items in pages('recording', {'artist': artist.mbid, 'inc': 'artist-credits+isrcs+work-rels+recording-rels'}, 'recordings', '录音作品关系'):
        repository.save_details(items)
        repository.save_related(items,'official recording artist browse')
        mark(items)
        seen.update(item['id'] for item in items)
    missing = [recording for recording in repository.recordings(artist.mbid) if recording.mbid not in seen]
    fresh = fresh_checks(repository,'recording','work-relations-v1') if not client.force_refresh else set()
    for index, recording in enumerate(missing, 1):
        check_cancel(client.cancel)
        if recording.mbid in fresh:
            continue
        progress(Progress('work_evidence', index - 1, len(missing), f'补查发行曲目专属录音关系：{index}/{len(missing)}', artist))
        try:
            data = client.get_json(f'recording/{recording.mbid}', {'inc': 'artist-credits+isrcs+work-rels+recording-rels'})
        except CatalogError as error:
            if 'HTTP 404' not in str(error):
                raise
            client.notice(str(error)+'；保留原始录音并标明补证失败')
            data = {**recording.payload, 'relations': [], '_lookup_error': str(error)}
        if data['id'] != recording.mbid:
            if repository.recording_redirects().get(recording.mbid)!=data['id']:
                raise CatalogError(f'Recording lookup MBID 不一致：{recording.mbid} / {data["id"]}')
        repository.save_details([data])
        repository.save_related([data],'official recording lookup')
        if not data.get('_lookup_error'):
            mark([data])
    browsed_work_ids = set()
    for items in pages('work', {'artist': artist.mbid, 'inc': 'aliases+artist-rels+recording-rels'}, 'works', '作品/别名/反向录音关系'):
        repository.save_works(items)
        browsed_work_ids.update(work['id'] for work in items)
    works = repository.works()
    linked = {}
    for recording in repository.recordings(artist.mbid):
        for relation in recording.details.get('relations', []):
            if relation.get('target-type') == 'work' and relation.get('type') == 'performance' and relation.get('work', {}).get('id'):
                linked[relation['work']['id']] = relation['work']
    missing_work_ids = sorted(set(linked) - (browsed_work_ids if client.force_refresh else set(works)))
    for index, work_id in enumerate(missing_work_ids, 1):
        progress(Progress('work_evidence', index - 1, len(missing_work_ids), f'补查关联作品别名：{index}/{len(missing_work_ids)}', artist))
        work = client.get_json(f'work/{work_id}', {'inc': 'aliases+artist-rels+recording-rels'})
        if work['id'] != work_id:
            raise CatalogError(f'Work lookup MBID 不一致：{work_id}')
        repository.save_works([work])
