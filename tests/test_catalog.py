import threading
import time
import httpx
import pytest
from melodyvault.catalog.models import ArtistChoiceRequired, CatalogCancelled, CatalogError, Recording
from melodyvault.catalog.musicbrainz import MusicBrainzClient, RateGate
from melodyvault.catalog.normalize import display_name, name_key, search_names
from melodyvault.catalog.service import CatalogService
from melodyvault.database import connect, initialize_database
from melodyvault.database.catalog import CatalogRepository
from catalog_fixtures import ARTIST_ID, CatalogTransport, recording


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    initialize_database(path)
    return CatalogRepository(path)


def make_client(repository, transport, cancel=None, **options):
    return MusicBrainzClient(repository, cancel or threading.Event(), transport=httpx.MockTransport(transport),
                            interval=0, retry_base=0, max_attempts=2, **options)


def test_simplified_traditional_and_unicode_normalization():
    assert name_key(" 周杰倫 ") == name_key("周杰伦")
    assert display_name("髮如雪") == "发如雪"
    assert name_key("ＡＢＣ　夜曲") == name_key("abc 夜曲")
    assert "周杰倫" in search_names("周杰伦")


def test_recording_identity_is_not_title():
    first = Recording.from_payload(recording(1, "髮如雪"))
    first.merge(Recording.from_payload(recording(1, "发如雪"), True, "official"))
    assert first.official and first.title == "发如雪"
    with pytest.raises(ValueError):
        first.merge(Recording.from_payload(recording(2, "发如雪")))


def test_pagination_dedup_versions_collaboration_and_persistence(repository):
    transport = CatalogTransport()
    progress = []
    with make_client(repository, transport) as client:
        result = CatalogService(repository, client, progress.append).search("周杰伦")
    assert result.artist.mbid == ARTIST_ID
    assert len(result.recordings) == 4
    assert len({song.mbid for song in result.recordings}) == 4
    assert sum(song.title == "晴天" for song in result.recordings) == 2
    assert any(song.display_title == "晴天（live）" for song in result.recordings)
    assert "发如雪" in {song.title for song in result.recordings}
    assert "其他歌手的曲目" not in {song.title for song in result.recordings}
    assert result.summary["excluded_video_recordings"] == 1
    assert result.summary["official_recording_count"] == 3
    assert result.summary["collaboration_recording_count"] == 1
    assert result.summary["duplicate_occurrences_removed"] == 3
    assert result.summary["pages"] == {'recordings': 2, 'release_groups': 2, 'official_releases': 2, 'collaboration_releases': 1}
    assert [int(params['offset']) for endpoint, params in transport.calls
            if endpoint == 'release' and 'artist' in params] == [0, 1]
    assert [int(params['offset']) for endpoint, params in transport.calls
            if endpoint == 'recording' and 'work-rels' not in params.get('inc','')] == [0, 2]
    assert [int(params['offset']) for endpoint, params in transport.calls
            if endpoint == 'recording' and 'work-rels' in params.get('inc','')] == [0, 2]
    assert len(repository.recordings(ARTIST_ID)) == 4
    with connect(repository.path) as db:
        assert db.execute("SELECT status FROM catalog_runs").fetchone()[0] == "completed"
        assert db.execute("SELECT count(*) FROM catalog_tracks").fetchone()[0] == 7
        assert db.execute("SELECT count(*) FROM catalog_release_groups").fetchone()[0] == 3
    assert any(p.stage == 'recordings' and p.processed == 2 and p.total == 3 for p in progress)
    assert progress[-1].stage == 'complete'


def test_repeat_search_uses_cache_without_network(repository):
    transport = CatalogTransport()
    with make_client(repository, transport) as client:
        original = CatalogService(repository, client).search("周杰伦")
    transport.calls.clear()
    with make_client(repository, transport) as client:
        repeated = CatalogService(repository, client).search("周杰倫")
    assert not transport.calls
    assert repeated.summary['api_requests'] == 0
    assert repeated.summary['cache_hits'] > 0
    assert {s.mbid for s in original.recordings} == {s.mbid for s in repeated.recordings}


