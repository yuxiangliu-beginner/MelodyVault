from pathlib import Path
import json
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHeaderView, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMainWindow, QProgressBar, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QTabWidget, QMenu, QComboBox,
)
from melodyvault.catalog.models import CatalogResult, Progress
from melodyvault.catalog.worker import CatalogWorker
from melodyvault.catalog.grouping import version_kind


class MainWindow(QMainWindow):
    def __init__(self, database_path: Path) -> None:
        super().__init__()
        self.database_path = database_path
        self.worker: CatalogWorker | None = None
        self.last_result: CatalogResult | None = None
        self._pending_choices = None
        self._close_pending = False
        self.evidence_worker = None
        self._deferred_catalog = None
        self._search_generation=0;self._search_workers=set();self._catalog_workers=set();self.search_worker=None;self._queued_song_source=None
        self.setWindowTitle("MelodyVault")
        self.resize(1040, 720)
        layout = QVBoxLayout()
        central = QWidget()
        central.setLayout(layout)
        title = QLabel("MelodyVault · 私人音乐目录")
        title.setStyleSheet("font-size: 24px; font-weight: 600; padding: 12px 0;")
        layout.addWidget(title)
        row = QHBoxLayout()
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("输入歌手名称或歌曲名称…")
        self.artist_input.setAccessibleName("歌手或歌曲名称")
        self.artist_input.setObjectName("artistInput")
        row.addWidget(self.artist_input, 1)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("searchButton")
        self.search_button.clicked.connect(self.start_search)
        self.artist_input.returnPressed.connect(self.start_search)
        row.addWidget(self.search_button)
        self.cancel_button = QPushButton("取消搜索")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_search)
        row.addWidget(self.cancel_button)
        self.review_button=QPushButton('待确认作品审核')
        self.review_button.setObjectName('reviewButton');self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self.open_review);row.addWidget(self.review_button)
        self.refresh_catalog_button=QPushButton('刷新歌曲目录')
        self.refresh_catalog_button.clicked.connect(self._refresh_artist);row.addWidget(self.refresh_catalog_button)
        layout.addLayout(row)
        options=QHBoxLayout();layout.addLayout(options)
        self.search_mode=QComboBox();self.search_mode.addItem('智能识别','smart');self.search_mode.addItem('歌手','artist');self.search_mode.addItem('歌曲','song')
        options.addWidget(self.search_mode)
        self.artist_filter=QLineEdit();self.artist_filter.setPlaceholderText('可选歌手条件：用于修正歌曲搜索，不自动选择同名歌手');options.addWidget(self.artist_filter,1)
        self.local_only=QCheckBox('仅本地搜索');options.addWidget(self.local_only)
        self.clear_button=QPushButton('清空结果');options.addWidget(self.clear_button);self.clear_button.clicked.connect(self.clear_results)
        self.search_mode.currentIndexChanged.connect(self._mode_changed)
        self.refresh_checkbox = QCheckBox("重新从 MusicBrainz 获取（忽略本地页面缓存）")
        layout.addWidget(self.refresh_checkbox)
        self.artist_label = QLabel("输入歌手或歌曲名称，核对身份后进入目录或选择录音版本；同名候选需要选择。")
        self.artist_label.setTextFormat(Qt.TextFormat.PlainText)
        self.artist_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.artist_label.setWordWrap(True)
        layout.addWidget(self.artist_label)
        notice = QLabel("已核实作品和独立待确认歌曲各一行；展开查看全部版本。弱证据只供人工审核，不按同名自动合并。")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.progress_label = QLabel("准备就绪。首次获取可能需要数分钟；再次搜索会复用最近 7 天的 API 页面。")
        self.progress_label.setObjectName("catalogStatus")
        self.progress_label.setTextFormat(Qt.TextFormat.PlainText)
        self.progress_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.statistics_label = QLabel("原始录音 0 · 已核实/人工确认作品 0 · 重复收录 0 · 版本 0 · 待确认 0 · 已人工审核 0")
        self.statistics_label.setObjectName('catalogStatistics')
        self.statistics_label.setWordWrap(True)
        layout.addWidget(self.statistics_label)
        from melodyvault.ui.unified_results import UnifiedResults
        self.unified_results=UnifiedResults(self);layout.addWidget(self.unified_results);self.unified_results.hide()
        self.unified_results.artist_chosen.connect(self._enter_artist);self.unified_results.song_chosen.connect(self._confirm_song)
        self.unified_results.more_requested.connect(lambda:self.start_search(force_online=True))
        self.song_table = QTreeWidget()
        self.song_table.setObjectName("songTable")
        self.song_table.setAccessibleName("歌曲目录")
        self.song_table.setColumnCount(3)
        self.song_table.setHeaderLabels(["歌曲 / 录音版本（点击箭头展开）", "作品状态", "音源搜索状态"])
        self.song_table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.song_table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.song_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.song_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.song_table.setSortingEnabled(False)
        layout.addWidget(self.song_table, 1)
        from melodyvault.ui.source_page import SourcePage
        root=QWidget();root_layout=QVBoxLayout(root)
        self.tabs=QTabWidget();self.tabs.addTab(central,'歌曲目录')
        self.source_page=SourcePage(database_path,self);self.tabs.addTab(self.source_page,'音源搜索');root_layout.addWidget(self.tabs,1)
        from melodyvault.ui.download_page import DownloadPage
        from melodyvault.ui.download_settings import DownloadSettingsPage
        self.download_page=DownloadPage(database_path,self);self.tabs.addTab(self.download_page,'下载任务')
        self.download_settings=DownloadSettingsPage(self.download_page.repository,self);self.tabs.addTab(self.download_settings,'下载设置')
        self.download_settings.saved.connect(self.download_page.save_settings)
        from melodyvault.ui.discovery_page import DiscoveryPage
        self.discovery_page=DiscoveryPage(database_path,self);self.tabs.addTab(self.discovery_page,'音源发现')
        self.discovery_page.workers_finished.connect(self._other_finished)
        self.download_page.workers_finished.connect(self._other_finished)
        self.source_page.download_requested.connect(self._queue_source_download)
        evidence_row=QHBoxLayout();root_layout.addLayout(evidence_row)
        self.evidence_button=QPushButton('补充作品证据');self.evidence_button.setEnabled(False)
        self.evidence_force=QCheckBox('强制刷新证据缓存');self.evidence_cancel=QPushButton('取消深度补证');self.evidence_cancel.setEnabled(False)
        self.evidence_label=QLabel('深度补证独立运行，不影响歌曲目录和音源搜索。');self.evidence_label.setWordWrap(True)
        for w in (self.evidence_button,self.evidence_force,self.evidence_cancel,self.evidence_label):evidence_row.addWidget(w)
        self.evidence_button.clicked.connect(self.start_evidence);self.evidence_cancel.clicked.connect(lambda:self.evidence_worker.cancel() if self.evidence_worker else None)
        self.source_task_label=QLabel('音源任务：等待开始');self.source_task_label.setWordWrap(True);root_layout.addWidget(self.source_task_label)
        self.source_page.task_progress.connect(self._source_progress);self.source_page.statuses_changed.connect(self._source_states)
        self.source_page.workers_finished.connect(self._other_finished)
        self.source_page.workers_finished.connect(self._launch_queued_source)
        self.song_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.song_table.customContextMenuRequested.connect(self._song_menu)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Phase 3B.1 · 来源发现/许可审核/本地归档 · 默认dry-run")

    @Slot()
    def _start_catalog(self, selected_mbid: str | None = None, force_refresh: bool = False, query_override=None) -> None:
        self._invalidate_requests()
        if self.worker is not None:
            return
        query = query_override or self.artist_input.text().strip()
        if not query:
            self.progress_label.setText("请输入歌手名字。")
            self.artist_input.setFocus()
            return
        if self.evidence_worker is not None and (force_refresh or self.refresh_checkbox.isChecked()):
            self._deferred_catalog=(query,selected_mbid,force_refresh)
            self.evidence_worker.cancel()
            self.evidence_label.setText('目录刷新优先：已请求取消补证，当前请求结束后开始刷新。已有歌曲和音源搜索不受影响。')
            return
        self.last_result = None
        self._last_catalog_query=query
        self.unified_results.hide();self.song_table.show()
        self.song_table.clear()
        self._pending_choices = None
        self.statistics_label.setText('正在处理目录；尚未完成本次统计')
        self._set_busy(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText("正在后台搜索 MusicBrainz；可以取消。")
        self.artist_label.setText("正在核对歌手身份……")
        # clicked(bool) is not a user-selected MBID.
        if not isinstance(selected_mbid, str):
            selected_mbid = None
        worker = CatalogWorker(self.database_path, query, force_refresh or self.refresh_checkbox.isChecked(), selected_mbid, self)
        self.worker = worker
        self._catalog_workers.add(worker);generation=self._search_generation
        from melodyvault.ui.request_relay import RequestRelay
        relay=RequestRelay(self,worker,generation,{'ready':self._on_completed,'progress':self._on_progress,'partial':self._on_partial,'failed':self._on_failed,'cancelled':self._on_cancelled,'choices':self._on_choices},catalog=True)
        worker.progress.connect(relay.progress);worker.completed.connect(relay.ready);worker.partial.connect(relay.partial)
        worker.failed.connect(relay.failed);worker.cancelled.connect(relay.cancelled);worker.choices_required.connect(relay.choices);worker.finished.connect(relay.finished)
        worker.start()

    def _deliver(self,generation,callback,data):
        if generation==self._search_generation and not self._close_pending:callback(data)

    def _invalidate_requests(self):
        self._search_generation+=1;self._queued_song_source=None
        for worker in (*self._search_workers,*self._catalog_workers):worker.cancel()
        self.search_worker=None;self.worker=None

    @Slot()
    def start_search(self, selected_mbid=None, force_refresh=False, force_online=False):
        if self.search_mode.currentData()=='artist' and not self.local_only.isChecked():
            self._start_catalog(selected_mbid,force_refresh);return
        from melodyvault.search.models import SearchRequest
        from melodyvault.search.worker import SearchWorker
        try:request=SearchRequest(self.artist_input.text(),self.search_mode.currentData(),self.artist_filter.text(),local_only=self.local_only.isChecked(),force_online=force_online or force_refresh or self.refresh_checkbox.isChecked())
        except ValueError as error:self.progress_label.setText(str(error));return
        self._invalidate_requests();generation=self._search_generation
        self.last_result=None;self.song_table.clear();self.song_table.hide();self.unified_results.clear();self.unified_results.show()
        self.artist_label.setText('尚未选择歌手或歌曲身份');self.statistics_label.setText('正在搜索候选，不代表已获取音频')
        self.statusBar().showMessage('正在后台搜索歌手与歌曲候选')
        self.progress_bar.setRange(0,0);self.progress_label.setText('正在后台检索本地索引和候选……')
        worker=SearchWorker(self.database_path,request,self);self.search_worker=worker;self._search_workers.add(worker)
        from melodyvault.ui.request_relay import RequestRelay
        relay=RequestRelay(self,worker,generation,{'ready':self._search_ready,'partial':self._search_partial,'progress':self.progress_label.setText,'failed':self._on_failed,'cancelled':self._on_cancelled})
        worker.ready.connect(relay.ready);worker.partial.connect(relay.partial);worker.progress.connect(relay.text_progress);worker.failed.connect(relay.failed);worker.cancelled.connect(relay.cancelled);worker.finished.connect(relay.finished);self.cancel_button.setEnabled(True)
        self.review_button.setEnabled(False);self.evidence_button.setEnabled(False);self.refresh_catalog_button.setEnabled(False)
        worker.start()

    def _search_ready(self,result):
        self.unified_results.show_result(result);self.song_table.hide();self.progress_bar.setRange(0,1);self.progress_bar.setValue(1)
        self.search_button.setText('搜索')
        self.statistics_label.setText(f'歌手候选 {len(result.artists)} · 录音候选 {len(result.songs)} · 待确认 {sum(c.pending_confirmation for c in result.songs)} · 查询错误 {len(result.errors)}')
        self.statusBar().showMessage('元数据检索已结束；请选择身份和版本，尚未开始音源搜索')
        self.progress_label.setText('请选择歌手目录或具体歌曲版本；不会自动选择同名歌曲。'+(' 部分查询失败，详见候选区域。' if result.errors else ''))
        if result.request.mode=='smart' and result.scope=='sqlite' and len(result.artists)==1 and not result.songs and result.title_query==result.request.query:
            from melodyvault.database.catalog import CatalogRepository
            previous=CatalogRepository(self.database_path).resolved_artist(result.request.query)
            if previous and previous.mbid==result.artists[0].mbid:self._enter_artist(previous)

    def _search_partial(self,result):
        self.unified_results.show_result(result);self.progress_label.setText('已显示本地候选；正在补充其他歌手/版本，不会因本地只存一位歌手就自动选定原唱。')

    def _enter_artist(self,artist):
        if self.local_only.isChecked():
            from melodyvault.database.catalog import CatalogRepository
            if not CatalogRepository(self.database_path).songs(artist.mbid):
                self.progress_label.setText('该歌手尚无本地歌曲目录；取消“仅本地搜索”后可联网获取。');return
        self._start_catalog(artist.mbid,False,artist.name)
    def _refresh_artist(self):
        if self.last_result:self._start_catalog(self.last_result.artist.mbid,self.last_result.summary.get('selection_scope')!='recording',self.last_result.artist.name)
    def _confirm_song(self,candidate):
        from melodyvault.search.worker import SearchWorker
        result=self.unified_results.result
        if result is None:return
        self._invalidate_requests();generation=self._search_generation
        worker=SearchWorker(self.database_path,result.request,self,candidate,result.title_query)
        self.search_worker=worker;self._search_workers.add(worker);self.unified_results.song_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.progress_label.setText('正在核对所选Recording并关联现有模型；不改变人工审核分组。')
        from melodyvault.ui.request_relay import RequestRelay
        relay=RequestRelay(self,worker,generation,{'ready':self._song_confirmed,'failed':self._on_failed,'cancelled':self._on_cancelled})
        worker.ready.connect(relay.ready);worker.failed.connect(relay.failed);worker.cancelled.connect(relay.cancelled);worker.finished.connect(relay.finished);worker.start()
    def _song_confirmed(self,result):
        self.unified_results.hide();self.song_table.show();self._on_completed(result)
        self.progress_label.setText('已选择具体录音版本，准备单首音源搜索；这不代表授权或下载成功。')
        self._queued_song_source=(self._search_generation,result);self._launch_queued_source()
    def _launch_queued_source(self):
        if not self._queued_song_source or self.source_page.worker is not None:return
        generation,result=self._queued_song_source;self._queued_song_source=None
        if generation!=self._search_generation or self._close_pending:return
        self.source_page.set_catalog(result);self.tabs.setCurrentIndex(1);self.source_page.search_songs(result.songs)
    def _unified_finished(self,worker,generation):
        self._search_workers.discard(worker)
        if generation==self._search_generation:
            self.search_worker=None;self._set_busy(False)
            if self.unified_results.result:self.unified_results._selected()
        worker.deleteLater();self._other_finished()
    def _catalog_finished(self,worker,generation):
        self._catalog_workers.discard(worker)
        if generation==self._search_generation and self.worker is worker:self._on_finished()
        else:worker.deleteLater()
        self._other_finished()
    def clear_results(self):
        self._invalidate_requests();self.artist_input.clear();self.artist_filter.clear();self.last_result=None
        self.unified_results.clear();self.unified_results.hide();self.song_table.clear();self.song_table.show()
        self.artist_label.setText('尚未选择歌手或歌曲身份')
        self.statusBar().showMessage('已清空当前结果；保存目录与审核历史保留')
        self.progress_bar.setRange(0,1);self.progress_bar.setValue(0);self.statistics_label.setText('当前搜索结果已清空；保存目录与审核历史未删除。')
        self.progress_label.setText('准备搜索');self._set_busy(False)
    def _mode_changed(self):
        self._invalidate_requests();self.unified_results.clear();self.unified_results.hide();self.song_table.show();self._set_busy(False)
        self.artist_filter.setEnabled(self.search_mode.currentData()!='artist')
    def _requests_running(self):return any(w.isRunning() for w in (*self._search_workers,*self._catalog_workers))

    def _set_busy(self, busy: bool) -> None:
        self.search_button.setEnabled(not busy)
        self.artist_input.setEnabled(not busy)
        self.refresh_checkbox.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.review_button.setEnabled(not busy and self.last_result is not None)
        self.refresh_catalog_button.setEnabled(not busy and self.last_result is not None)
        self.evidence_button.setEnabled(not busy and self.last_result is not None and self.evidence_worker is None)

    @Slot()
    def open_review(self):
        if self.worker is not None or self.last_result is None:return
        from melodyvault.ui.review_dialog import ReviewDialog
        dialog=ReviewDialog(self.database_path,self.last_result.artist,self)
        dialog.catalog_changed.connect(self._on_reviewed)
        dialog.exec()

    @Slot(object)
    def _on_reviewed(self,result):
        self._on_completed(result)
        message='审核结果已保存：原始录音与全部版本保留，可在审计历史中撤销决定。'
        if result.summary.get('stale_review_count'):
            message+=f" 有 {result.summary['stale_review_count']} 条历史决定需重审。"
        self.progress_label.setText(message)

    @Slot()
    def cancel_search(self) -> None:
        if self.search_worker:
            self.search_worker.cancel();self.cancel_button.setEnabled(False);self.progress_label.setText('已请求取消搜索；已保存数据保留。')
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.progress_label.setText("正在取消；当前 HTTP 请求最迟在超时后结束，已完成页面会保留。")

    @Slot(object)
    def _on_progress(self, event: Progress) -> None:
        if event.total is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, max(1, event.total))
            self.progress_bar.setValue(event.processed if event.total else 1)
        self.progress_label.setText(event.message)
        self.statusBar().showMessage(f"{event.stage} · {event.processed}/{event.total if event.total is not None else '?'}")
        if event.artist:
            self.artist_label.setText("已确认歌手：" + event.artist.label)

    @Slot(object)
    def _on_completed(self, result: CatalogResult) -> None:
        self.last_result = result
        self.artist_label.setText('已确认歌手：'+result.artist.label)
        self.refresh_catalog_button.setText('进入该歌手目录' if result.summary.get('selection_scope')=='recording' else '刷新歌曲目录')
        self.song_table.setUpdatesEnabled(False)
        self.song_table.clear()
        confirmed = [song for song in result.songs if not song.pending_confirmation]
        pending = [song for song in result.songs if song.pending_confirmation]
        try:
            for song in confirmed + pending:
                label='待确认' if song.pending_confirmation else '人工确认' if song.reviewed else 'Work 已核实'
                state = f"{label}{' · 已审核' if song.reviewed else ''} · {len(song.recordings)} 个录音"
                item = QTreeWidgetItem([song.title, state, '尚未搜索'])
                item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "song", "song_id": song.id})
                tooltip = f"Song ID：{song.id}\nWork ID：{', '.join(song.work_ids) or '缺少可靠作品关联'}\n主版本依据：{song.primary_reason}\n" + json.dumps(song.evidence, ensure_ascii=False, indent=2)
                item.setToolTip(0, tooltip)
                self.song_table.addTopLevelItem(item)
                for recording in song.recordings:
                    kind, reasons = version_kind(recording)
                    kind_label = {'studio':'录音室（发行证据）','live':'现场','remix':'Remix',
                                  'unknown':'版本未核实','medley':'串烧','partial':'片段',
                                  'instrumental':'演奏版','karaoke':'伴奏','demo':'Demo','edit':'剪辑版','rerecording':'重新录制'}.get(kind,kind)
                    is_primary = recording.mbid == song.primary_recording_mbid
                    child = QTreeWidgetItem([recording.display_title, f"{'主版本 · ' if is_primary else ''}{kind_label} · {recording.mbid[:8]}"])
                    child.setData(0, Qt.ItemDataRole.UserRole, {"kind": "recording", "recording_mbid": recording.mbid})
                    child.setToolTip(0, f"原始标题：{recording.original_title}\nRecording MBID：{recording.mbid}\n版本证据：{'; '.join(reasons)}\n下载授权：尚未核验")
                    item.addChild(child)
            self.song_table.collapseAll()
        finally:
            self.song_table.setUpdatesEnabled(True)
        summary = result.summary
        self.statistics_label.setText(
            f"原始录音 {summary['raw_recording_count']} · 已核实/人工确认作品 {summary['independent_song_count']}（Work 核实 {summary.get('work_verified_song_count',0)}） · "
            f"重复发行收录 {summary['duplicate_release_count']} · 录音版本 {summary['version_count']}（额外版本 {summary['additional_version_count']}） · "
            f"待确认 {summary['pending_song_count']} 项 / {summary['pending_recording_count']} 条录音 · "
            f"已人工审核 {summary.get('manually_reviewed_item_count',0)}项")
        self.progress_label.setText(
            f"目录处理已保存到 SQLite；API 请求 {summary['api_requests']} 次，缓存页面 {summary['cache_hits']} 个。\n"
            "同名不等于同一作品；待确认记录仍独立保存。此目录不代表完整作品库或音频下载授权。")
        if summary.get('stale_review_count'):
            self.progress_label.setText(self.progress_label.text()+f"\n有 {summary['stale_review_count']} 条历史决定因证据/依赖变化需重审，请打开审核历史。")
        self.statusBar().showMessage(f"{len(confirmed)} 首已核实/人工确认作品 · {len(pending)} 项待确认 · 展开查看版本和证据")
        self.review_button.setEnabled(self.worker is None)
        self.evidence_button.setEnabled(self.worker is None and self.evidence_worker is None)
        self.source_page.set_catalog(result)
        self.download_page.set_catalog(result)
        if result.summary.get('cached_catalog'):
            self.progress_label.setText(f"已从 SQLite 直接显示保存目录；本次 API 请求 0，读取耗时 {summary.get('catalog_seconds',0):.3f}秒。通过“刷新歌曲目录”更新目录，作品补证请单独启动。")
            self.progress_bar.setRange(0,1);self.progress_bar.setValue(1)

    @Slot(object)
    def _on_partial(self,result):
        self._on_completed(result)
        self.progress_label.setText(f'已逐步显示 {len(result.songs)} 个歌曲条目；目录获取仍在后台进行，可先搜索音源。尚未完成本次目录任务。')

    def start_evidence(self):
        if self.evidence_worker or self.worker or not self.last_result:return
        from melodyvault.catalog.evidence_worker import EvidenceWorker
        worker=EvidenceWorker(self.database_path,self.last_result.artist,self.evidence_force.isChecked(),self)
        self.evidence_worker=worker;self.evidence_button.setEnabled(False);self.evidence_cancel.setEnabled(True)
        worker.progress.connect(lambda message:self.evidence_label.setText(f'{worker.artist.name}：{message}'));worker.completed.connect(self._evidence_done)
        worker.failed.connect(lambda message:self.evidence_label.setText('补证失败：'+message))
        worker.cancelled.connect(lambda message:self.evidence_label.setText('补证已取消；已有歌曲保留。'+message))
        worker.finished.connect(self._evidence_finished);worker.start(worker.Priority.LowPriority)

    def _evidence_done(self,result):
        if self.last_result and self.last_result.artist.mbid==result.artist.mbid:self._on_completed(result)
        self.evidence_label.setText(f"{result.artist.name}补证完成；API {result.summary['api_requests']}，缓存 {result.summary['cache_hits']}；耗时 {result.summary['evidence_seconds']:.2f}秒。")
    def _evidence_finished(self):
        worker=self.evidence_worker;self.evidence_worker=None
        if worker and worker.cancel_event.is_set():
            metrics=getattr(worker,'metrics',{})
            self.evidence_label.setText(self.evidence_label.text()+f" 实际API {metrics.get('api_requests',0)}，耗时{metrics.get('seconds',0):.2f}秒。")
        if worker:worker.deleteLater()
        self.evidence_cancel.setEnabled(False);self.evidence_button.setEnabled(self.last_result is not None and self.worker is None)
        self._other_finished()
        if self._deferred_catalog and not self._close_pending:
            query,selected,force=self._deferred_catalog;self._deferred_catalog=None;self.artist_input.setText(query)
            QTimer.singleShot(0,lambda:self._start_catalog(selected,force,query))
    def _other_finished(self):
        if self._close_pending and not self._requests_running() and self.worker is None and self.evidence_worker is None and self.source_page.worker is None and self.source_page.browser_worker is None and self.download_page.worker is None and self.discovery_page.worker is None:self.close()
    def _source_progress(self,stats):
        self.source_task_label.setText(f"{stats.get('artist','')} 音源：{stats['current_song'] or '—'} · {stats['current_provider'] or '—'} · {stats['searched']}/{stats['total']}（{stats['percent']:.1f}%） · 已完成 {stats.get('completed',stats['searched']-stats['failed'])} / 失败 {stats['failed']} / 待处理 {stats['pending']}。{stats['message']}")
    def _source_states(self,payload):
        if not self.last_result or payload['artist_mbid']!=self.last_result.artist.mbid:return
        states=payload['states']
        for index in range(self.song_table.topLevelItemCount()):
            item=self.song_table.topLevelItem(index);data=item.data(0,Qt.ItemDataRole.UserRole)
            if data:item.setText(2,states.get(data['song_id'],'尚未搜索'))
    def _song_menu(self,point):
        item=self.song_table.itemAt(point)
        if item is None or self.last_result is None:return
        selected_recording=item.data(0,Qt.ItemDataRole.UserRole).get('recording_mbid') if item.parent() else None
        if item.parent():item=item.parent()
        sid=item.data(0,Qt.ItemDataRole.UserRole)['song_id']
        song=next(s for s in self.last_result.songs if s.id==sid)
        menu=QMenu(self);action=menu.addAction('搜索此歌曲的多来源音源');action.setEnabled(self.source_page.worker is None)
        download=menu.addAction('建立下载审核任务（默认dry-run）');download.setEnabled(self.download_page.worker is None)
        chosen=menu.exec(self.song_table.viewport().mapToGlobal(point))
        if chosen==action:
            self.tabs.setCurrentIndex(1);self.source_page.search_songs([song])
        elif chosen==download:
            from dataclasses import replace
            summary=dict(self.last_result.summary)
            if selected_recording:
                record=next(r for r in song.recordings if r.mbid==selected_recording)
                song=replace(song,recordings=[record],primary_recording_mbid=record.mbid if song.primary_recording_mbid==record.mbid else None);summary['selection_scope']='recording'
            snapshot=CatalogResult(self.last_result.artist,[song],summary,song.recordings)
            self.tabs.setCurrentWidget(self.download_page);self.download_page.enqueue_catalog(snapshot)

    def _queue_source_download(self,raw):
        catalog=self.source_page.catalog
        if not raw or not catalog:return
        song=next((s for s in catalog.songs if s.id==raw.get('target_song_id')),None)
        if song is None:return
        self.tabs.setCurrentWidget(self.download_page)
        self.download_page.enqueue_catalog(CatalogResult(catalog.artist,[song],dict(catalog.summary),song.recordings),raw)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.progress_label.setText("搜索失败：" + message)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.search_button.setText("重试搜索")
        self.statusBar().showMessage("未完成；再次搜索可复用已保存的页面")

    @Slot(str)
    def _on_cancelled(self, message: str) -> None:
        self.progress_label.setText(message)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("已取消；未标记搜索完成")

    @Slot(object)
    def _on_choices(self, candidates) -> None:
        self._pending_choices = candidates

    @Slot()
    def _on_finished(self) -> None:
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_busy(False)
        if self.last_result:
            self.search_button.setText("搜索")
        if self._close_pending:
            self.close()
            return
        if self._pending_choices:
            candidates = self._pending_choices
            self._pending_choices = None
            dialog = QDialog(self)
            dialog.setWindowTitle("请选择正确的 MusicBrainz 歌手")
            dialog.resize(780, 450)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("存在同名或近似歌手，请核对地区、出生日期和 MBID；不确定时取消。"))
            choices = QListWidget()
            for artist in candidates:
                choices.addItem(artist.label)
            choices.setCurrentRow(-1)
            layout.addWidget(choices)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            choices.currentRowChanged.connect(lambda row: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(row >= 0))
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() == QDialog.DialogCode.Accepted and choices.currentRow() >= 0:
                self._start_catalog(candidates[choices.currentRow()].mbid,query_override=self._last_catalog_query)
            else:
                self.progress_label.setText("已取消歌手选择；未搜索或保存错误身份的歌曲。")

    def closeEvent(self, event) -> None:
        if self.discovery_page.worker is not None:
            self._close_pending=True;self.discovery_page.cancel()
            self.source_page.cancel();self.download_page.pause_tasks()
            for worker in (*self._search_workers,*self._catalog_workers):worker.cancel()
            if self.evidence_worker:self.evidence_worker.cancel()
            if self.source_page.browser_worker:self.source_page.browser_worker.cancel()
            event.ignore();return
        if self._requests_running():
            self._close_pending=True
            for worker in (*self._search_workers,*self._catalog_workers):worker.cancel()
            if self.evidence_worker:self.evidence_worker.cancel()
            self.source_page.cancel()
            self.download_page.pause_tasks()
            if self.source_page.browser_worker:self.source_page.browser_worker.cancel()
            event.ignore();return
        other_busy=self.evidence_worker is not None or self.source_page.worker is not None or self.source_page.browser_worker is not None or self.download_page.worker is not None
        if other_busy:
            self._close_pending=True
            if self.evidence_worker:self.evidence_worker.cancel()
            self.source_page.cancel()
            self.download_page.pause_tasks()
            if self.source_page.browser_worker:self.source_page.browser_worker.cancel()
            if self.worker:self.cancel_search()
            event.ignore();return
        if self.worker is not None:
            self._close_pending = True
            self.cancel_search()
            event.ignore()
            return
        super().closeEvent(event)
