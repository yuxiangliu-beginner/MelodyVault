"""Opt-in native Qt E2E: real widgets + official API, no fixture transport.

Run from the installed development environment. The script only sends Qt events
to widgets it owns; it does not control other Windows applications.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

# Set before importing Qt. CI/offscreen tests cannot satisfy this native check.
os.environ["QT_QPA_PLATFORM"] = "windows"
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from melodyvault.config import load_settings
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository
from melodyvault.logging_setup import configure_logging
from melodyvault.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--allow-cached", action="store_true", help="UI-only regression after a separately verified live refresh")
    parser.add_argument('--artist',default='周杰伦')
    args = parser.parse_args()
    settings = load_settings(data_root=args.data_dir)
    settings.prepare()
    initialize_database(settings.database_path)
    configure_logging(settings.log_dir)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("MelodyVault")
    window = MainWindow(settings.database_path)
    window.show()
    started = time.monotonic()
    last_tick = started
    gaps = []
    busy_ticks = 0
    messages = []
    state = {"qt_platform": app.platformName(), "artist_input": args.artist, "started": False}
    finished = False
    timeout = False

    def write_report(success, error=None):
        payload = {**state, "success": success, "error": error,
                   "elapsed_seconds": time.monotonic() - started,
                   "ui_heartbeat_ticks_during_work": busy_ticks,
                   "max_ui_heartbeat_gap_seconds": max(gaps, default=0),
                   "progress_messages": messages}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def finish():
        nonlocal finished
        finished = True
        timer.stop()
        result = window.last_result
        assert result is not None, window.progress_label.text()
        expected={'周杰伦':'a223958d-5c56-4b2c-a30a-87e357bc121b','林俊杰':'e5d8c705-8ea4-4820-b11d-fbf580d85ce4'}
        assert result.artist.mbid == expected[args.artist]
        assert len(result.recordings) >= 200
        confirmed = [song for song in result.songs if not song.pending_confirmation]
        pending = [song for song in result.songs if song.pending_confirmation]
        assert window.song_table.topLevelItemCount() == len(result.songs)
        assert '专辑' not in window.song_table.headerItem().text(0)
        visible_recording_ids = set()
        song_items = []
        for index in range(window.song_table.topLevelItemCount()):
            top = window.song_table.topLevelItem(index)
            assert not top.isExpanded()
            data = top.data(0,Qt.ItemDataRole.UserRole)
            items = [top.child(i) for i in range(top.childCount())] if data['kind'] == 'pending' else [top]
            for item in items:
                song_items.append(item)
                for j in range(item.childCount()):
                    visible_recording_ids.add(item.child(j).data(0,Qt.ItemDataRole.UserRole)['recording_mbid'])
        assert visible_recording_ids == {recording.mbid for recording in result.recordings}
        expandable = next(item for item in song_items if item.childCount() > 1 and (args.artist!='周杰伦' or item.text(0)=='龙拳'))
        window.song_table.setCurrentItem(expandable)
        window.song_table.scrollToItem(expandable)
        QTest.keyClick(window.song_table, Qt.Key.Key_Right)
        assert expandable.isExpanded()
        window.song_table.scrollToItem(expandable.child(expandable.childCount()-1))
        assert window.search_button.isEnabled() and not window.cancel_button.isEnabled()
        assert "SQLite" in window.progress_label.text()
        assert args.allow_cached or result.summary["api_requests"] > 0, "Use fresh data or --allow-cached for UI-only regression"
        assert busy_ticks > 10, "Qt heartbeat did not run during work"
        persisted = CatalogRepository(settings.database_path).recordings(result.artist.mbid)
        assert {recording.mbid for recording in persisted} == visible_recording_ids
        assert len(CatalogRepository(settings.database_path).songs(result.artist.mbid)) == len(result.songs)
        screenshot = args.report.with_suffix(".png")
        app.processEvents()
        assert window.grab().save(str(screenshot))
        state.update({"summary": result.summary, "displayed_song_rows": len(result.songs), "verified_or_human_confirmed_rows":len(confirmed),
                      "pending_entries":len(pending), "expand_recording_versions_verified":True,
                      "restored_search_button": True, "sqlite_matches_table": True,
                      "native_screenshot": str(screenshot.resolve())})
        write_report(True)
        print("NATIVE_CATALOG_E2E_OK", len(result.songs), flush=True)
        if not args.keep_open:
            window.close()
            app.quit()

    def tick():
        nonlocal last_tick, busy_ticks, timeout, finished
        try:
            now = time.monotonic()
            gaps.append(now - last_tick)
            last_tick = now
            if not state["started"]:
                return
            if window.worker is not None:
                busy_ticks += 1
            message = window.progress_label.text()
            if not messages or messages[-1] != message:
                messages.append(message)
                # Keep the heartbeat observational: synchronous stdout/file I/O
                # here can stall the GUI thread and distort measured gaps.
            if now - started > 300 and not timeout:
                timeout = True
                window.cancel_search()
            if window.worker is None:
                if timeout:
                    raise TimeoutError("Native E2E exceeded 300 seconds")
                finish()
        except Exception as error:
            finished = True
            timer.stop()
            write_report(False, f"{type(error).__name__}: {error}")
            window.close()
            app.exit(1)

    def enter_and_click():
        try:
            assert app.platformName() == "windows"
            window.artist_input.setFocus()
            commit = QInputMethodEvent()
            commit.setCommitString(args.artist)
            QApplication.sendEvent(window.artist_input, commit)
            assert window.artist_input.text() == args.artist
            QTest.mouseClick(window.search_button, Qt.MouseButton.LeftButton)
            assert not window.search_button.isEnabled()
            assert window.cancel_button.isEnabled()
            state.update({"started": True, "qt_input_commit_verified": True,
                          "search_clicked": True, "disabled_search_while_running": True})
        except Exception as error:
            write_report(False, f"{type(error).__name__}: {error}")
            app.exit(1)

    timer = QTimer()
    timer.setInterval(25)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(200, enter_and_click)
    exit_code = app.exec()
    if not finished:
        write_report(False, "Window closed before verification completed")
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
