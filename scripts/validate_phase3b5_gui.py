"""Opt-in real network + Qt click acceptance against an isolated library.

No transport/provider substitutions. Never touches the production database.
"""
import argparse
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.database import initialize_database,connect
from melodyvault.database.downloads import DownloadRepository
from melodyvault.ui.music_window import MusicWindow


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-live',action='store_true')
    parser.add_argument('--directory',type=Path,default=Path('.local/reports/phase-3b5/gui-live'))
    args=parser.parse_args()
    if not args.run_live:raise SystemExit('Requires --run-live: real network downloads, isolated database only')
    root=args.directory.resolve()
    if root.exists():raise SystemExit('Use a new validation directory; existing files preserved')
    root.mkdir(parents=True);db=root/'qa.sqlite3';initialize_database(db)
    repo=DownloadRepository(db)
    repo.save_settings(replace(repo.settings(),directory=str(root/'music'),max_concurrent=1,max_attempts=2,keep_temporary=False))
    app=QApplication.instance() or QApplication([]);w=MusicWindow(db);w.show()
    report={'kind':'Qt clicks with actual production providers and live network, not human desktop clicks',
            'db':str(db),'events':[]}
    def wait_idle(label):
        start=time.monotonic()
        while w.worker is not None and time.monotonic()-start<150:
            app.processEvents();time.sleep(.02)
        if w.worker:raise TimeoutError(label+' timed out')
        report['events'].append({'stage':label,'elapsed':time.monotonic()-start,'status':w.status.text()})
    try:
        w.input.setText('是你');QTest.mouseClick(w.search_button,Qt.MouseButton.LeftButton)
        wait_idle('search')
        report['search_results']=w.songs
        index=next(i for i,s in enumerate(w.songs) if s['source']=='commons' and s['song_id']=='15326761')
        w.grab().save(str(root/'search.png'))
        QTest.mouseClick(w.table.cellWidget(index,3),Qt.MouseButton.LeftButton);wait_idle('download')
        with connect(db) as c:
            rows=[dict(r) for r in c.execute('select * from personal_music')]
            files=[dict(r) for r in c.execute('select * from downloaded_files')]
        assert len(rows)==len(files)==1,repo.rows()
        record=rows[0];path=Path(record['path'])
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        assert json.loads(files[0]['media_json'])['full_decode'] is True
        assert Path(str(path)+'.evidence.json').is_file()
        w.tabs.setCurrentIndex(1);w.refresh_history();QTest.qWait(100)
        assert w.history.topLevelItemCount()==1 and w.history.topLevelItem(0).childCount()==1
        assert w.history.topLevelItem(0).isExpanded()
        assert w.history.topLevelItem(0).child(0).text(0)=='是你'
        w.grab().save(str(root/'library.png'))
        # A second click uses real metadata verification and existing file bytes.
        w.tabs.setCurrentIndex(0)
        QTest.mouseClick(w.table.cellWidget(index,3),Qt.MouseButton.LeftButton);wait_idle('duplicate')
        with connect(db) as c:
            assert c.execute('select count(*) from personal_music').fetchone()[0]==1
            assert c.execute('select count(*) from downloaded_files').fetchone()[0]==1
            jobs=[dict(r) for r in c.execute('select id,state,result_json from download_jobs')]
        assert any(json.loads(r['result_json']).get('reused') for r in jobs)
        report.update(result='PASS',library=record,download_jobs=jobs,
                      audio_files=[str(f) for f in (root/'music').rglob('*.ogg')])
        assert len(report['audio_files'])==1
    except Exception as error:
        report.update(result='FAIL',error=type(error).__name__+': '+str(error))
        raise
    finally:
        (root/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if w.worker:
            w.worker.cancel()
            while w.worker:app.processEvents();time.sleep(.02)
        w.close();app.processEvents()
    print(json.dumps({k:report[k] for k in ['result','events','library','audio_files']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
