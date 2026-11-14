import threading
import httpx
import pytest
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.models import CatalogError,Artist,Recording
from melodyvault.catalog.identity import build_identity_links
from melodyvault.catalog.grouping import group_recordings
from melodyvault.catalog.normalize import normalized_isrc
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository
from catalog_fixtures import ARTIST_ID,recording


def test_only_valid_isrcs_are_strong_identifier_keys():
    assert normalized_isrc('TW-AAA-01-00001')=='TWAAA0100001'
    assert normalized_isrc(' tWaaa0100001 ')=='TWAAA0100001'
    assert normalized_isrc('unknown') is None
    assert normalized_isrc('../artist/x') is None


def test_official_canonical_redirect_retains_original_and_is_not_external(tmp_path):
    repo=CatalogRepository(tmp_path/'redirect.sqlite3');initialize_database(repo.path)
    first=recording(1);second=recording(2)
    artist=Artist.from_payload({'id':ARTIST_ID,'name':'周杰倫'})
    repo.save_artist('周杰伦',artist);repo.save_recordings(artist,[Recording.from_payload(first),Recording.from_payload(second)])
    def transport(request):
        if request.url.path.endswith(first['id']):
            return httpx.Response(301,headers={'Location':f'https://musicbrainz.org/ws/2/recording/{second["id"]}'})
        return httpx.Response(200,json=second)
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(transport),interval=0) as client:
        assert client.get_json('recording/'+first['id'])['id']==second['id']
        assert client.requests==2
    assert repo.recording_redirects()[first['id']]==second['id']
    records=repo.recordings(ARTIST_ID)
    related={second['id']:second}
    links=build_identity_links(artist,records,{},related,repo.recording_redirects())
    for r in records:r.identity_links=links.get(r.mbid,[])
    songs=group_recordings(artist,records,{})
    assert len(songs)==1 and len(songs[0].recordings)==2 and songs[0].pending_confirmation
    assert len(repo.recordings(ARTIST_ID))==2


def test_recording_redirect_cannot_follow_untrusted_host(tmp_path):
    repo=CatalogRepository(tmp_path/'bad.sqlite3');initialize_database(repo.path)
    calls=[]
    def transport(request):
        calls.append(request.url)
        return httpx.Response(301,headers={'Location':'https://example.com/ws/2/recording/'+recording(2)['id']})
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(transport),interval=0) as client:
        with pytest.raises(CatalogError,match='重定向不合法'):
            client.get_json('recording/'+recording(1)['id'])
    assert len(calls)==1
