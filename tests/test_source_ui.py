import time
from dataclasses import replace
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from melodyvault.sources.models import Candidate
from melodyvault.sources import worker as source_worker
from melodyvault.catalog.models import Artist
from test_catalog_ui import qapp,window,wait_until


class MetadataProvider:
    name='archive';enabled=True
    def __init__(self,delay=.025):self.calls=0;self.delay=delay
    def search(self,query,http):
        self.calls+=1;time.sleep(self.delay)
        return [Candidate(self.name,query.song_id,query.title,query.artist,'https://archive.org/details/unit-test',license_reason='离线故障/界面样例，无许可证明')]


def load_catalog(app,widget):
    widget.artist_input.setText('周杰伦');QTest.mouseClick(widget.search_button,Qt.MouseButton.LeftButton)
    wait_until(app,lambda:widget.worker is None)
    assert widget.last_result


def test_source_widgets_real_queue_progress_cache_and_license_reasons(qapp,window,monkeypatch):
    widget,transport=window;load_catalog(qapp,widget)
    provider=MetadataProvider();monkeypatch.setattr(source_worker,'default_providers',lambda:[provider])
    widget.tabs.setCurrentIndex(1);page=widget.source_page;ticks=[]
    timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(5)
    try:
        QTest.mouseClick(page.five_button,Qt.MouseButton.LeftButton)
        assert not page.five_button.isEnabled() and page.cancel_button.isEnabled()
        wait_until(qapp,lambda:page.worker is None)
        assert page.progress_bar.maximum()==4 and page.progress_bar.value()==4
        assert provider.calls==4 and len(ticks)>5 and page.table.rowCount()==4
        page.table.selectRow(0)
        assert 'LICENSE_UNVERIFIED' in page.details.toPlainText() and '无许可证明' in page.details.toPlainText()
        assert page.open_button.isEnabled() and page.inspect_button.isEnabled()
        QTest.mouseClick(page.five_button,Qt.MouseButton.LeftButton);wait_until(qapp,lambda:page.worker is None)
        assert provider.calls==4
    finally:timer.stop()


def test_artist_switch_waits_for_old_source_snapshot_then_loads_new_artist(qapp,window,monkeypatch):
    widget,transport=window;load_catalog(qapp,widget)
    provider=MetadataProvider(.08);monkeypatch.setattr(source_worker,'default_providers',lambda:[provider])
    page=widget.source_page;page.search_songs(widget.last_result.songs)
    new=replace(widget.last_result,artist=Artist('different-artist','另一位歌手'))
    widget._on_completed(new)
    assert page.pending_catalog is new
    wait_until(qapp,lambda:page.worker is None)
    assert page.catalog.artist.mbid=='different-artist' and page.table.rowCount()==0
    assert all(widget.song_table.topLevelItem(i).text(2)=='尚未搜索' for i in range(widget.song_table.topLevelItemCount()))


def test_close_cancels_source_worker_and_waits_without_destroying_thread(qapp,window,monkeypatch):
    widget,transport=window;load_catalog(qapp,widget)
    monkeypatch.setattr(source_worker,'default_providers',lambda:[MetadataProvider(.1)])
    page=widget.source_page;page.search_songs(widget.last_result.songs)
    qapp.processEvents();widget.close()
    wait_until(qapp,lambda:page.worker is None)
    assert not widget.isVisible()
