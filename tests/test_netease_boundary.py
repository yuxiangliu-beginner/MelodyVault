import pytest
from melodyvault.providers.netease import NeteaseMusicSearchProvider,NeteaseSearchRequest,NeteaseUnavailable


def test_unverified_netease_never_claims_search_or_download():
    provider=NeteaseMusicSearchProvider()
    assert not provider.is_enabled
    assert provider.get_status()['status']=='RESTRICTED'
    assert not provider.get_capabilities()['download']
    for query in (NeteaseSearchRequest(artist='周杰伦'),NeteaseSearchRequest(title='晴天'),
                  NeteaseSearchRequest(album='叶惠美'),NeteaseSearchRequest(song_id='123')):
        with pytest.raises(NeteaseUnavailable):provider.search(query)


def test_empty_query_is_rejected_before_any_access():
    with pytest.raises(ValueError):NeteaseMusicSearchProvider().search(NeteaseSearchRequest())
