"""Evidence fetching must resume without inventing data or losing raw payloads."""
import threading

import httpx
import pytest

from melodyvault.catalog.grouping import group_recordings
from melodyvault.catalog.models import Artist, Recording, CatalogError, CatalogCancelled
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.supplement import supplement_pending, PROFILE
from melodyvault.database import initialize_database, connect
from melodyvault.database.catalog import CatalogRepository
from catalog_fixtures import ARTIST_ID, recording


def setup_repository(tmp_path, payload):
    repo = CatalogRepository(tmp_path / 'supplement.sqlite3')
    initialize_database(repo.path)
    artist = Artist(ARTIST_ID, '周杰倫')
    repo.save_artist('周杰伦', artist)
    repo.save_recordings(artist, [Recording.from_payload(payload)])
    return repo, artist


def test_isrc_lookup_adds_explicit_work_without_extra_versions_and_resumes(tmp_path):
    raw = {**recording(1), 'isrcs': ['TWAAA0100001']}
    repo, artist = setup_repository(tmp_path, raw)
    work = {'id': '50000000-0000-4000-8000-000000000001', 'title': '晴天', 'aliases': []}
    auxiliary = {**recording(2), 'video': True, 'isrcs': raw['isrcs'], 'relations': [
        {'type': 'performance', 'target-type': 'work', 'work': work, 'attributes': []}]}
    calls = []

    def transport(request):
        endpoint = request.url.path.removeprefix('/ws/2/')
        calls.append(endpoint)
        if endpoint.startswith('recording/'):
            return httpx.Response(200, json={**raw, 'relations': [], 'releases': []})
        if endpoint.startswith('isrc/'):
            return httpx.Response(200, json={'isrc': 'TWAAA0100001', 'recordings': [auxiliary]})
        if endpoint.startswith('work/'):
            return httpx.Response(200, json=work)
        raise AssertionError(endpoint)

    with connect(repo.path) as db:
        original = db.execute('SELECT payload_json FROM catalog_recordings').fetchone()[0]
    assert group_recordings(artist, repo.recordings(artist.mbid), {})[0].pending_confirmation
    progress = []
    with MusicBrainzClient(repo, threading.Event(), transport=httpx.MockTransport(transport), interval=0) as client:
        stats = supplement_pending(repo, client, artist, progress.append)
        assert stats['targeted_fetched'] == stats['isrc_lookup_count'] == 1
        songs = group_recordings(artist, repo.recordings(artist.mbid), repo.works())
        assert len(songs) == 1 and not songs[0].pending_confirmation
        assert len(songs[0].recordings) == 1 and songs[0].work_ids == (work['id'],)
        old_calls = list(calls)
        supplement_pending(repo, client, artist, progress.append)
        assert calls == old_calls
    assert any(event.stage == 'isrc_evidence' for event in progress)
    assert auxiliary['id'] in repo.related()
    assert len(repo.recordings(artist.mbid)) == 1
    with connect(repo.path) as db:
        assert db.execute('SELECT payload_json FROM catalog_recordings').fetchone()[0] == original


def test_failed_pending_lookup_is_retryable_and_cancelled_task_keeps_raw(tmp_path):
    raw = recording(1)
    repo, artist = setup_repository(tmp_path, raw)
    attempts = []

    def transport(request):
        attempts.append(request.url.path)
        if len(attempts) == 1:
            return httpx.Response(503, json={'error': 'actual service busy'})
        return httpx.Response(200, json={**raw, 'relations': [], 'releases': []})

    with MusicBrainzClient(repo, threading.Event(), transport=httpx.MockTransport(transport), interval=0, max_attempts=1) as client:
        with pytest.raises(CatalogError, match='503.*actual service busy'):
            supplement_pending(repo, client, artist, lambda event: None)
        assert not repo.evidence_fetch_fresh(raw['id'], PROFILE)
        supplement_pending(repo, client, artist, lambda event: None)
        assert repo.evidence_fetch_fresh(raw['id'], PROFILE)
        supplement_pending(repo, client, artist, lambda event: None)
        assert len(attempts) == 2
        client.cancel.set()
        with pytest.raises(CatalogCancelled):
            supplement_pending(repo, client, artist, lambda event: None)
    assert len(repo.recordings(artist.mbid)) == 1
    assert group_recordings(artist, repo.recordings(artist.mbid), {})[0].pending_confirmation
