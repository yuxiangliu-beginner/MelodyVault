"""Search-page recall and precision for the two downloadable sources (Commons, Archive)."""
import httpx,pytest
from melodyvault.search import platforms
from melodyvault.sources.http import SourceHTTP
from melodyvault.sources.matching import core_title


def archive_http(monkeypatch,items,docs_by_query=None):
    """Mock Archive: items by identifier; docs per query kind ('fielded' or 'full')."""
    seen=[]
    def handler(request):
        if request.url.path=='/advancedsearch.php':
            q=request.url.params['q'];seen.append(q)
            kind='fielded' if 'title:(' in q else 'full'
            docs=(docs_by_query or {}).get(kind,list(items))
            return httpx.Response(200,json={'response':{'docs':[{'identifier':i} for i in docs]}})
        return httpx.Response(200,json=items[request.url.path.rsplit('/',1)[-1]])
    monkeypatch.setattr(platforms,'SourceHTTP',lambda cancel:SourceHTTP(cancel,transport=httpx.MockTransport(handler),interval=0,max_attempts=1))
    return seen


ALBUM={'metadata':{'title':'周杰倫好聽的 20首歌','creator':'周杰倫'},'files':[
    {'name':'01.mp3','source':'original','title':'晴天','length':'269'},
    {'name':'02.mp3','source':'original','title':'稻香','length':'223'},
    {'name':'cover.jpg','source':'original'}]}
ENGLISH={'metadata':{'title':'Jay Chou Fearless','creator':'Jay Chou'},'files':[
    {'name':'fearless.mp3','source':'original','title':'Fearless','creator':'Jay Chou','length':'250'}]}
PODCAST={'metadata':{'title':'Film Club Podcast','creator':'Film Club','description':'we talk about 周杰倫'},'files':[
    {'name':'ep2.mp3','source':'original','title':'Episode 2','length':'3000'}]}


def test_artist_only_query_lists_album_tracks_named_only_by_the_item(monkeypatch):
    archive_http(monkeypatch,{'album':ALBUM,'podcast':PODCAST})
    rows=platforms.ArchiveMusicSearch().search('周杰伦')
    assert [(r.title,r.artist,r.album) for r in rows]==[('晴天','周杰倫','周杰倫好聽的 20首歌'),('稻香','周杰倫','周杰倫好聽的 20首歌')]


def test_compilation_title_alone_does_not_pull_in_unrelated_tracks(monkeypatch):
    # Real case: "周杰倫好聽的 20首歌" with no credited artist, full of other people's songs.
    grab_bag={'metadata':{'title':'周杰倫好聽的 20首歌 Best Songs Of Jay Chou'},'files':[
        {'name':'a.mp3','source':'original','title':'Charli xcx - party 4 u','length':'297'},
        {'name':'b.mp3','source':'original','title':'Connie Francis - Pretty Little Baby','length':'143'},
        {'name':'c.mp3','source':'original','title':'周杰倫 - 晴天','length':'269'}]}
    single={'metadata':{'title':'发如雪 周杰伦'},'files':[{'name':'track.mp3','source':'original','title':'Track 1','length':'299'}]}
    archive_http(monkeypatch,{'bag':grab_bag,'single':single})
    rows=platforms.ArchiveMusicSearch().search('周杰伦')
    assert [(r.song_id,r.title,r.artist) for r in rows]==[('bag/c.mp3','晴天','周杰倫'),('single/track.mp3','发如雪 周杰伦','未知歌手')]


def test_uncredited_artist_dash_title_file_names_are_split(monkeypatch):
    item={'metadata':{'title':'Jay Chou Dandelions Promise'},'files':[
        {'name':'Jay_Chou_-_Rainbow_AsianPopMusic.net.mp3','source':'original'},
        {'name':'01.mp3','source':'original','title':'Jay Chou - Ge Qian'},
        {'name':'mix.mp3','source':'original','title':'Best Songs Of Jay Chou Collection - 20 Songs Mix'}]}
    archive_http(monkeypatch,{'x':item})
    rows=platforms.ArchiveMusicSearch().search('Jay Chou')
    assert sorted((r.artist,r.title) for r in rows)==[('Jay Chou','Ge Qian'),('Jay Chou','Rainbow AsianPopMusic.net'),
        ('未知歌手','Best Songs Of Jay Chou Collection - 20 Songs Mix')]  # long left side is not an artist


