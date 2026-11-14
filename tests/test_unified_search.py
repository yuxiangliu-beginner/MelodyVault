import threading,json
from dataclasses import replace
import httpx,pytest
from melodyvault.catalog.models import Artist,Recording,CatalogError,CatalogCancelled
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.review import ReviewService
from melodyvault.database import connect
from melodyvault.database.search import SearchRepository
from melodyvault.search.models import SearchRequest,SongCandidate,identity_key
from melodyvault.search.services import UnifiedSearchEngine
from melodyvault.search.selection import SongSelectionService
from melodyvault.sources.models import SourceQuery
from test_review import review_data,find
from catalog_fixtures import recording,credit,ARTIST_ID,OTHER_ID


@pytest.fixture
def library(review_data):
    repo,old_artist,records,review=review_data
    artist=Artist.from_payload({'id':ARTIST_ID,'name':'周杰倫','aliases':[{'name':'周杰伦'},{'name':'Jay Chou'}]})
    repo.save_artist('周杰伦',artist);review.load(artist)
    other=Artist.from_payload({'id':OTHER_ID,'name':'同名作品演唱者'})
    repo.save_artist(other.name,other)
    payload={**recording(9,'晴天'),'artist-credit':[credit(OTHER_ID,'同名作品演唱者')]}
    repo.save_recordings(other,[Recording.from_payload(payload)]);ReviewService(repo).load(other)
    return repo,artist,other,records,review


def client(repo,transport=None,event=None,attempts=1,force=False):
    return MusicBrainzClient(repo,event or threading.Event(),force,transport=httpx.MockTransport(transport or (lambda r:pytest.fail('Unexpected network'))),interval=0,retry_base=0,max_attempts=attempts)


def test_local_only_normalization_versions_and_different_performers(library):
    repo,artist,other,records,review=library
    with client(repo) as http:
        engine=UnifiedSearchEngine(repo,http)
        results=engine.search(SearchRequest(' 晴 天！ ','song',local_only=True))
        assert {c.artist.mbid for c in results.songs}=={artist.mbid,other.mbid}
        assert len({c.recording_mbid for c in results.songs})==4
        assert len({c.song_id for c in results.songs})==4
        assert engine.search(SearchRequest('周杰倫','artist',local_only=True)).artists[0].mbid==artist.mbid
        assert http.requests==0


def test_combined_artist_identity_and_pinyin_are_weak_not_official_alias(library):
    repo,artist,other,records,review=library
    with client(repo) as http:
        result=UnifiedSearchEngine(repo,http).search(SearchRequest('jay chou QING-TIAN','smart',local_only=True))
    assert result.title_query=='QING-TIAN' and result.songs
    assert {c.artist.mbid for c in result.songs}=={artist.mbid}
    assert all(c.pending_confirmation and not c.title_exact and any('拼音' in r for r in c.reasons) for c in result.songs)
    assert {c.recording_mbid for c in result.songs}=={r.mbid for r in records[:3]}


def test_smart_ambiguity_retains_artist_and_song_categories(library):
    repo,artist,other,records,review=library
    same=Artist.from_payload({'id':'20000000-0000-4000-8000-000000000001','name':'晴天'})
    repo.save_artist('晴天',same)
    with client(repo) as http:result=UnifiedSearchEngine(repo,http).search(SearchRequest('晴天','smart',local_only=True))
    assert result.artists and result.songs and result.artists[0].mbid==same.mbid


