"""Real native Windows widgets + real saved/API metadata, no fixture providers."""
import os,json,time,argparse
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt,QTimer,QEventLoop
from PySide6.QtGui import QInputMethodEvent,QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu
from melodyvault.database import initialize_database,connect
from melodyvault.catalog.normalize import title_key
from melodyvault.database.catalog import CatalogRepository
from melodyvault.ui.main_window import MainWindow


def wait(app,predicate,timeout=180):
    if predicate():app.processEvents();return
    # A nested Qt event loop releases the GIL like normal app.exec(). Repeated
    # QTest.qWait in a Python loop can starve the Python worker being measured.
    loop=QEventLoop();timer=QTimer();deadline=QTimer();deadline.setSingleShot(True);timed_out=[]
    def check():
        if predicate():loop.quit()
    def expire():timed_out.append(True);loop.quit()
    timer.timeout.connect(check);deadline.timeout.connect(expire)
    timer.start(10);deadline.start(int(timeout*1000));loop.exec();timer.stop();deadline.stop();app.processEvents()
    if timed_out:raise TimeoutError('Native Phase 2 condition timed out')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase2'));args=parser.parse_args()
    root=args.report_dir;root.mkdir(parents=True,exist_ok=True)
    database=Path('.local/runtime/database/melodyvault.sqlite3');initialize_database(database)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);assert app.platformName()=='windows'
    reports=[]
    for name,title in [('周杰伦','晴天'),('林俊杰','江南'),('周传雄','黄昏')]:
        window=MainWindow(database);window.resize(1280,900);window.show();app.processEvents()
        heartbeats=[];last=[time.perf_counter()]
        def tick():
            now=time.perf_counter();heartbeats.append(now-last[0]);last[0]=now
        timer=QTimer();timer.setInterval(20);timer.timeout.connect(tick);timer.start()
        report={'artist':name,'platform':'windows'}
        try:
            before={r.mbid for r in CatalogRepository(database).recordings(CatalogRepository(database).resolved_artist(name).mbid)}
            event=QInputMethodEvent();event.setCommitString(name);window.artist_input.setFocus();QApplication.sendEvent(window.artist_input,event)
            started=time.perf_counter();QTest.mouseClick(window.search_button,Qt.MouseButton.LeftButton)
            assert not window.search_button.isEnabled()
            wait(app,lambda:window.worker is None)
            report.update(local_display_seconds=time.perf_counter()-started,catalog_summary=window.last_result.summary)
            assert window.last_result.summary['api_requests']==0 and window.song_table.topLevelItemCount()==len(window.last_result.songs)
            target=next(s for s in window.last_result.songs if title_key(s.title)==title_key(title))
            item=next(window.song_table.topLevelItem(i) for i in range(window.song_table.topLevelItemCount()) if window.song_table.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole)['song_id']==target.id)
            window.song_table.setCurrentItem(item);window.song_table.scrollToItem(item);app.processEvents()
            point=window.song_table.visualItemRect(item).center()
            def choose():
                menu=QApplication.activePopupWidget()
                assert isinstance(menu,QMenu)
                QTest.mouseClick(menu,Qt.MouseButton.LeftButton,pos=menu.actionGeometry(menu.actions()[0]).center())
            QTimer.singleShot(25,choose)
            context=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,point,window.song_table.viewport().mapToGlobal(point))
            QApplication.sendEvent(window.song_table.viewport(),context)
            assert window.source_page.worker is not None
            wait(app,lambda:window.source_page.worker is None)
            report['single_search']=window.source_page.last_stats
            assert report['single_search']['total']==1 and report['single_search']['searched']==1
            report['context_menu_search_verified']=True
            QTest.mouseClick(window.source_page.five_button,Qt.MouseButton.LeftButton)
            wait(app,lambda:window.source_page.worker is None)
            assert window.source_page.last_stats['total']==5 and window.source_page.progress_bar.value()==5
            report['batch_five']=window.source_page.last_stats
            if name=='周杰伦':
                row=next(i for i,c in enumerate(window.source_page.candidates) if c['target_title']==target.title)
                window.source_page.table.selectRow(row);app.processEvents()
                assert 'LICENSE_UNVERIFIED' in window.source_page.details.toPlainText()
                QTest.mouseClick(window.source_page.inspect_button,Qt.MouseButton.LeftButton)
                inspections=[];window.source_page.browser_worker.completed.connect(inspections.append)
                wait(app,lambda:window.source_page.browser_worker is None)
                assert inspections and inspections[0]['chrome_version'],window.source_page.status_label.text()
                assert 'LICENSE_UNVERIFIED' in window.source_page.details.toPlainText()
                report['candidate_chrome_inspection_verified']=True
            assert window.grab().save(str(root/(name+'-sources-native.png')))
            if name=='周传雄':
                window.tabs.setCurrentIndex(0);window.evidence_force.setChecked(True)
                def cancel_after_real_page(message):
                    if '录音作品关系：' in message and window.evidence_worker:
                        QTest.mouseClick(window.evidence_cancel,Qt.MouseButton.LeftButton)
                QTest.mouseClick(window.evidence_button,Qt.MouseButton.LeftButton)
                worker=window.evidence_worker;worker.progress.connect(cancel_after_real_page)
                assert worker.priority()==worker.Priority.LowPriority
                assert window.search_button.isEnabled() and window.source_page.five_button.isEnabled()
                wait(app,lambda:window.evidence_worker is None)
                assert worker.cancel_event.is_set() and worker.metrics['api_requests']>0
                report['cancelled_real_evidence']=worker.metrics
                assert '已有歌曲保留' in window.evidence_label.text()
            window.tabs.setCurrentIndex(0);app.processEvents()
            assert {r.mbid for r in window.last_result.recordings}==before
            assert window.grab().save(str(root/(name+'-catalog-native.png')))
            report.update(success=True,ui_heartbeat_ticks=len(heartbeats),max_ui_gap_seconds=max(heartbeats,default=0))
            reports.append(report);(root/'native-gui.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
            print('NATIVE_PHASE2_OK',name,report['local_display_seconds'],len(heartbeats),flush=True)
        finally:
            timer.stop();window.close()
            wait(app,lambda:window.worker is None and window.evidence_worker is None and window.source_page.worker is None and window.source_page.browser_worker is None)
            window.close();app.processEvents()
    return 0


if __name__=='__main__':raise SystemExit(main())
