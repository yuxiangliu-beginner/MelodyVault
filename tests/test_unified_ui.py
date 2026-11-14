import threading,time
from dataclasses import replace
import httpx,pytest
from PySide6.QtCore import QThread,Signal,Qt,QTimer,QEventLoop
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.ui.main_window import MainWindow
from melodyvault.search.models import SearchRequest,SearchResult
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.models import Artist
from melodyvault.database import connect
from test_unified_search import library
from test_review import review_data


def wait(app,predicate):
    app.processEvents()
    if predicate():return
    loop=QEventLoop();timer=QTimer();deadline=QTimer();deadline.setSingleShot(True);expired=[]
    timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
    timer.start(10);deadline.start(30000);loop.exec();timer.stop();deadline.stop();app.processEvents()
    assert not expired,'Qt condition timed out'


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app,library):
    repo,*_=library;window=MainWindow(repo.path);window.local_only.setChecked(True);window.show()
    yield window
    window.close();wait(app,lambda:not window._requests_running() and window.source_page.worker is None)
    window.close();app.processEvents()


def search(app,window,text):
    window.artist_input.setText(text);QTest.keyClick(window.artist_input,Qt.Key.Key_Return)
    wait(app,lambda:not window._requests_running() and window.search_worker is None)


def test_enter_modes_no_automatic_song_choice_and_ui_thread_delivery(app,widget,monkeypatch):
    seen=[];original=widget._search_ready
    def ready(result):seen.append(QThread.currentThread());original(result)
    monkeypatch.setattr(widget,'_search_ready',ready)
    assert widget.artist_input.placeholderText()=='输入歌手名称或歌曲名称…'
    assert widget.search_mode.currentData()=='smart'
    search(app,widget,'晴天')
    result=widget.unified_results.result
    assert len({c.artist.mbid for c in result.songs})==2 and widget.last_result is None
    assert widget.search_button.text()=='搜索' and '录音候选' in widget.statistics_label.text()
    assert not widget.unified_results.song_button.isEnabled()
    assert all(t==widget.thread() for t in seen)
    QTest.mouseClick(widget.clear_button,Qt.MouseButton.LeftButton)
    assert widget.unified_results.tree.topLevelItemCount()==0 and not widget.artist_input.text()


def test_smart_ambiguous_artist_and_song_are_both_visible(app,widget,library):
    repo,artist,other,records,review=library
    repo.save_artist('晴天',Artist.from_payload({'id':'20000000-0000-4000-8000-000000000001','name':'晴天'}))
    search(app,widget,'晴天')
    tree=widget.unified_results.tree
    assert tree.topLevelItem(0).childCount()==1 and tree.topLevelItem(1).childCount()==4
    assert widget.worker is None and widget.last_result is None


def test_confirm_recording_starts_one_source_task_and_reuses_cache(app,widget,library,monkeypatch):
    from melodyvault.sources import worker as source_worker
    class Empty:
        name='empty';enabled=True;calls=0
        def search(self,q,http):self.calls+=1;return []
    provider=Empty();monkeypatch.setattr(source_worker,'default_providers',lambda:[provider])
    widget.search_mode.setCurrentIndex(widget.search_mode.findData('song'))
    for attempt in range(2):
        search(app,widget,'晴天')
        tree=widget.unified_results.tree;tree.setCurrentItem(tree.topLevelItem(1).child(0))
        assert widget.unified_results.song_button.isEnabled()
        QTest.mouseClick(widget.unified_results.song_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:not widget._requests_running() and widget.search_worker is None and widget.source_page.worker is None and widget.source_page.last_stats is not None)
        assert widget.last_result.summary['selection_scope']=='recording'
        assert len(widget.last_result.recordings)==1 and widget.source_page.last_stats['total']==1
    assert provider.calls==1
    with connect(library[0].path) as db:
        assert db.execute('SELECT count(*) FROM catalog_review_events').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM unified_confirmations').fetchone()[0]==2


def test_stale_uncooperative_worker_cannot_overwrite_new_query(app,widget,monkeypatch):
    from melodyvault.search import worker as module
    class Uncooperative(QThread):
        ready=Signal(object);partial=Signal(object);progress=Signal(str);failed=Signal(str);cancelled=Signal(str)
        def __init__(self,path,request,parent=None,**kwargs):super().__init__(parent);self.request=request;self.cancel_event=threading.Event()
        def cancel(self):self.cancel_event.set()
        def run(self):
            time.sleep(.2 if self.request.query=='old' else .02)
            self.ready.emit(SearchResult(self.request,title_query=self.request.query))
    monkeypatch.setattr(module,'SearchWorker',Uncooperative)
    widget.artist_input.setText('old');widget.start_search()
    widget.artist_input.setText('new');widget.start_search()
    wait(app,lambda:not widget._requests_running())
    assert widget.unified_results.result.request.query=='new'
    widget.artist_input.setText('old');widget.start_search();widget.clear_results()
    wait(app,lambda:not widget._requests_running())
    assert widget.unified_results.result is None and widget.last_result is None


def test_api_failure_keeps_local_candidates_and_cancel_closes_safely(app,widget,library,monkeypatch):
    from melodyvault.search import worker as module
    def factory(repo,event,force=False,notice=None):
        return MusicBrainzClient(repo,event,force,notice,transport=httpx.MockTransport(lambda r:httpx.Response(503,json={'error':'injected busy'})),interval=0,max_attempts=1)
    monkeypatch.setattr(module,'MusicBrainzClient',factory)
    widget.local_only.setChecked(False);widget.search_mode.setCurrentIndex(widget.search_mode.findData('song'))
    search(app,widget,'晴天')
    assert widget.unified_results.result.songs and '503' in widget.unified_results.summary.text()
    assert widget.search_button.isEnabled()
