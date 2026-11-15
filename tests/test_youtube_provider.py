"""Synthetic API responses; never treated as live YouTube results."""
import httpx,pytest,threading
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.providers.video_search import YouTubeSearchProvider


def test_missing_key_is_unconfigured_without_network():
    calls=[];provider=YouTubeSearchProvider(key='',transport=httpx.MockTransport(lambda r:calls.append(r)))
    assert provider.get_status()['status']=='NOT_CONFIGURED'
    with pytest.raises(RuntimeError):provider.search('周杰伦 晴天')
    assert not calls and provider.requests==0


def test_official_metadata_only_and_memory_cache():
    requests=[]
    def handle(request):
        requests.append(request)
        if request.url.path.endswith('/search'):
            return httpx.Response(200,json={'items':[{'id':{'videoId':'abcdefghijk'},'snippet':{'title':'Official test','channelTitle':'Artist',
                'publishedAt':'2020-01-01T00:00:00Z','channelId':'channel'}}]})
        return httpx.Response(200,json={'items':[{'id':'abcdefghijk','contentDetails':{'duration':'PT4M10S'},'status':{'license':'creativeCommon'}}]})
    provider=YouTubeSearchProvider(key='local-test-key',transport=httpx.MockTransport(handle),interval=0,_display_compliant=True)
    results=provider.search('歌手 歌曲')
    assert len(results)==1 and results[0].duration==250 and results[0].source_url=='https://www.youtube.com/watch?v=abcdefghijk'
    assert results[0].download_permission=='METADATA_ONLY' and results[0].recording_id=='' and results[0].match_score==0
    assert 'local-test-key' not in repr(results)
    assert all('local-test-key' not in str(request.url) and request.headers['X-Goog-Api-Key']=='local-test-key' for request in requests)
    assert provider.search('歌手 歌曲')==results and len(requests)==2


def test_error_never_exposes_api_key_and_cancel_prevents_request():
    provider=YouTubeSearchProvider(key='local-test-key',transport=httpx.MockTransport(lambda r:httpx.Response(403)),interval=0,_display_compliant=True)
    with pytest.raises(RuntimeError) as error:provider.search('song')
    assert '403' in str(error.value) and 'local-test-key' not in str(error.value)
    cancel=threading.Event();cancel.set();provider=YouTubeSearchProvider(key='local-test-key',cancel=cancel,
        transport=httpx.MockTransport(lambda r:pytest.fail('must not request')),interval=0,_display_compliant=True)
    with pytest.raises(CatalogCancelled):provider.search('song')


def test_configured_key_still_requires_reviewed_branding():
    provider=YouTubeSearchProvider(key='local-test-key',transport=httpx.MockTransport(lambda r:pytest.fail('must not request')))
    assert provider.get_status()['status']=='RESTRICTED'
    with pytest.raises(RuntimeError):provider.search('song')
    assert provider.requests==0