def test_typed_cache_and_artist_identity_never_reuse_another_mode(library):
    assert SearchRequest('AB C').cache_key()!=SearchRequest('A BC').cache_key()
    assert SearchRequest('Song (live)').cache_key()!=SearchRequest('Song').cache_key()
    repo,artist,other,records,review=library;calls=[]
    def transport(request):
        calls.append(request)
        if request.url.path.endswith('/artist'):return httpx.Response(200,json={'artists':[],'count':0,'offset':0})
        return httpx.Response(200,json={'recordings':[],'count':0,'offset':0})
    with client(repo,transport) as http:
        engine=UnifiedSearchEngine(repo,http)
        first=engine.search(SearchRequest('OnlyOnlineName','song'));assert http.requests==1
        assert engine.search(SearchRequest('onlyonlinename','song')).cache_hit and http.requests==1
        engine.search(SearchRequest('OnlyOnlineName','artist'));assert http.requests==2
        a=engine.search(SearchRequest('晴天','song',artist_ids=(artist.mbid,),local_only=True))
        b=engine.search(SearchRequest('晴天','song',artist_ids=(other.mbid,),local_only=True))
        assert {c.artist.mbid for c in a.songs}=={artist.mbid}
        assert {c.artist.mbid for c in b.songs}=={other.mbid}
    with connect(repo.path) as db:assert {r[0] for r in db.execute('SELECT mode FROM unified_search_cache')}=={'artist','song'}


def test_unknown_but_explicit_artist_id_cannot_leak_all_local_singers(library):
    repo,artist,other,records,review=library
    with client(repo) as http:
        result=UnifiedSearchEngine(repo,http).search(SearchRequest('晴天','song',artist_ids=('30000000-0000-4000-8000-000000000001',),local_only=True))
    assert not result.songs


def test_bare_title_local_partial_does_not_silently_choose_only_saved_singer(library):
    repo,artist,other,records,review=library;partials=[]
    remote={**recording(99,'晴天'),'artist-credit':[credit(OTHER_ID,'同名作品演唱者')]}
    def transport(request):return httpx.Response(200,json={'recordings':[remote],'count':1,'offset':0})
    with client(repo,transport) as http:
        result=UnifiedSearchEngine(repo,http,partial=partials.append).search(SearchRequest('晴天','song'))
    assert http.requests==1 and partials and partials[0].scope=='sqlite' and result.scope=='musicbrainz'
    assert len(partials[0].songs)==4 and len(result.songs)==5


def test_offline_failure_preserves_local_candidates_and_reports_error(library):
    repo,artist,other,records,review=library
    def transport(request):raise httpx.ConnectError('injected offline',request=request)
    with client(repo,transport) as http:result=UnifiedSearchEngine(repo,http).search(SearchRequest('晴天','song'))
    assert result.songs and 'offline' in result.errors['song'] and result.api_requests==1
    with connect(repo.path) as db:assert db.execute('SELECT count(*) FROM unified_search_cache').fetchone()[0]==0


def test_503_retries_and_cancelled_response_cannot_complete(library):
    repo,artist,other,records,review=library;calls=[]
    def transport(request):
        calls.append(1)
        return httpx.Response(503,json={'error':'injected busy'}) if len(calls)==1 else httpx.Response(200,json={'count':0,'offset':0,'recordings':[]})
    with client(repo,transport,attempts=2) as http:
        result=UnifiedSearchEngine(repo,http).search(SearchRequest('NonexistentTitle','song'))
        assert not result.errors and result.api_requests==2 and result.retries==1
    event=threading.Event()
    def cancel_transport(request):event.set();return httpx.Response(200,json={'count':0,'offset':0,'recordings':[]})
    with client(repo,cancel_transport,event) as http:
        with pytest.raises(CatalogCancelled):UnifiedSearchEngine(repo,http).search(SearchRequest('Cancel query','song'))


def test_multiword_song_is_not_reinterpreted_as_an_arbitrary_artist(library):
    repo,artist,other,records,review=library;calls=[]
    payload={**recording(99,'All Of Me'),'artist-credit':[credit(other.mbid,other.name)]}
    def transport(request):
        calls.append(request.url.path)
        assert request.url.path.endswith('/recording')
        return httpx.Response(200,json={'recordings':[payload],'count':1,'offset':0})
    with client(repo,transport) as http:result=UnifiedSearchEngine(repo,http).search(SearchRequest('All Of Me','song'))
    assert len(calls)==1 and result.songs[0].artist.mbid==other.mbid and result.title_query=='All Of Me'


