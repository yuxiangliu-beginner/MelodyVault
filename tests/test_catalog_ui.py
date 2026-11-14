"""Real widgets, QThread, signals and event loop; offline HTTP fixtures only."""
import time
import httpx
import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from melodyvault.catalog import worker as worker_module
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.database import initialize_database
from melodyvault.ui.main_window import MainWindow
from catalog_fixtures import CatalogTransport


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def wait_until(app, condition, timeout=30):
    end = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > end:
            raise AssertionError("Qt condition timed out")
        QTest.qWait(5)
    app.processEvents()


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    transport = CatalogTransport(delay=0.025)
    def factory(repository, cancel, force_refresh=False):
        return MusicBrainzClient(repository, cancel, force_refresh,
                                transport=httpx.MockTransport(transport), interval=0,
                                max_attempts=1, retry_base=0)
    monkeypatch.setattr(worker_module, "MusicBrainzClient", factory)
    database = tmp_path / "gui.sqlite3"
    initialize_database(database)
    widget = MainWindow(database)
    widget.search_mode.setCurrentIndex(widget.search_mode.findData('artist'))
    widget.show()
    yield widget, transport
    if widget.worker:
        widget.worker.cancel()
        wait_until(qapp, lambda: widget.worker is None)
    widget.close()
    qapp.processEvents()


@pytest.mark.gui
def test_search_keeps_event_loop_alive_and_restores_controls(qapp, window):
    widget, _ = window
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    try:
        widget.artist_input.setText("周杰伦")
        QTest.mouseClick(widget.search_button, Qt.MouseButton.LeftButton)
        assert not widget.search_button.isEnabled()
        assert widget.cancel_button.isEnabled()
        wait_until(qapp, lambda: widget.worker is None)
        assert len(ticks) > 5
        assert widget.search_button.isEnabled()
        assert not widget.cancel_button.isEnabled()
        assert widget.last_result is not None
        assert len(widget.last_result.recordings) == 4
        # Fast catalog retrieval no longer implicitly waits for Work enrichment.
        assert widget.song_table.topLevelItemCount() == 4
        assert sum(widget.song_table.topLevelItem(i).childCount() for i in range(4)) == 4
        assert not widget.song_table.topLevelItem(0).isExpanded()
        widget.song_table.expandItem(widget.song_table.topLevelItem(0))
        assert widget.song_table.topLevelItem(0).isExpanded()
        assert "专辑" not in widget.song_table.headerItem().text(0)
        assert '已核实/人工确认作品 0' in widget.statistics_label.text()
        assert "已保存到 SQLite" in widget.progress_label.text()
    finally:
        timer.stop()


@pytest.mark.gui
def test_actual_http_error_is_visible_and_retry_enabled(qapp, window):
    widget, transport = window
    transport.fail_all = True
    widget.artist_input.setText("周杰伦")
    QTest.mouseClick(widget.search_button, Qt.MouseButton.LeftButton)
    wait_until(qapp, lambda: widget.worker is None)
    assert 'HTTP 503' in widget.progress_label.text()
    assert 'offline fixture busy' in widget.progress_label.text()
    assert widget.search_button.isEnabled()
    assert widget.last_result is None
    assert widget.song_table.topLevelItemCount() == 0


@pytest.mark.gui
def test_cancel_restores_controls_without_success(qapp, window):
    widget, _ = window
    widget.artist_input.setText("周杰伦")
    QTest.mouseClick(widget.search_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(widget.cancel_button, Qt.MouseButton.LeftButton)
    wait_until(qapp, lambda: widget.worker is None)
    assert '取消' in widget.progress_label.text()
    assert widget.search_button.isEnabled()
    assert widget.last_result is None


@pytest.mark.gui
def test_close_waits_for_cancellation_without_blocking_ui(qapp, window):
    widget, _ = window
    widget.artist_input.setText("周杰伦")
    QTest.mouseClick(widget.search_button, Qt.MouseButton.LeftButton)
    widget.close()
    assert widget._close_pending
    wait_until(qapp, lambda: widget.worker is None)
    assert not widget.isVisible()
