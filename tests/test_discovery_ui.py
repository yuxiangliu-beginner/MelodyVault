"""Qt event-loop integration; injected backend results are not live coverage."""
import threading,time,json
import pytest
from PySide6.QtCore import Qt,QTimer,QEventLoop,QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.discovery.models import DiscoveryHit
from melodyvault.discovery.service import SourceDiscoveryService
from melodyvault.ui.main_window import MainWindow


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def wait(app,condition):
    loop=QEventLoop();poll=QTimer();deadline=QTimer();expired=[];deadline.setSingleShot(True)
    poll.timeout.connect(lambda:loop.quit() if condition() else None)
    deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
    poll.start(10);deadline.start(10000)
    if not condition():loop.exec()
    poll.stop();deadline.stop();app.processEvents();assert not expired


def test_discovery_background_cancel_recheck_controls_and_audit(app,tmp_path,monkeypatch):
    path=tmp_path/'app.sqlite3';initialize_database(path);seen=[]
    def discover(service,artist,title,**kwargs):
        seen.append((artist,title,QThread.currentThread()))
        service.progress({'message':'test-only blocking request'})
        for _ in range(10):
            if service.cancel.wait(.01):return {'cancelled':True}
        service.repository.discover(DiscoveryHit('Test site','https://example.org/song',title,'test',{'not_live':True}))
        return {'discovered':1,'not_live':True}
    def check(service,domain,http=None):
        service.repository.verify(domain,{'state':'ACCESSIBLE','automation_allowed':True,'formats':['flac'],'download_permission':'LICENSE_UNVERIFIED'})
        return {'state':'ACCESSIBLE','not_live':True}
    monkeypatch.setattr(SourceDiscoveryService,'discover',discover);monkeypatch.setattr(SourceDiscoveryService,'check',check)
    window=MainWindow(path);window.show();page=window.discovery_page;window.tabs.setCurrentWidget(page);app.processEvents()
    timer=QTimer();ticks=[];timer.timeout.connect(lambda:ticks.append(1));timer.start(5)
    try:
        page.artist.setText('周杰伦');page.title.setText('晴天')
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
        assert page.worker is not None and not page.start_button.isEnabled() and page.cancel_button.isEnabled()
        wait(app,lambda:page.worker is None)
        assert seen[0][:2]==('周杰伦','晴天') and seen[0][2]!=window.thread() and ticks
        assert page.table.rowCount()==1 and 'PENDING_REVIEW' in page.table.item(0,1).text()
        page.table.selectRow(0);QTest.mouseClick(page.disable_button,Qt.MouseButton.LeftButton)
        assert not page.repository.get('example.org')['enabled']
        QTest.mouseClick(page.enable_button,Qt.MouseButton.LeftButton)
        assert page.repository.get('example.org')['enabled'] and page.repository.get('example.org')['review_status']=='PENDING_REVIEW'
        QTest.mouseClick(page.check_button,Qt.MouseButton.LeftButton);wait(app,lambda:page.worker is None)
        page.table.selectRow(0);page.details()
        assert 'manual_disable' in page.detail.toPlainText() and 'flac' in page.detail.toPlainText()
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton);QTest.mouseClick(page.cancel_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:page.worker is None);assert '已取消' in page.status.text() and page.progress.value()==0
        assert not window.download_page.repository.settings().automatic_download and window.tabs.count()==5
    finally:timer.stop();window.close();app.processEvents()


def test_window_close_cancels_discovery_and_waits_for_queued_signals(app,tmp_path,monkeypatch):
    path=tmp_path/'app.sqlite3';initialize_database(path)
    def discover(service,*args,**kwargs):
        service.cancel.wait(2);return {'cancelled':True}
    monkeypatch.setattr(SourceDiscoveryService,'discover',discover)
    window=MainWindow(path);window.show();page=window.discovery_page;page.title.setText('晴天');page.start()
    window.close();assert page.worker is not None
    wait(app,lambda:page.worker is None);app.processEvents();assert not window.isVisible()
