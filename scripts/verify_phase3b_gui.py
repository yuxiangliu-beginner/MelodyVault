"""Real Windows input, official metadata and explicitly opted-in open MP3 download."""
import argparse,json,os,sqlite3,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt,QTimer,QEventLoop,QPoint
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database,connect
from melodyvault.ui.main_window import MainWindow

RECORDING='56c6eca2-5953-45d2-a7c2-54d6ab5833ef'


def wait(app,predicate,timeout=180):
    app.processEvents()
    if predicate():return
    loop=QEventLoop();timer=QTimer();deadline=QTimer();deadline.setSingleShot(True);expired=[]
    timer.timeout.connect(lambda:loop.quit() if predicate() else None);deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
    timer.start(10);deadline.start(int(timeout*1000));loop.exec();timer.stop();deadline.stop();app.processEvents()
    if expired:raise TimeoutError('Native Phase3B condition timed out')


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-downloads',action='store_true');p.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase3b/native'));args=p.parse_args()
    if not args.execute_downloads:raise SystemExit('Requires --execute-downloads for explicitly licensed QA audio')
    root=args.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);path=root/'qa.sqlite3'
    if path.exists():raise SystemExit('New report directory required; existing data not overwritten')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(path) as dst:src.backup(dst)
    initialize_database(path);app=QApplication([]);app.setQuitOnLastWindowClosed(False);assert app.platformName()=='windows'
    report={'platform':'windows'};ticks=[];previous=[time.perf_counter()]
    def tick():now=time.perf_counter();ticks.append(now-previous[0]);previous[0]=now
    timer=QTimer();timer.setInterval(20);timer.timeout.connect(tick);timer.start()
    def save():
        report.update(ui_ticks=len(ticks),max_ui_gap_seconds=max(ticks,default=0));(root/'native-gui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def text(field,value):field.clear();field.setFocus();e=QInputMethodEvent();e.setCommitString(value);QApplication.sendEvent(field,e);assert field.text()==value
    window=MainWindow(path);window.show();app.processEvents()
    try:
        settings=window.download_settings;window.tabs.setCurrentWidget(settings);app.processEvents()
        assert not settings.automatic.isChecked()
        settings.directory.setText(str(root/'music'));settings.speed.setValue(128);QTest.mouseClick(settings.save_button,Qt.MouseButton.LeftButton)
        assert not window.download_page.repository.settings().automatic_download
        window.tabs.setCurrentIndex(0);window.search_mode.setCurrentIndex(window.search_mode.findData('song'));text(window.artist_filter,'Kevin MacLeod');text(window.artist_input,'Silent Night');QTest.keyClick(window.artist_input,Qt.Key.Key_Return)
        wait(app,lambda:not window._requests_running() and window.search_worker is None and window.unified_results.result is not None);result=window.unified_results.result
        assert result and any(c.recording_mbid==RECORDING for c in result.songs)
        group=window.unified_results.tree.topLevelItem(1)
        item=next(group.child(i) for i in range(group.childCount()) if group.child(i).data(0,Qt.ItemDataRole.UserRole)[1].recording_mbid==RECORDING)
        window.unified_results.tree.setCurrentItem(item);QTest.mouseClick(window.unified_results.song_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._requests_running() and window.search_worker is None and window.source_page.worker is None and window.source_page.last_stats is not None and window.source_page.last_stats['searched']==1)
        report['source_stats']=window.source_page.last_stats;report['selected_recording']=window.last_result.summary['selected_recording_mbid'];save()
        index=next(i for i,c in enumerate(window.source_page.candidates) if c['provider']=='commons' and '.mp3' in c.get('audio_url',''))
        window.source_page.table.selectRow(index);QTest.mouseClick(window.source_page.download_button,Qt.MouseButton.LeftButton)
        page=window.download_page;wait(app,lambda:page.worker is None);QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton);wait(app,lambda:page.worker is None)
        dry=page.repository.rows()[0];assert dry['state']=='READY' and dry['dry_run'] and not (root/'music').exists()
        report['dry_run']={'state':dry['state'],'reason':dry['reason'],'audio_created':False};assert window.grab().save(str(root/'dry-run-native.png'));save()
        # Native click on the actual checkbox indicator, then Save.
        window.tabs.setCurrentWidget(settings);app.processEvents();QTest.mouseClick(settings.automatic,Qt.MouseButton.LeftButton,pos=QPoint(8,settings.automatic.height()//2));QTest.mouseClick(settings.save_button,Qt.MouseButton.LeftButton)
        assert page.repository.settings().automatic_download
        window.tabs.setCurrentWidget(window.source_page);window.source_page.table.selectRow(index);QTest.mouseClick(window.source_page.download_button,Qt.MouseButton.LeftButton);wait(app,lambda:page.worker is None)
        jid=next(r['id'] for r in page.repository.rows() if not r['dry_run']);started=time.perf_counter();QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:page.repository.get(jid)['bytes_received']>=128*1024 and page.repository.get(jid)['state']=='DOWNLOADING')
        page.refresh();row=next(i for i in range(page.table.rowCount()) if page.table.item(i,0).data(Qt.ItemDataRole.UserRole)==jid);page.table.selectRow(row);QTest.mouseClick(page.pause_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:page.worker is None);paused=page.repository.get(jid);assert paused['state']=='PAUSED'
        report['paused']={k:paused[k] for k in ('bytes_received','total_bytes','etag','state')};assert window.grab().save(str(root/'paused-native.png'));save()
        window.close();window.deleteLater();app.processEvents()
        # Recreate native window, no automatic queue execution.
        window=MainWindow(path);window.show();app.processEvents();page=window.download_page
        assert page.repository.get(jid)['state']=='PAUSED' and page.worker is None
        window.tabs.setCurrentWidget(window.download_settings);window.download_settings.speed.setValue(0);QTest.mouseClick(window.download_settings.save_button,Qt.MouseButton.LeftButton)
        window.tabs.setCurrentWidget(page);page.refresh();row=next(i for i in range(page.table.rowCount()) if page.table.item(i,0).data(Qt.ItemDataRole.UserRole)==jid);page.table.selectRow(row)
        QTest.mouseClick(page.resume_button,Qt.MouseButton.LeftButton);wait(app,lambda:page.worker is None)
        complete=page.repository.get(jid);report['completed']=complete;report['total_seconds']=time.perf_counter()-started;report['resume_events']=[e for e in page.repository.evidence_rows(jid) if e['step']=='resume'];save()
        assert complete['state']=='COMPLETED',complete['reason']
        page.refresh();page.table.selectRow(row);QTest.mouseClick(page.evidence_button,Qt.MouseButton.LeftButton)
        assert 'LICENSE_VERIFIED' in page.details.toPlainText() and complete['result']['sha256'] in page.details.toPlainText()
        assert window.grab().save(str(root/'completed-native.png'))
        assert report['resume_events'] and any(e['decision']=='RANGE_ACCEPTED' for e in report['resume_events'])
        # Original music/recording and review rows remain; QA has one genuinely
        # imported public MusicBrainz recording, no production changes.
        with connect(path) as db:report['qa_recordings']=db.execute('SELECT count(*) FROM catalog_recordings').fetchone()[0]
        report['success']=True;save();print('NATIVE_PHASE3B_OK',complete['result'],flush=True)
    finally:
        timer.stop();window.close();wait(app,lambda:window.download_page.worker is None and not window._requests_running() and window.source_page.worker is None);window.close();app.processEvents();save()


if __name__=='__main__':main()
