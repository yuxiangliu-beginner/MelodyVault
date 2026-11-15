from melodyvault.providers.openverse import OpenverseProvider
from melodyvault.sources.models import SourceQuery
from melodyvault.sources.matching import match_candidate


class FakeHTTP:
    def __init__(self, item):
        self.item = item
        self.calls = []

    def json(self, url, params=None):
        self.calls.append((url, params))
        return {'results': [self.item] if params['q'] == '江南' else []}


def test_openverse_keeps_unverified_source_and_does_not_use_preview_as_download():
    http = FakeHTTP({'id':'x', 'title':'江南小镇', 'creator':'other',
                     'foreign_landing_url':'https://example.org/song',
                     'url':'https://example.org/preview.mp3', 'duration':120000,
                     'license_url':'https://creativecommons.org/licenses/by/4.0/',
                     'source':'jamendo', 'filetype':'mp3'})
    q = SourceQuery('artist', 'song', '林俊杰', '江南', ['林俊杰'], ['江南'], ['studio'], [], [])
    c = OpenverseProvider().search(q, http)[0]
    match_candidate(q, c)
    assert c.page_url == 'https://example.org/song'
    assert c.duration_seconds == 120
    assert c.audio_url == '' and c.license_status == 'LICENSE_UNVERIFIED'
    assert c.match_status == 'REVIEW_REQUIRED'
    assert c.evidence['preview_not_full_file']
    assert http.calls[-1][1]['q'] == '江南'


def test_openverse_rejects_unsafe_landing_urls():
    assert OpenverseProvider._candidate({'id':'x','foreign_landing_url':'http://localhost/private'}) is None
    assert OpenverseProvider._candidate({'id':'x','foreign_landing_url':'https://user:pass@example.org/'}) is None
