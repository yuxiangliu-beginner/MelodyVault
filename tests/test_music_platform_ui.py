import json
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database,connect
from melodyvault.database.downloads import DownloadRepository
from melodyvault.ui.music_window import MusicWindow
from melodyvault.search.platforms import PlatformSearchService,PlatformSong

def test_platform_search_does_not_call_musicbrainz_and_keeps_versions(tmp_path):
    path=tmp_path/'db.sqlite3';initialize_database(path)
    class Provider:
        name='test';requests=1
        def search(self,q):return [PlatformSong('test','1','晴天','周杰倫','',269,'https://music.apple.com/tw/album/x'),PlatformSong('test','2','晴天 (Live)','周杰倫','',300,'https://music.apple.com/tw/album/y','live')]
    service=PlatformSearchService(path,providers=[Provider()]);result=service.search('周杰伦 晴天')
    assert [r['song_id'] for r in result['rows']]==['1','2']
    assert service.search('周杰伦 晴天')['requests']==0

def test_simple_shell_and_history_keep_missing_and_failed(tmp_path):
    app=QApplication.instance() or QApplication([]);path=tmp_path/'db.sqlite3';initialize_database(path);repo=DownloadRepository(path)
    target={'song_id':'test','recording_id':'test','artist':{'id':'a','name':'测试歌手'},'title':'测试歌曲','version':'unknown'}
    a=repo.enqueue(target,repo.settings());repo.update(a,state='COMPLETED',result_json=json.dumps({'path':str(tmp_path/'missing.mp3'),'format':'mp3'}))
    b=repo.enqueue({**target,'recording_id':'other'},repo.settings());repo.update(b,state='FAILED')
    w=MusicWindow(path)
    try:
        assert [w.tabs.tabText(i) for i in range(w.tabs.count())]==['音乐搜索','下载记录','视频转 MP3']
        assert [w.table.horizontalHeaderItem(i).text() for i in range(w.table.columnCount())]==['歌曲','歌手','时长','操作']
        w.results({'rows':[{'title':'晴天','artist':'周杰伦','duration':0,'source_url':'https://music.apple.com/','source':'apple','song_id':'1','version':'unknown'}],'statuses':{'apple':{'status':'COMPLETED'}}})
        assert w.table.item(0,2).text()=='--:--' and w.table.cellWidget(0,3).text()=='下载'
        assert w.history.topLevelItemCount()==2
        states=[w.history.topLevelItem(i).child(0).text(2) for i in range(2)]
        assert '文件不存在' in states and '下载失败' in states
        for i in range(w.history.topLevelItemCount()):w.history.topLevelItem(i).setExpanded(False)
        w.refresh_history();assert all(not w.history.topLevelItem(i).isExpanded() for i in range(w.history.topLevelItemCount()))
        w.filter.setText('没有这个歌手');assert w.history.topLevelItemCount()==0
    finally:w.close();app.processEvents()
