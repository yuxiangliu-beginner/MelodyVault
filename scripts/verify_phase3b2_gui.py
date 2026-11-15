"""Native Qt event-loop integration with real SQLite and public sources.

This QA copy keeps the normal dry-run setting and never claims a download.
"""
import argparse,json,os,sqlite3,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt,QTimer,QEventLoop
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database,connect
from melodyvault.ui.main_window import MainWindow


def wait(app,predicate,timeout=180000):
    app.processEvents()
    if predicate():return
    loop=QEventLoop();timer=QTimer();deadline=QTimer();deadline.setSingleShot(True);expired=[]
    timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
    timer.start(10);deadline.start(timeout);loop.exec();timer.stop();deadline.stop();app.processEvents()
    if expired:raise TimeoutError('native GUI task timed out')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True)
    p.add_argument('--authorized-english-control',action='store_true')
    p.add_argument('--cancel-after-start',action='store_true');a=p.parse_args()
    root=a.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);db=root/'qa.sqlite3'
    if db.exists():raise SystemExit('Use a new QA directory')
    seed='.local/reports/phase3b1/authorized-control/qa.sqlite3' if a.authorized_english_control else '.local/runtime/database/melodyvault.sqlite3'
    with sqlite3.connect(seed) as src,sqlite3.connect(db) as dst:src.backup(dst)
    if a.authorized_english_control:
        with sqlite3.connect(db) as c:c.execute('DELETE FROM downloaded_files')
    initialize_database(db);app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    assert app.platformName()=='windows';window=MainWindow(db);window.show();app.processEvents()
    ticks=[];last=[time.perf_counter()]
    def tick():
        now=time.perf_counter();ticks.append(now-last[0]);last[0]=now
    heartbeat=QTimer();heartbeat.setInterval(25);heartbeat.timeout.connect(tick);heartbeat.start()
    if a.authorized_english_control:
        settings=window.download_page.repository.settings();settings.automatic_download=True;settings.directory=str(root/'music')
        window.download_page.repository.save_settings(settings)
    window.pipeline_dry_run.setChecked(not a.authorized_english_control)
    report={'platform':'windows','dry_run':window.pipeline_dry_run.isChecked(),
            'language':'English control' if a.authorized_english_control else 'Chinese'}
    try:
        assert report['dry_run'] != a.authorized_english_control
        query='Kevin MacLeod Silent Night' if a.authorized_english_control else '周杰伦 晴天'
        artist='Kevin MacLeod' if a.authorized_english_control else '周杰伦'
        window.local_only.setChecked(True);window.artist_input.setFocus();e=QInputMethodEvent();e.setCommitString(query);QApplication.sendEvent(window.artist_input,e)
        assert window.artist_input.text()==query
        QTest.mouseClick(window.pipeline_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._requests_running() and window.search_worker is None and window.unified_results.result is not None)
        result=window.unified_results.result
        with connect(db) as c:session_exists=bool(c.execute('SELECT 1 FROM pipeline_sessions LIMIT 1').fetchone())
        manual_selection=False
        if window.pipeline_worker is None and not session_exists:
            tree=window.unified_results.tree;group=tree.topLevelItem(1)
            candidates=[group.child(i) for i in range(group.childCount())]
            selected=next((v for v in candidates if v.data(0,Qt.ItemDataRole.UserRole)[1].artist.matches(artist)),None)
            if selected is None:raise AssertionError('No requested artist recording in real local search')
            tree.setCurrentItem(selected);QTest.mouseClick(window.unified_results.song_button,Qt.MouseButton.LeftButton)
            manual_selection=True
        if a.cancel_after_start:
            wait(app,lambda:window.pipeline_worker is not None)
            QTest.mouseClick(window.cancel_button,Qt.MouseButton.LeftButton)
            report['cancel_requested']=True
        def complete():
            with connect(db) as c:row=c.execute('SELECT status,result_json FROM pipeline_sessions ORDER BY started_at DESC LIMIT 1').fetchone()
            return bool(row and row['status']!='running' and window.pipeline_worker is None and not window._requests_running())
        wait(app,complete)
        with connect(db) as c:
            row=c.execute('SELECT status,result_json FROM pipeline_sessions ORDER BY started_at DESC LIMIT 1').fetchone()
            report['session_status']=row['status'];report['session']=json.loads(row['result_json'])
        report['label']=window.progress_label.text();report['heartbeat_count']=len(ticks);report['max_ui_gap_seconds']=max(ticks,default=0)
        report['explicit_selection_used']=manual_selection
        if a.cancel_after_start:assert report['session_status']=='CANCELLED',report['session']
        elif report['dry_run']:assert report['session_status']!='COMPLETED','dry-run must never count as actual download'
        else:assert report['session_status']=='COMPLETED',report['session']
        assert window.grab().save(str(root/'native.png'))
        report['success']=True
        print('NATIVE_GUI_PIPELINE',report['session_status'],'ticks',len(ticks),flush=True)
    finally:
        window.close();wait(app,lambda:window.pipeline_worker is None and not window._requests_running());window.close();heartbeat.stop()
        (root/'native.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