def test_index_invalidates_after_manual_regroup_and_alias_selection(library):
    repo,artist,other,records,review=library
    with client(repo) as http:
        engine=UnifiedSearchEngine(repo,http);before=engine.search(SearchRequest('晴天','song',artist_ids=(artist.mbid,),local_only=True))
    snap=review.load(artist);review.decide(artist,'merge',find(snap,records[1].mbid).id,find(snap,records[0].mbid).id,'unit manual grouping')
    with client(repo) as http:
        after=UnifiedSearchEngine(repo,http).search(SearchRequest('晴天','song',artist_ids=(artist.mbid,),local_only=True))
    assert next(c for c in after.songs if c.recording_mbid==records[1].mbid).song_id!=next(c for c in before.songs if c.recording_mbid==records[1].mbid).song_id


def test_confirm_live_version_preserves_raw_manual_audit_and_source_version(library):
    repo,artist,other,records,review=library
    repo.save_details([{**records[1].payload,'disambiguation':'live','relations':[]}])
    snap=review.load(artist);review.decide(artist,'merge',find(snap,records[1].mbid).id,find(snap,records[0].mbid).id,'unit confirmed composition')
    with connect(repo.path) as db:
        raw=[tuple(r) for r in db.execute('SELECT * FROM catalog_recordings ORDER BY mbid')]
        audit=[tuple(r) for r in db.execute('SELECT * FROM catalog_review_events ORDER BY rowid')]
        groups=[tuple(r) for r in db.execute('SELECT * FROM catalog_songs ORDER BY song_id')]
    with client(repo) as http:
        result=UnifiedSearchEngine(repo,http).search(SearchRequest('晴天','song',local_only=True))
        selected=next(c for c in result.songs if c.recording_mbid==records[1].mbid)
        confirmed=SongSelectionService(repo,http).confirm(selected,result.request,'Qing Tian')
        assert http.requests==0 and len(confirmed.recordings)==1
    query=SourceQuery.from_song(confirmed.artist,confirmed.songs[0],repo.works())
    assert query.versions==['live'] and query.recording_ids==[records[1].mbid] and 'Qing Tian' in query.titles
    with connect(repo.path) as db:
        assert raw==[tuple(r) for r in db.execute('SELECT * FROM catalog_recordings ORDER BY mbid')]
        assert audit==[tuple(r) for r in db.execute('SELECT * FROM catalog_review_events ORDER BY rowid')]
        assert groups==[tuple(r) for r in db.execute('SELECT * FROM catalog_songs ORDER BY song_id')]
        assert db.execute('SELECT count(*) FROM unified_confirmations').fetchone()[0]==1


def test_new_recording_does_not_change_reviewed_work_group(library):
    repo,artist,other,records,review=library
    snap=review.load(artist);review.decide(artist,'merge',find(snap,records[1].mbid).id,find(snap,records[0].mbid).id,'manual before new recording')
    with connect(repo.path) as db:before=[tuple(r) for r in db.execute('SELECT * FROM catalog_songs WHERE reviewed=1')]
    payload={**recording(99),'relations':[{'type':'performance','target-type':'work','work':{'id':'w1','title':'晴天'},'attributes':[]}]}
    candidate=SongCandidate(payload['id'],'晴天',artist,origin='musicbrainz')
    with client(repo,lambda req:httpx.Response(200,json=payload)) as http:
        confirmed=SongSelectionService(repo,http).confirm(candidate,SearchRequest('晴天','song'),'晴天')
    assert confirmed.songs[0].pending_confirmation
    with connect(repo.path) as db:
        assert before==[tuple(r) for r in db.execute('SELECT * FROM catalog_songs WHERE reviewed=1')]
        assert db.execute('SELECT count(*) FROM catalog_song_recordings WHERE recording_mbid=?',(payload['id'],)).fetchone()[0]==1


def test_confirmation_rejects_wrong_performer_before_persistence(library):
    repo,artist,other,records,review=library
    payload={**recording(99),'artist-credit':[credit(other.mbid,other.name)]}
    with client(repo,lambda req:httpx.Response(200,json=payload)) as http:
        with pytest.raises(CatalogError,match='不属于'):
            SongSelectionService(repo,http).confirm(SongCandidate(payload['id'],'晴天',artist),SearchRequest('晴天','song'),'晴天')
    with connect(repo.path) as db:assert db.execute('SELECT count(*) FROM unified_confirmations').fetchone()[0]==0
