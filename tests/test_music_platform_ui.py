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

def test_failed_provider_does_not_cache_partial_results(tmp_path):
    path=tmp_path/'db.sqlite3';initialize_database(path)
    class Provider:
        def __init__(self,name,fail=False):self.name=name;self.fail=fail;self.requests=0
        def search(self,q):
            self.requests+=1
            if self.fail:raise RuntimeError('source unavailable')
            return [PlatformSong(self.name,'1','晴天','周杰倫','',269,'https://music.apple.com/tw/album/x')]
    ok=Provider('one');bad=Provider('two',True);service=PlatformSearchService(path,providers=[ok,bad])
    first=service.search('周杰伦 晴天');second=service.search('周杰伦 晴天')
    assert len(first['rows'])==1 and first['statuses']['two']['status']=='FAILED'
    assert not second['cached'] and ok.requests==2 and bad.requests==2

def test_simple_shell_and_history_keep_missing_and_failed(tmp_path):
    app=QApplication.instance() or QApplication([]);path=tmp_path/'db.sqlite3';initialize_database(path);repo=DownloadRepository(path)
    target={'song_id':'test','recording_id':'test','artist':{'id':'a','name':'测试歌手'},'title':'测试歌曲','version':'unknown'}
    a=repo.enqueue(target,repo.settings());repo.update(a,state='COMPLETED',result_json=json.dumps({'path':str(tmp_path/'missing.mp3'),'format':'mp3'}))
    b=repo.enqueue({**target,'recording_id':'other'},repo.settings());repo.update(b,state='FAILED')
    w=MusicWindow(path)
    try:
        assert [w.tabs.tabText(i) for i in range(w.tabs.count())]==['音乐搜索','我的音乐','媒体转换']
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

def test_imported_history_preserves_selection_and_shows_missing_file(tmp_path):
    app=QApplication.instance() or QApplication([]);path=tmp_path/'db.sqlite3';initialize_database(path)
    missing=str(tmp_path/'missing.mp3')
    with connect(path) as db:db.execute('insert into personal_music values(?,?,?,?,?,?,?,?,?,?,?)',('x','歌曲','歌手','',1,'mp3',missing,1,'a'*64,'import','now'))
    w=MusicWindow(path)
    try:
        item=w.history.topLevelItem(0).child(0);assert item.text(2)=='文件不存在' and item.text(3)==missing
        w.history.setCurrentItem(item);w.refresh_history()
        assert w.history.currentItem().data(0,256)=={'library_path':missing}
    finally:w.close();app.processEvents()

def test_cancelled_download_is_not_displayed_as_unavailable(tmp_path):
    from PySide6.QtWidgets import QPushButton
    app=QApplication.instance() or QApplication([]);path=tmp_path/'db.sqlite3';initialize_database(path);w=MusicWindow(path)
    try:
        w.active_download_button=QPushButton('下载中')
        w.download_done({'attempts':[{'state':'CANCELLED'}],'errors':{},'candidates':[]})
        assert w.active_download_button.text()=='重试' and w.status.text()=='任务已取消。'
    finally:w.close();app.processEvents()


def test_new_download_group_is_visible_and_user_collapse_is_preserved(tmp_path):
    app=QApplication.instance() or QApplication([]);path=tmp_path/'db.sqlite3';initialize_database(path);w=MusicWindow(path)
    try:
        with connect(path) as db:db.execute('insert into personal_music values(?,?,?,?,?,?,?,?,?,?,?)',
            ('new','新歌','新歌手','',150,'ogg',str(tmp_path/'song.ogg'),100,'b'*64,'download','now'))
        w.refresh_history();group=w.history.topLevelItem(0)
        assert group.isExpanded() and group.child(0).text(0)=='新歌'
        group.setExpanded(False);w.refresh_history();assert not w.history.topLevelItem(0).isExpanded()
    finally:w.close();app.processEvents()
