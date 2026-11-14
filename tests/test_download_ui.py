"""Real Qt controls, mock HTTP audio, synthetic WAV. No real artist/network claims."""
import json
from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QTimer,QEventLoop,QThread,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.ui.main_window import MainWindow
from test_downloads import setup,audio,manager,opt_in,queue,good


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def wait(app,predicate):
    if predicate():app.processEvents();return
    loop=QEventLoop();timer=QTimer();deadline=QTimer();expired=[];deadline.setSingleShot(True)
    timer.timeout.connect(lambda:loop.quit() if predicate() else None);deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
    timer.start(10);deadline.start(30000);loop.exec();timer.stop();deadline.stop();app.processEvents();assert not expired


def test_settings_default_off_save_opt_in_and_dry_run_never_completed(app,setup,audio):
    repo,settings,*_=setup;window=MainWindow(repo.path);window.show();page=window.download_page
    page.manager=manager(setup,lambda req:good(audio,req));jid=queue(setup)
    try:
        assert not window.download_settings.automatic.isChecked() and window.tabs.count()==5
        window.tabs.setCurrentWidget(page);QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:page.worker is None);page.refresh()
        assert repo.get(jid)['state']=='READY' and repo.summary()['COMPLETED']==0
        assert 'dry-run' in page.table.item(0,3).text() and not Path(settings.directory).exists()
        window.tabs.setCurrentWidget(window.download_settings)
        app.processEvents();box=window.download_settings.automatic
        QTest.mouseClick(box,Qt.MouseButton.LeftButton,pos=QPoint(8,box.height()//2));QTest.mouseClick(window.download_settings.save_button,Qt.MouseButton.LeftButton)
        assert repo.settings().automatic_download
        # Enabling does not silently convert an old dry-run job to actual download.
        page.start();wait(app,lambda:page.worker is None);assert repo.get(jid)['state']=='READY'
    finally:window.close();app.processEvents()


def test_download_ui_responsive_evidence_folder_and_completion(app,setup,audio,monkeypatch):
    settings=opt_in(setup);repo=setup[0];window=MainWindow(repo.path);page=window.download_page
    page.manager=manager(setup,lambda req:good(audio,req));jid=queue(setup);window.show();window.tabs.setCurrentWidget(page)
    ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(True));timer.start()
    threads=[];original=page._finished
    # Signal callbacks are bound QWidget methods, delivered on the main Qt thread.
    page.workers_finished.connect(lambda:threads.append(QThread.currentThread()))
    try:
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton);wait(app,lambda:page.worker is None)
        page.refresh();assert repo.get(jid)['state']=='COMPLETED' and ticks and threads[0]==window.thread()
        page.table.selectRow(0);QTest.mouseClick(page.evidence_button,Qt.MouseButton.LeftButton)
        assert 'LICENSE_VERIFIED' in page.details.toPlainText() and 'sha256' in page.details.toPlainText()
        assert page.table.item(0,4).text()=='100.0%'
        from melodyvault.ui import download_page
        opened=[];monkeypatch.setattr(download_page.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()) or True)
        QTest.mouseClick(page.folder_button,Qt.MouseButton.LeftButton);assert [Path(p) for p in opened]==[Path(settings.directory)]
    finally:timer.stop();window.close();app.processEvents()


def test_settings_write_failure_is_not_reported_as_saved(app,setup,monkeypatch):
    import sqlite3
    window=MainWindow(setup[0].path);page=window.download_settings;window.show();window.tabs.setCurrentWidget(page);app.processEvents()
    def fail(settings):raise sqlite3.OperationalError('fault-injected full disk')
    monkeypatch.setattr(page.repository,'save_settings',fail)
    page.automatic.setChecked(True);QTest.mouseClick(page.save_button,Qt.MouseButton.LeftButton)
    assert '设置未保存' in page.message.text() and not setup[0].settings().automatic_download
    window.close();app.processEvents()
