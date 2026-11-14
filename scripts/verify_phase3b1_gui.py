"""Interactive native QA harness; input comes from the real Windows UI.

Heartbeat measures event-loop responsiveness, never task progress. Close the
window to save the report. No production database/settings are modified.
"""
import argparse,json,sqlite3,os,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database
from melodyvault.ui.main_window import MainWindow


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase3b1/native'))
    parser.add_argument('--automated',action='store_true',help='Run Qt native integration inputs inside this QA application')
    args=parser.parse_args();root=args.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);path=root/'qa.sqlite3'
    if path.exists():raise SystemExit('Use a fresh QA report directory')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(path) as dst:src.backup(dst)
    initialize_database(path);app=QApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));assert app.platformName()=='windows'
    window=MainWindow(path);window.setWindowTitle('MelodyVault · Phase 3B.1 QA');window.resize(1180,820)
    report={'platform':app.platformName(),'tabs':[window.tabs.tabText(i) for i in range(window.tabs.count())],
        'automatic_download':window.download_page.repository.settings().automatic_download,'discovery_events':[],
        'status_events':[],'ui_ticks':0,'max_ui_gap_seconds':0}
    last=[time.perf_counter()]
    def tick():
        now=time.perf_counter();gap=now-last[0];report['ui_ticks']+=1;report['max_ui_gap_seconds']=max(report['max_ui_gap_seconds'],gap);last[0]=now
        if window.discovery_page.worker is not None:report['discovery_max_ui_gap_seconds']=max(report.get('discovery_max_ui_gap_seconds',0),gap)
        message=window.discovery_page.status.text()
        if not report['status_events'] or report['status_events'][-1]!=message:report['status_events'].append(message)
    def finished():
        report['discovery_events'].append({'status':window.discovery_page.status.text(),'rows':window.discovery_page.repository.rows()})
        save()
    def save():
        report['registry']=window.discovery_page.repository.rows()
        report['local_song_rows']=window.song_table.topLevelItemCount()
        (root/'native-gui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    window.discovery_page.workers_finished.connect(finished)
    timer=QTimer();timer.setInterval(25);timer.timeout.connect(tick);timer.start();window.show();save()
    if args.automated:
        from PySide6.QtCore import Qt,QEventLoop
        from PySide6.QtGui import QInputMethodEvent
        from PySide6.QtTest import QTest
        def wait(predicate,timeout=180000):
            app.processEvents()
            if predicate():return
            loop=QEventLoop();poll=QTimer();deadline=QTimer();expired=[];deadline.setSingleShot(True)
            poll.timeout.connect(lambda:loop.quit() if predicate() else None);deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
            poll.start(10);deadline.start(timeout);loop.exec();poll.stop();deadline.stop();app.processEvents()
            if expired:raise TimeoutError('Native Qt integration condition timed out')
        def text(field,value):
            field.clear();field.setFocus();event=QInputMethodEvent();event.setCommitString(value);QApplication.sendEvent(field,event)
            assert field.text()==value
        try:
            app.processEvents();window.local_only.setChecked(True);window.search_mode.setCurrentIndex(window.search_mode.findData('artist'))
            text(window.artist_input,'周杰伦');start=time.perf_counter();QTest.keyClick(window.artist_input,Qt.Key.Key_Return)
            wait(lambda:not window._requests_running() and window.search_worker is None and window.unified_results.result is not None)
            group=window.unified_results.tree.topLevelItem(0)
            item=next(group.child(i) for i in range(group.childCount()) if group.child(i).data(0,Qt.ItemDataRole.UserRole)[1].matches('周杰伦'))
            window.unified_results.tree.setCurrentItem(item);QTest.mouseClick(window.unified_results.artist_button,Qt.MouseButton.LeftButton)
            wait(lambda:window.worker is None and not window._requests_running() and window.last_result is not None)
            report['local_catalog']={'seconds':time.perf_counter()-start,'rows':window.song_table.topLevelItemCount(),'api_requests':window.last_result.summary['api_requests']}
            assert report['local_catalog']['api_requests']==0 and report['local_catalog']['rows']>0
            page=window.discovery_page;window.tabs.setCurrentWidget(page);app.processEvents()
            text(page.artist,'周杰伦');text(page.title,'晴天');QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
            assert page.worker is not None and not page.start_button.isEnabled()
            wait(lambda:page.worker is None);assert page.table.rowCount()>0
            report['live_discovery_status']=page.status.text();page.table.selectRow(0)
            domain=page.selected()['domain'];QTest.mouseClick(page.disable_button,Qt.MouseButton.LeftButton)
            assert not page.repository.get(domain)['enabled']
            QTest.mouseClick(page.enable_button,Qt.MouseButton.LeftButton);assert page.repository.get(domain)['enabled']
            QTest.mouseClick(page.check_button,Qt.MouseButton.LeftButton);wait(lambda:page.worker is None)
            page.table.selectRow(0);page.details();assert 'manual_disable' in page.detail.toPlainText()
            report['manual_enable_disable_recheck']=True
            assert window.grab().save(str(root/'discovery-native.png'))
            text(page.title,'未命名取消测试');QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
            QTest.mouseClick(page.cancel_button,Qt.MouseButton.LeftButton);wait(lambda:page.worker is None)
            report['cancel_status']=page.status.text();assert '已取消' in page.status.text()
            report['success']=True;save()
            print('NATIVE_QT_PHASE3B1_OK',report['local_catalog'],flush=True)
        finally:
            window.close();wait(lambda:window.discovery_page.worker is None and not window._requests_running() and window.worker is None);window.close();app.processEvents();timer.stop();save()
    else:
        app.exec();timer.stop();save()


if __name__=='__main__':main()
