"""Qt interaction with an injected pipeline; no claim of real network I/O."""
import time
from PySide6.QtCore import QThread,Signal,Qt
from PySide6.QtTest import QTest
from test_unified_ui import app,widget,library,wait
from test_review import review_data


def test_one_click_keeps_ambiguous_recordings_for_user_choice(app,widget,monkeypatch):
    from melodyvault.search import pipeline_worker as module
    class Stub(QThread):
        progress=Signal(object);completed=Signal(object);failed=Signal(str)
        def __init__(self,path,artist,song,parent=None,dry_run=False):super().__init__(parent)
        def cancel(self):pass
        def run(self):
            time.sleep(.25);self.completed.emit({'status':'NO_SOURCE','attempts':[]})
    monkeypatch.setattr(module,'PipelineWorker',Stub)
    widget.artist_input.setText('晴天')
    QTest.mouseClick(widget.pipeline_button,Qt.MouseButton.LeftButton)
    wait(app,lambda:not widget._requests_running() and widget.search_worker is None)
    assert widget.unified_results.result is not None and widget.last_result is None
    assert widget.pipeline_worker is None
    tree=widget.unified_results.tree;tree.setCurrentItem(tree.topLevelItem(1).child(0))
    QTest.mouseClick(widget.unified_results.song_button,Qt.MouseButton.LeftButton)
    wait(app,lambda:widget.pipeline_worker is not None)
    assert not widget.search_button.isEnabled() and not widget.clear_button.isEnabled()
    wait(app,lambda:not widget._requests_running() and widget.search_worker is None and widget.pipeline_worker is None)
    assert '没有找到候选' in widget.progress_label.text()
    assert widget.pipeline_button.isEnabled()


def test_batch_only_runs_selected_recordings_and_preserves_versions(app,widget,review_data,monkeypatch):
    from test_review import find
    from melodyvault.search import pipeline_worker as module
    repo,artist,records,service=review_data;snapshot=service.load(artist)
    merged=service.decide(artist,'merge',find(snapshot,records[1].mbid).id,find(snapshot,records[0].mbid).id,'测试录音版本')
    captured=[]
    class StubBatch(QThread):
        progress=Signal(object);completed=Signal(object);failed=Signal(str)
        def __init__(self,path,artist,selections,parent=None,dry_run=False):
            super().__init__(parent);captured.extend(selections)
        def cancel(self):pass
        def run(self):self.completed.emit({'status':'BATCH_COMPLETED','results':[{'status':'NO_SOURCE'}]*len(captured),'total':len(captured),'attempts':[]})
    monkeypatch.setattr(module,'BatchPipelineWorker',StubBatch)
    # Use this fixture's own library; the window's database must match it.
    from melodyvault.ui.main_window import MainWindow
    window=MainWindow(repo.path);window.show()
    try:
        window._on_completed(merged['result']);window._set_busy(False)
        tree=window.song_table;parent=next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).childCount()==2)
        parent.setExpanded(True);parent.child(0).setSelected(True);parent.child(1).setSelected(True)
        QTest.mouseClick(window.pipeline_selected_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:window.pipeline_worker is None)
        assert len(captured)==2 and len({song.recordings[0].mbid for song,explicit in captured})==2
        assert all(explicit and len(song.recordings)==1 for song,explicit in captured)
        assert '下载完成 0' in window.progress_label.text()
    finally:window.close();app.processEvents()
