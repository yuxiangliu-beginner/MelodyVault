"""Three live store searches through the native UI, never media downloads."""
import os,json,sqlite3,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from melodyvault.database import initialize_database
from melodyvault.ui.music_window import MusicWindow
from melodyvault.catalog.normalize import title_key,name_key

root=Path('.local/reports/final-integration/native');root.mkdir(parents=True,exist_ok=True)
db=root/'qa.sqlite3'
if db.exists():raise SystemExit('Use a fresh QA directory')
with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(db) as dst:src.backup(dst)
initialize_database(db);app=QApplication([]);w=MusicWindow(db);w.show();app.processEvents();report=[]
try:
    for artist,title in [('周杰伦','晴天'),('林俊杰','江南'),('周传雄','黄昏')]:
        w.input.setText(artist+' '+title);start=time.perf_counter();QTest.mouseClick(w.search_button,Qt.MouseButton.LeftButton)
        deadline=time.monotonic()+100
        while w.worker is not None and time.monotonic()<deadline:app.processEvents();QTest.qWait(20)
        if w.worker:raise TimeoutError('search did not finish')
        matches=[s for s in w.songs if title_key(s['title'])==title_key(title) and name_key(s['artist'])==name_key(artist)]
        report.append({'query':artist+' '+title,'seconds':time.perf_counter()-start,'candidates':len(w.songs),'exact_metadata_matches':len(matches),'rows':w.songs,'label':w.status.text(),'downloaded':0})
        w.grab().save(str(root/(title+'.png')))
    (root/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print([(r['query'],r['candidates'],r['exact_metadata_matches']) for r in report],flush=True)
finally:
    if w.worker:w.cancel();w.worker.wait(70000)
    w.close();app.processEvents()
