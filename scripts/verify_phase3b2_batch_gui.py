"""Native Windows multi-selection integration using an isolated dry-run DB."""
import argparse,json,os,sqlite3,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database,connect
from melodyvault.ui.main_window import MainWindow
from verify_phase3b2_gui import wait


def main():
    p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args()
    root=a.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);db=root/'qa.sqlite3'
    if db.exists():raise SystemExit('Use a new report directory')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(db) as dst:src.backup(dst)
    initialize_database(db);app=QApplication([]);app.setQuitOnLastWindowClosed(False);assert app.platformName()=='windows'
    window=MainWindow(db);window.show();app.processEvents();report={'platform':'windows','dry_run':True}
    try:
        window.local_only.setChecked(True);window.pipeline_dry_run.setChecked(True);window.artist_input.setFocus()
        event=QInputMethodEvent();event.setCommitString('周杰伦');QApplication.sendEvent(window.artist_input,event)
        QTest.mouseClick(window.pipeline_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._requests_running() and window.worker is None and window.last_result is not None)
        songs={s.id:s for s in window.last_result.songs};chosen=[]
        for i in range(window.song_table.topLevelItemCount()):
            item=window.song_table.topLevelItem(i);song=songs[item.data(0,Qt.ItemDataRole.UserRole)['song_id']]
            if song.primary_recording_mbid and not song.pending_confirmation:
                item.setSelected(True);chosen.append(song.title)
                if len(chosen)==2:break
        if len(chosen)!=2:raise AssertionError('Two verified songs were not found')
        QTest.mouseClick(window.pipeline_selected_button,Qt.MouseButton.LeftButton)
        def done():
            with connect(db) as c:count=c.execute("SELECT count(*) FROM pipeline_sessions WHERE status!='running'").fetchone()[0]
            return count>=2 and window.pipeline_worker is None
        wait(app,done)
        with connect(db) as c:rows=[dict(r) for r in c.execute('SELECT status,query_json FROM pipeline_sessions ORDER BY started_at')]
        report.update(selected_titles=chosen,sessions=[{'status':r['status'],'title':json.loads(r['query_json'])['title']} for r in rows],
                      label=window.progress_label.text())
        assert len(rows)==2 and all(r['status']!='COMPLETED' for r in rows)
        assert window.grab().save(str(root/'batch-native.png'));report['success']=True
        print('NATIVE_BATCH_OK',len(rows),report['label'],flush=True)
    finally:
        window.close();wait(app,lambda:window.pipeline_worker is None and not window._requests_running());window.close()
        (root/'batch-native.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
