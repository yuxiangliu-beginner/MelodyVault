import json
from melodyvault.database import initialize_database,connect
from melodyvault.search.recording_bridge import linked_recording

def test_bridge_requires_exact_official_recording_link(tmp_path):
    path=tmp_path/'db.sqlite3';initialize_database(path)
    song={'title':'晴天','artist':'周杰伦','source_url':'https://music.apple.com/tw/album/x?i=123','duration':269}
    artist={'id':'artist','name':'周杰倫'};payload={'id':'recording','title':'晴天','length':269000}
    def detail(url):return json.dumps({'relations':[{'url':{'resource':url}}],'isrcs':['TW1234567890']})
    with connect(path) as db:
        db.execute('insert into catalog_artists values (?,?,?,?)',('artist','周杰倫',json.dumps(artist),'now'))
        db.execute('insert into catalog_recordings values (?,?,?,?,?)',('recording','晴天','晴天',json.dumps(payload),'now'))
        db.execute('insert into catalog_artist_recordings values (?,?,?,?)',('artist','recording',1,'[]'))
        db.execute('insert into catalog_recording_details values (?,?,?)',('recording',detail('https://music.apple.com/tw/album/other'),'now'))
    assert linked_recording(path,song) is None
    with connect(path) as db:db.execute('update catalog_recording_details set payload_json=?',(detail(song['source_url']),))
    assert linked_recording(path,song)['recording_id']=='recording'
    assert linked_recording(path,{**song,'artist':'其他歌手'}) is None
    assert linked_recording(path,{**song,'duration':30}) is None
