"""Native Windows QA on an isolated SQLite backup, never on the user's audit."""
import argparse,json,os,sqlite3,time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository
from melodyvault.catalog.review import suggestions,recording_set
from melodyvault.ui.review_dialog import ReviewDialog


def wait(app,predicate,timeout=90):
    end=time.monotonic()+timeout
    while not predicate():
        app.processEvents();QTest.qWait(10)
        if time.monotonic()>end:raise TimeoutError('Native review GUI condition timed out')
    app.processEvents()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    copied=args.output/'isolated-review.sqlite3'
    if copied.exists():raise SystemExit('Use a fresh output directory; never overwrite existing QA audit')
    with sqlite3.connect(args.database) as source,sqlite3.connect(copied) as target:source.backup(target)
    initialize_database(copied)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    assert app.platformName()=='windows'
    repo=CatalogRepository(copied);reports=[]
    for name in ('林俊杰','周杰伦'):
        artist=repo.resolved_artist(name)
        widget=ReviewDialog(copied,artist,actor='qa_automation');widget.show()
        try:
            wait(app,lambda:widget.worker is None and widget.snapshot is not None)
            original={r.mbid for r in widget.snapshot['result'].recordings}
            pair=None
            for source in widget.sources:
                if not source.pending_confirmation:continue
                for candidate in suggestions(artist,source,widget.snapshot['result'].songs,widget.snapshot['works']):
                    target=next(s for s in widget.snapshot['result'].songs if s.id==candidate['target_song_id'])
                    if candidate['allowed'] and not target.pending_confirmation:
                        pair=(source,target);break
                if pair:break
            assert pair,'No allowed real review candidate; cannot fabricate one'
            source,target=pair;source_ids=recording_set(source);target_ids=recording_set(target)
            def select_pair():
                row=next(i for i,s in enumerate(widget.sources) if source_ids<=recording_set(s))
                widget.source_table.selectRow(row);widget._select_source()
                target_song=next(s for s in widget.snapshot['result'].songs if target_ids<=recording_set(s))
                index=next(i for i,c in enumerate(widget.candidates) if c['target_song_id']==target_song.id)
                widget.candidate_table.selectRow(index);widget._select_candidate();app.processEvents()
            def click(button):
                assert button.isEnabled();QTest.mouseClick(button,Qt.MouseButton.LeftButton)
                wait(app,lambda:widget.worker is None)
            def undo(event_id):
                widget.tabs.setCurrentIndex(1)
                row=next(i for i,e in enumerate(widget._history) if e['id']==event_id)
                widget.history_table.selectRow(row);app.processEvents();click(widget.undo_button)
            select_pair();confidence=widget._candidate()['confidence']
            assert widget.grab().save(str(args.output/(artist.mbid+'-suggestion.png')))
            widget.reason_input.setText('QA自动化：仅在隔离副本验证界面与可撤销审计，不代表实际用户作品判断')
            click(widget.merge_button)
            assert any(source_ids|target_ids<=recording_set(s) for s in widget.snapshot['result'].songs)
            merge_id=widget.snapshot['events'][-1]['id']
            widget.grab().save(str(args.output/(artist.mbid+'-merge.png')))
            undo(merge_id)
            assert not any(source_ids|target_ids<=recording_set(s) for s in widget.snapshot['result'].songs)
            widget.tabs.setCurrentIndex(0);select_pair();click(widget.reject_button)
            reject_id=widget.snapshot['events'][-1]['id']
            assert next(s for s in widget.snapshot['result'].songs if source_ids<=recording_set(s)).review_action=='reject'
            select_pair();click(widget.independent_button)
            independent_id=widget.snapshot['events'][-1]['id']
            independent=next(s for s in widget.snapshot['result'].songs if source_ids<=recording_set(s))
            assert independent.reviewed and not independent.pending_confirmation
            undo(independent_id);undo(reject_id)
            events=[e for e in widget.snapshot['events'] if e['actor']=='qa_automation']
            assert len(events)==6
            assert widget.snapshot['result'].summary['manually_reviewed_item_count']==0
            assert {r.mbid for r in repo.recordings(artist.mbid)}==original
            assert {r.mbid for s in repo.songs(artist.mbid) for r in s.recordings}==original
            widget.tabs.setCurrentIndex(1);app.processEvents()
            assert widget.grab().save(str(args.output/(artist.mbid+'-audit.png')))
            reports.append({'artist':name,'artist_mbid':artist.mbid,'raw_recordings':len(original),'confidence':confidence,
                'merge_reject_independent_and_all_undos_verified':True,'audit_events':len(events),'production_audit_untouched':True})
        finally:
            if widget.worker:widget.worker.cancel_event.set();wait(app,lambda:widget.worker is None)
            widget.close();app.processEvents()
    with connect(args.database) as db:production_events=db.execute('SELECT count(*) FROM catalog_review_events').fetchone()[0]
    result={'success':True,'platform':'windows','isolated_database':str(copied.resolve()),'production_audit_event_count':production_events,'artists':reports}
    (args.output/'review-gui.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('NATIVE_REVIEW_GUI_OK',json.dumps(reports,ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