def test_cancel_saves_pages_and_next_search_resumes(repository):
    transport = CatalogTransport()
    cancel = threading.Event()
    def cancel_after_page(progress):
        if progress.stage == 'recordings' and progress.processed == 2:
            cancel.set()
    with make_client(repository, transport, cancel) as client:
        with pytest.raises(CatalogCancelled):
            CatalogService(repository, client, cancel_after_page).search("周杰伦")
    with connect(repository.path) as db:
        assert db.execute("SELECT status FROM catalog_runs").fetchone()[0] == 'cancelled'
        assert db.execute("SELECT count(*) FROM catalog_recordings").fetchone()[0] == 2
    transport.calls.clear()
    with make_client(repository, transport) as client:
        result = CatalogService(repository, client).search("周杰伦")
    assert len(result.recordings) == 4 and result.summary['cache_hits'] >= 2
    assert not any(endpoint == 'recording' and params.get('offset') == '0'
                   and 'work-rels' not in params.get('inc','') for endpoint, params in transport.calls)


def test_real_error_details_and_failed_page_is_retryable(repository):
    transport = CatalogTransport()
    transport.fail_recording_page = True
    notices = []
    with make_client(repository, transport) as client:
        with pytest.raises(CatalogError, match='HTTP 503.*offline fixture busy'):
            CatalogService(repository, client, notices.append).search("周杰伦")
    with connect(repository.path) as db:
        assert db.execute("SELECT status FROM catalog_runs").fetchone()[0] == 'failed'
    assert any('503' in event.message for event in notices)
    transport.fail_recording_page = False
    with make_client(repository, transport) as client:
        result = CatalogService(repository, client).search("周杰伦")
    assert len(result.recordings) == 4


def test_ambiguous_artist_is_not_silently_selected(repository):
    transport = CatalogTransport()
    transport.ambiguous = True
    with make_client(repository, transport) as client:
        with pytest.raises(ArtistChoiceRequired) as choice:
            CatalogService(repository, client).search("周杰伦")
    assert len(choice.value.candidates) == 2
    assert len(transport.calls) == 1
    with connect(repository.path) as db:
        assert db.execute("SELECT count(*) FROM catalog_artists").fetchone()[0] == 0
        assert db.execute("SELECT status FROM catalog_runs").fetchone()[0] == 'needs_selection'
    with make_client(repository, transport) as client:
        assert len(CatalogService(repository, client).search("周杰伦", ARTIST_ID).recordings) == 4


def test_repeated_page_cannot_be_marked_complete(repository):
    transport = CatalogTransport()
    transport.repeated_page = True
    with make_client(repository, transport) as client:
        with pytest.raises(CatalogError, match='分页提前结束或重复'):
            CatalogService(repository, client).search("周杰伦")


def test_rate_gate_and_cancellation():
    gate = RateGate(0.025)
    cancel = threading.Event()
    gate.wait(cancel)
    start = time.monotonic()
    gate.wait(cancel)
    assert time.monotonic() - start >= 0.020
    cancel.set()
    with pytest.raises(CatalogCancelled):
        gate.wait(cancel)


def test_non_retryable_http_error_and_malformed_json(repository):
    def denied(request):
        return httpx.Response(403, json={'error': 'not allowed'})
    with make_client(repository, denied) as client:
        with pytest.raises(CatalogError, match='HTTP 403 not allowed'):
            client.get_json('artist', {'query': 'anything'})
        assert client.requests == 1
    def invalid(request):
        return httpx.Response(200, text='not JSON')
    with make_client(repository, invalid) as client:
        with pytest.raises(CatalogError, match='JSON 解析失败'):
            client.get_json('artist', {'query': 'anything'})


def test_refresh_ignores_cache(repository):
    transport = CatalogTransport()
    with make_client(repository, transport) as client:
        CatalogService(repository, client).search("周杰伦")
    transport.calls.clear()
    with make_client(repository, transport, force_refresh=True) as client:
        result = CatalogService(repository, client).search("周杰伦")
    assert result.summary['api_requests'] > 0 and result.summary['cache_hits'] == 0
