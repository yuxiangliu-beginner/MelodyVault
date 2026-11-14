"""Native Windows input/clicks against an isolated backup of real saved metadata.

No fixture providers, no audio download. Target selections are QA audit events in
the isolated DB, never user confirmations in the production library.
"""
import argparse,json,os,sqlite3,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt,QTimer,QEventLoop
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.database import connect
from melodyvault.ui.main_window import MainWindow
from melodyvault.search.models import identity_key

JAY='a223958d-5c56-4b2c-a30a-87e357bc121b'


def wait(app,predicate,timeout=180):
    if predicate():app.processEvents();return
    loop=QEventLoop();timer=QTimer();deadline=QTimer();deadline.setSingleShot(True);expired=[]
    timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    deadline.timeout.connect(lambda:(expired.append(True),loop.quit()))
    timer.start(10);deadline.start(int(timeout*1000));loop.exec();timer.stop();deadline.stop();app.processEvents()
    if expired:raise TimeoutError('Native Phase 3A condition timed out')


def input_text(app,field,text):
    field.clear();field.setFocus();event=QInputMethodEvent();event.setCommitString(text);QApplication.sendEvent(field,event);app.processEvents()
    assert field.text()==text


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase3a/native'));args=parser.parse_args()
    root=args.report_dir;root.mkdir(parents=True,exist_ok=True);database=root/'qa.sqlite3'
    if database.exists():raise RuntimeError('Use a new report directory; QA database will not be overwritten')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as source,sqlite3.connect(database) as destination:source.backup(destination)
    with connect(database) as db:
        original_songs=[tuple(r) for r in db.execute('SELECT * FROM catalog_songs ORDER BY song_id')]
        original_links=[tuple(r) for r in db.execute('SELECT * FROM catalog_song_recordings ORDER BY song_id,recording_mbid')]
        original_reviews=[tuple(r) for r in db.execute('SELECT * FROM catalog_review_events')]
        original_raw=[tuple(r) for r in db.execute('SELECT mbid,payload_json FROM catalog_recordings ORDER BY mbid')]
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);assert app.platformName()=='windows'
    window=MainWindow(database);window.show();app.processEvents();reports=[];heartbeats=[];last=[time.perf_counter()]
    def tick():
        now=time.perf_counter();heartbeats.append(now-last[0]);last[0]=now
    timer=QTimer();timer.setInterval(20);timer.timeout.connect(tick);timer.start()
    def save():
        (root/'native-gui.json').write_text(json.dumps({'cases':reports,'platform':app.platformName(),'ui_ticks':len(heartbeats),'max_ui_gap_seconds':max(heartbeats,default=0)},ensure_ascii=False,indent=2),encoding='utf-8')
    def search(query,mode='smart',enter=True):
        window.tabs.setCurrentIndex(0);window.search_mode.setCurrentIndex(window.search_mode.findData(mode));input_text(app,window.artist_input,query)
        started=time.perf_counter()
        if enter:QTest.keyClick(window.artist_input,Qt.Key.Key_Return)
        else:QTest.mouseClick(window.search_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._requests_running())
        seconds=time.perf_counter()-started;print('NATIVE_QUERY',query,seconds,flush=True);return seconds
    try:
        assert window.search_mode.currentData()=='smart'
        assert window.artist_input.placeholderText()=='输入歌手名称或歌曲名称…'
        for singer in ('周杰伦','林俊杰','周传雄'):
            seconds=search(singer)
            assert window.last_result is not None,window.progress_label.text()
            assert window.last_result.summary['api_requests']==0
            assert window.song_table.topLevelItemCount()==len(window.last_result.songs)
            reports.append({'query':singer,'mode':'smart','native_seconds':seconds,'catalog':window.last_result.summary,'artist_mbid':window.last_result.artist.mbid})
            save()
        for title in ('晴天','江南'):
            seconds=search(title,'song',False);result=window.unified_results.result
            assert result and len({c.artist.mbid for c in result.songs})>1
            assert window.last_result is None and not window.unified_results.song_button.isEnabled()
            reports.append({'query':title,'mode':'song','native_seconds':seconds,'candidates':len(result.songs),'performers':len({c.artist.mbid for c in result.songs}),'api_requests':result.api_requests,'scope':result.scope,'no_automatic_song_choice':True})
            assert window.grab().save(str(root/(title+'-default-native.png')));save()
        seconds=search('周杰伦','artist');assert window.last_result and window.last_result.artist.mbid==JAY
        reports.append({'query':'周杰伦','mode':'artist','native_seconds':seconds,'catalog':window.last_result.summary});save()
        seconds=search('晴天','smart');result=window.unified_results.result
        assert result and len({c.artist.mbid for c in result.songs})>1 and window.last_result is None
        reports.append({'query':'晴天','mode':'smart','native_seconds':seconds,'artists':len(result.artists),'candidates':len(result.songs),'performers':len({c.artist.mbid for c in result.songs}),'api_requests':result.api_requests,'errors':result.errors});save()
        assert window.grab().save(str(root/'smart-title-native.png'))
        seconds=search('周杰伦 晴天');result=window.unified_results.result
        assert result and any(c.artist.mbid==JAY for c in result.songs)
        reports.append({'query':'周杰伦 晴天','native_seconds':seconds,'candidates':len(result.songs),'api_requests':result.api_requests});save()
        # Click a precise recording candidate, not a title-only default.
        def select_jay_studio():
            group=window.unified_results.tree.topLevelItem(1)
            for i in range(group.childCount()):
                item=group.child(i);candidate=item.data(0,Qt.ItemDataRole.UserRole)[1]
                if candidate.artist.mbid==JAY and identity_key(candidate.title)==identity_key('晴天') and candidate.version=='studio':
                    window.unified_results.tree.setCurrentItem(item);window.unified_results.tree.scrollToItem(item);app.processEvents()
                    QTest.mouseClick(window.unified_results.song_button,Qt.MouseButton.LeftButton)
                    wait(app,lambda:not window._requests_running() and window.source_page.worker is None)
                    assert window.last_result and len(window.last_result.recordings)==1
                    assert window.source_page.last_stats['total']==1
                    return candidate.recording_mbid,dict(window.source_page.last_stats)
            raise AssertionError('No evidence-backed studio candidate')
        selected,stats=select_jay_studio();reports.append({'selected_recording_mbid':selected,'single_sources':stats});save()
        assert window.grab().save(str(root/'selected-sources-native.png'))
        search('周杰伦 晴天');again,reused=select_jay_studio()
        assert again==selected and reused['api_requests']==0
        reports.append({'same_recording_source_cache':reused});save()
        seconds=search('Jay Chou Qing Tian');result=window.unified_results.result
        assert result and result.songs and all(c.pending_confirmation for c in result.songs)
        reports.append({'query':'Jay Chou Qing Tian','native_seconds':seconds,'candidates':len(result.songs),'pending':sum(c.pending_confirmation for c in result.songs),'official_english_alias_confirmed':False,'api_requests':result.api_requests});save()
        assert window.grab().save(str(root/'pinyin-pending-native.png'))
        # Forced fresh real metadata request; cancel from native button once a
        # local partial has appeared and the online request can be in flight.
        input_text(app,window.artist_input,'晴天');window.search_mode.setCurrentIndex(window.search_mode.findData('song'))
        window.refresh_checkbox.setChecked(True);QTest.mouseClick(window.search_button,Qt.MouseButton.LeftButton);worker=window.search_worker
        wait(app,lambda:window.unified_results.result is not None and bool(window.unified_results.result.songs))
        QTest.mouseClick(window.cancel_button,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._requests_running());assert worker.metrics['cancelled']
        reports.append({'cancelled_real_search':worker.metrics,'visible_status':window.progress_label.text()});save();window.refresh_checkbox.setChecked(False)
        QTest.mouseClick(window.clear_button,Qt.MouseButton.LeftButton)
        assert not window.artist_input.text() and window.song_table.topLevelItemCount()==0 and window.unified_results.tree.topLevelItemCount()==0
        with connect(database) as db:
            assert [tuple(r) for r in db.execute('SELECT * FROM catalog_songs ORDER BY song_id')]==original_songs
            assert [tuple(r) for r in db.execute('SELECT * FROM catalog_song_recordings ORDER BY song_id,recording_mbid')]==original_links
            assert [tuple(r) for r in db.execute('SELECT * FROM catalog_review_events')]==original_reviews
            assert [tuple(r) for r in db.execute('SELECT mbid,payload_json FROM catalog_recordings ORDER BY mbid')]==original_raw
            count=db.execute('SELECT count(*) FROM unified_confirmations').fetchone()[0]
        reports.append({'clear_verified':True,'original_grouping_and_review_history_unchanged':True,'qa_target_selection_events':count});save()
        print('NATIVE_PHASE3A_OK',len(reports),'cases',flush=True)
    finally:
        timer.stop();window.close();wait(app,lambda:not window._requests_running() and window.source_page.worker is None);window.close();app.processEvents();save()


if __name__=='__main__':main()
