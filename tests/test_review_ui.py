import pytest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.ui.review_dialog import ReviewDialog
from test_review import review_data,find
from test_catalog_ui import wait_until


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app,review_data):
    repo,artist,records,service=review_data
    widget=ReviewDialog(repo.path,artist,actor='qa_automation');widget.show()
    wait_until(app,lambda:widget.snapshot is not None and widget.worker is None)
    yield widget,records
    if widget.worker:wait_until(app,lambda:widget.worker is None)
    widget.close();app.processEvents()


def select_pair(widget,source_mbid,target_mbid):
    target=find(widget.snapshot,target_mbid)
    row=next(i for i,s in enumerate(widget.sources) if source_mbid in {r.mbid for r in s.recordings})
    widget.source_table.selectRow(row);widget._select_source()
    index=next(i for i,c in enumerate(widget.candidates) if c['target_song_id']==target.id)
    widget.candidate_table.selectRow(index);widget._select_candidate()


@pytest.mark.gui
def test_review_merge_undo_real_widgets_threads_and_audit(app,dialog):
    widget,records=dialog
    select_pair(widget,records[1].mbid,records[0].mbid)
    assert '低' in widget._candidate()['confidence']
    assert '演唱者' in widget.details.toPlainText()
    widget.reason_input.setText('GUI测试人工确认，不用于生产目录')
    QTest.mouseClick(widget.merge_button,Qt.MouseButton.LeftButton)
    assert not widget.merge_button.isEnabled()
    wait_until(app,lambda:widget.worker is None)
    assert len(find(widget.snapshot,records[0].mbid).recordings)==2
    assert widget.snapshot['result'].summary['manually_reviewed_item_count']==1
    widget.tabs.setCurrentIndex(1);widget.history_table.selectRow(0)
    assert widget.undo_button.isEnabled()
    QTest.mouseClick(widget.undo_button,Qt.MouseButton.LeftButton)
    wait_until(app,lambda:widget.worker is None)
    assert len(widget.snapshot['events'])==2
    assert find(widget.snapshot,records[1].mbid).pending_confirmation


@pytest.mark.gui
def test_review_reject_independent_and_reason_error(app,dialog):
    widget,records=dialog
    select_pair(widget,records[1].mbid,records[0].mbid)
    QTest.mouseClick(widget.reject_button,Qt.MouseButton.LeftButton)
    wait_until(app,lambda:widget.worker is None)
    assert '理由' in widget.status_label.text()
    assert not widget.snapshot['events']
    widget.reason_input.setText('同名不构成证据，拒绝建议')
    QTest.mouseClick(widget.reject_button,Qt.MouseButton.LeftButton)
    wait_until(app,lambda:widget.worker is None)
    assert find(widget.snapshot,records[1].mbid).review_action=='reject'
    select_pair(widget,records[1].mbid,records[0].mbid)
    widget.reason_input.setText('人工决定保持独立')
    QTest.mouseClick(widget.independent_button,Qt.MouseButton.LeftButton)
    wait_until(app,lambda:widget.worker is None)
    assert not find(widget.snapshot,records[1].mbid).pending_confirmation
    assert widget.history_table.rowCount()==2


@pytest.mark.gui
def test_review_escape_waits_for_worker_shutdown(app,review_data):
    repo,artist,records,service=review_data
    widget=ReviewDialog(repo.path,artist,actor='qa_automation');widget.show()
    app.processEvents()
    QTest.keyClick(widget,Qt.Key.Key_Escape)
    if widget.worker:wait_until(app,lambda:widget.worker is None)
    assert not widget.isVisible()