def test_artist_and_song_query_keeps_only_that_song(monkeypatch):
    archive_http(monkeypatch,{'album':ALBUM})
    assert [r.title for r in platforms.ArchiveMusicSearch().search('周杰伦 稻香')]==['稻香']


def test_multi_word_english_names_are_not_split_into_artist_and_song(monkeypatch):
    archive_http(monkeypatch,{'en':ENGLISH})
    rows=platforms.ArchiveMusicSearch().search('Jay Chou')
    assert [(r.title,r.artist) for r in rows]==[('Fearless','Jay Chou')]


def test_title_creator_matches_come_first_and_full_text_only_fills(monkeypatch):
    seen=archive_http(monkeypatch,{'album':ALBUM,'podcast':PODCAST},{'fielded':['album'],'full':['podcast','album']})
    search=platforms.ArchiveMusicSearch(max_items=2)
    rows=search.search('周杰伦')
    assert len(seen)==2 and 'title:(' in seen[0] and 'creator:(' in seen[0] and 'title:(' not in seen[1]
    assert {r.song_id.split('/')[0] for r in rows}=={'album'}  # the podcast has no matching track
    seen.clear();platforms.ArchiveMusicSearch(max_items=1).search('周杰伦')
    assert len(seen)==1  # enough title/creator matches: no full-text query


def test_flac_original_is_preferred_over_mp3_original_of_the_same_song(monkeypatch):
    item={'metadata':{'title':'Album','creator':'Singer'},'files':[
        {'name':'song.mp3','source':'original','title':'Song','length':'200'},
        {'name':'song.flac','source':'original','title':'Song','length':'200'}]}
    archive_http(monkeypatch,{'x':item})
    assert [r.song_id for r in platforms.ArchiveMusicSearch().search('Singer Song')]==['x/song.flac']


def commons_http(monkeypatch,pages):
    def handler(request):return httpx.Response(200,json={'query':{'pages':pages}})
    monkeypatch.setattr(platforms,'SourceHTTP',lambda cancel:SourceHTTP(cancel,transport=httpx.MockTransport(handler),interval=0,max_attempts=1))


def commons_page(pageid,name,desc,categories,artist=''):
    ext={'ObjectName':name,'ImageDescription':desc,'Categories':categories,'Artist':artist,'LicenseUrl':'https://creativecommons.org/publicdomain/zero/1.0/'}
    return {'pageid':pageid,'title':'File:'+name+'.ogg','imageinfo':[{'url':'https://upload.wikimedia.org/wikipedia/commons/a/ab/'+name+'.ogg',
        'descriptionurl':'https://commons.wikimedia.org/wiki/File:'+name+'.ogg','mime':'audio/ogg','mediatype':'AUDIO','size':10,
        'extmetadata':{k:{'value':v} for k,v in ext.items()},'metadata':[{'name':'length','value':100.}]}]}


def test_commons_drops_spoken_wikipedia_and_files_unrelated_to_the_query(monkeypatch):
    commons_http(monkeypatch,[
        commons_page(1,'En-Jay Chou-article','This is a spoken word version of the Wikipedia article: Jay Chou','Spoken English Wikipedia'),
        commons_page(2,'Tape 529, Conversation 016','On June 28, 1971, President Richard M. Nixon met','PD US'),
        commons_page(3,'是你','创作：陈正瑆 华语原创','Chinese songs')])
    assert [r.title for r in platforms.CommonsMusicSearch().search('是你')]==['是你']
    assert platforms.CommonsMusicSearch().search('Jay Chou')==[]  # only the spoken article mentions him


@pytest.mark.parametrize('title,artist,expected',[
    ('周杰倫 - 退後 [192kHz]','周杰倫','退后'),('青花瓷 - 周杰伦 (R&B Version)','周杰伦','青花瓷'),
    ('稻香','周杰倫','稻香'),('Jay Chou- Fearless','Jay Chou','Fearless'),
    ('霸王别姬【西皮二六】','梅兰芳 / 齐如山','霸王别姬'),('周杰倫','周杰倫','周杰伦')])
def test_core_title_strips_artist_brackets_and_separators(title,artist,expected):
    assert core_title(title,artist)==expected
