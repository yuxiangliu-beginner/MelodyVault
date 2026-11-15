"""Source candidates, real task counters and explicit public-page inspection."""
import json
from urllib.parse import urlsplit
from PySide6.QtCore import Signal,Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,
    QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QPlainTextEdit,QProgressBar)
from melodyvault.sources.worker import SourceWorker
from melodyvault.sources.browser_worker import BrowserCheckWorker
from melodyvault.sources.models import SourceQuery
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.sources import SourceRepository


class SourcePage(QWidget):
    task_progress=Signal(object);statuses_changed=Signal(object);workers_finished=Signal()
    download_requested=Signal(object)
    def __init__(self,path,parent=None):
        super().__init__(parent);self.path=path;self.worker=None;self.browser_worker=None;self.catalog=None;self.pending_catalog=None;self.candidates=[];self.jobs={};self._rendered=-1
        layout=QVBoxLayout(self)
        title=QLabel('音源搜索 · 候选元数据；下载须经过独立资格审核');layout.addWidget(title)
        self.policy_label=QLabel('官方API：Internet Archive / Wikimedia Commons。Jamendo未配置client_id时明确跳过。网页或下载按钮本身不是授权证据。')
        self.policy_label.setWordWrap(True);layout.addWidget(self.policy_label)
        row=QHBoxLayout();layout.addLayout(row)
        self.all_button=QPushButton('批量搜索全部');self.five_button=QPushButton('搜索前5首');self.missing_button=QPushButton('仅搜索缺少已核实来源');self.retry_button=QPushButton('重试失败/取消项');self.cancel_button=QPushButton('取消音源搜索')
        for button in (self.all_button,self.five_button,self.missing_button,self.retry_button,self.cancel_button):row.addWidget(button)
        self.force_checkbox=QCheckBox('强制重新搜索（忽略成功/无结果缓存）');layout.addWidget(self.force_checkbox)
        self.browser_checkbox=QCheckBox('补充Chrome公开网页搜索（独立会话；遇访问限制停止）');layout.addWidget(self.browser_checkbox)
        self.progress_bar=QProgressBar();self.progress_bar.setRange(0,100);layout.addWidget(self.progress_bar)
        self.stats_label=QLabel('等待选择歌手目录');self.stats_label.setWordWrap(True);layout.addWidget(self.stats_label)
        self.status_label=QLabel('准备就绪');self.status_label.setWordWrap(True);self.status_label.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status_label)
        layout.addWidget(QLabel('上方为本次任务统计；下方候选列表包含该歌手已保存的查询结果。'))
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['目标歌曲','候选标题','演唱者','来源','匹配程度','授权状态','版本/时长'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(180);layout.addWidget(self.details)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.open_button=QPushButton('打开原始网页');self.inspect_button=QPushButton('用Chrome读取公开授权页面');self.browser_cancel_button=QPushButton('取消网页核验')
        for b in (self.open_button,self.inspect_button,self.browser_cancel_button):actions.addWidget(b)
        self.download_button=QPushButton('加入下载审核');actions.addWidget(self.download_button)
        self.download_button.clicked.connect(lambda:self.download_requested.emit(self.selected()) if self.selected() else None)
        self.all_button.clicked.connect(lambda:self.search_songs(self.catalog.songs if self.catalog else []))
        self.five_button.clicked.connect(lambda:self.search_songs(self.catalog.songs[:5] if self.catalog else []))
        self.missing_button.clicked.connect(lambda:self.search_songs(self.catalog.songs if self.catalog else [],'missing'))
        self.retry_button.clicked.connect(lambda:self.search_songs(self.catalog.songs if self.catalog else [],'failed'))
        self.cancel_button.clicked.connect(self.cancel)
        self.table.itemSelectionChanged.connect(self._select)
        self.open_button.clicked.connect(self._open)
        self.inspect_button.clicked.connect(self._inspect)
        self.browser_cancel_button.clicked.connect(lambda:self.browser_worker.cancel() if self.browser_worker else None)
        self._controls()

    def set_catalog(self,result):
        # An in-flight source task keeps its own immutable artist/song snapshot.
        if self.worker is not None:
            self.pending_catalog=result;return
        changed=self.catalog is None or self.catalog.artist.mbid!=result.artist.mbid
        self.catalog=result
        works=CatalogRepository(self.path).source_aliases(wid for s in result.songs for wid in s.work_ids)
        expected={s.id:SourceQuery.from_song(result.artist,s,works).fingerprint for s in result.songs}
        previous=SourceRepository(self.path).latest_jobs(result.artist.mbid)
        self.jobs={sid:{**p['summary'],'job_state':p['status']} for sid,p in previous.items() if p['query'].get('fingerprint')==expected.get(sid)}
        if changed:
            self.last_stats=None;self.progress_bar.setRange(0,100);self.progress_bar.setValue(0)
            self.stats_label.setText(f'当前歌手：{result.artist.name}；目录歌曲 {len(result.songs)}。尚未开始本次音源任务。')
            self.status_label.setText('已加载该歌手保存的来源查询结果。')
        self._render();self._controls()

    def search_songs(self,songs,mode='all'):
        if self.worker or self.catalog is None or not songs:return
        self._rendered=-1
        self.progress_bar.setRange(0,0)
        self.stats_label.setText('正在准备真实任务队列；总数尚未确定。')
        self.status_label.setText('准备查询快照和缓存，尚未开始本次来源搜索。')
        self.worker=SourceWorker(self.path,self.catalog.artist,list(songs),None,
            self.force_checkbox.isChecked(),mode,self,browser=self.browser_checkbox.isChecked())
        self.worker.progress.connect(self._progress);self.worker.completed.connect(self._complete);self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished);self._controls();self.worker.start()

    def _progress(self,stats):
        self.last_stats=stats
        total=stats['total'];self.progress_bar.setRange(0,max(total,1));self.progress_bar.setValue(stats['searched'] if total else 1)
        self.stats_label.setText(f"歌曲总数 {total} · 已搜索 {stats['searched']} · 有候选 {stats['found_songs']} · 已核实匹配来源 {stats['verified_sources']} · 文件许可已验证 {stats['license_verified']} / 待确认 {stats['license_unverified']} · 无结果 {stats['no_result']} · 失败 {stats['failed']} · 待处理 {stats['pending']} · {stats['percent']:.1f}%")
        self.status_label.setText(f"歌手：{stats.get('artist','')}；当前歌曲：{stats['current_song'] or '—'}；来源：{stats['current_provider'] or '—'}。{stats['message']}")
        if self._rendered!=stats['searched']:
            for job in stats['jobs']:self.jobs[job['song_id']]=job
            self._render();self._rendered=stats['searched']
        self.task_progress.emit(stats)

    def _complete(self,stats):
        self._progress(stats)
        skipped=sorted({p for j in stats['jobs'] for p in j['unconfigured']})
        self.status_label.setText(self.status_label.text()+f" 元数据HTTP请求 {stats['api_requests']} / 重试 {stats['retries']}，耗时{stats['elapsed_seconds']:.2f}秒。未配置来源：{', '.join(skipped) or '无'}。")
    def _failed(self,message):
        self.status_label.setText('任务失败：'+message);self.progress_bar.setRange(0,1);self.progress_bar.setValue(0)
    def _finished(self):
        old=self.worker;self.worker=None
        if old:old.deleteLater()
        if self.pending_catalog is not None:
            pending=self.pending_catalog;self.pending_catalog=None;self.set_catalog(pending)
        self._controls();self.workers_finished.emit()
    def cancel(self):
        if self.worker:self.worker.cancel()

    def _render(self):
        self.candidates=[{**candidate,'target_title':job.get('title',''),'target_song_id':sid} for sid,job in self.jobs.items() for candidate in job.get('candidates',[])]
        self.table.setRowCount(len(self.candidates))
        for row,c in enumerate(self.candidates):
            values=[c['target_title'],c['title'],c['performer'] or '演唱者未核实',c['provider'],f"{c['match_score']} · {c['match_status']}",c['license_status'],f"{c['version']} / {c['duration_seconds'] or '未知'}秒 / {c.get('file_format','')} / {c.get('file_size',0)}字节"]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value));item.setToolTip(str(value));self.table.setItem(row,col,item)
        states={sid:('已取消/待处理' if job.get('job_state') in {'pending','running','cancelled'} else '部分来源失败' if job.get('errors') and job.get('candidates') else '搜索失败' if job.get('errors') else
            '已核实来源' if job.get('verified_sources') else '候选待核对' if job.get('candidates') else '无结果（已缓存）') for sid,job in self.jobs.items()}
        self.statuses_changed.emit({'artist_mbid':self.catalog.artist.mbid if self.catalog else None,'states':states})
        if not self.candidates:self.details.setPlainText('暂无候选。无结果、失败和未配置来源会分别记录；不会伪造找到音频。')
        self._controls()
    def selected(self):
        row=self.table.currentRow();return self.candidates[row] if 0<=row<len(self.candidates) else None
    def _select(self):
        candidate=self.selected()
        if candidate:
            c=candidate
            self.details.setPlainText('\n'.join([
                f"目标歌曲：{c['target_title']}",f"候选标题：{c['title']}",f"演唱者：{c['performer'] or '未核实（上传者/作曲者不等于演唱者）'}",
                f"版本：{c['version']}；时长：{c['duration_seconds'] or '未知'}秒",f"匹配建议：{c['match_status']}（{c['match_score']}分，仅用于人工筛选）",
                *c['match_reasons'],f"授权状态：{c['license_status']}",f"核验原因：{c['license_reason']}",f"许可说明：{c['license_statement'] or '未提供'}",
                f"许可链接：{c['license_url'] or '未提供'}",f"原始网页：{c['page_url']}",
                '此页不下载。只有独立下载任务通过录音身份、完整性及许可审核后，才允许本地归档。']))
        self._controls()
    def _open(self):
        candidate=self.selected()
        if candidate and self._safe_link(candidate['page_url']):QDesktopServices.openUrl(QUrl(candidate['page_url']))
    @staticmethod
    def _safe_link(url):
        p=urlsplit(url)
        return p.scheme=='https' and p.hostname in {'archive.org','commons.wikimedia.org','www.jamendo.com','jamendo.com','ccmixter.org','freesound.org','www.freesound.org','openverse.org'} and not p.username and p.port in (None,443)
    def _inspect(self):
        candidate=self.selected()
        if self.browser_worker or not candidate:return
        self.browser_worker=BrowserCheckWorker(self.path,candidate['page_url'],self)
        self.browser_worker.completed.connect(self._browser_result)
        self.browser_worker.failed.connect(self.status_label.setText);self.browser_worker.finished.connect(self._browser_finished)
        self._controls();self.browser_worker.start()
    def _browser_result(self,data):
        self.details.setPlainText(f"原始网页：{data['url']}\n授权状态：{data['license_status']}\n核验原因：{data['reason']}\n公开页面的许可相关说明：\n{data['license_excerpt'] or '未找到明确授权说明。'}")
    def _browser_finished(self):
        old=self.browser_worker;self.browser_worker=None
        if old:old.deleteLater()
        self._controls();self.workers_finished.emit()
    def _controls(self):
        for b in (self.all_button,self.five_button,self.missing_button,self.retry_button):b.setEnabled(self.worker is None and self.catalog is not None)
        self.cancel_button.setEnabled(self.worker is not None)
        self.open_button.setEnabled(self.selected() is not None)
        self.inspect_button.setEnabled(self.browser_worker is None and self.selected() is not None and self.selected().get('provider')!='ccmixter')
        self.browser_cancel_button.setEnabled(self.browser_worker is not None)
        self.download_button.setEnabled(bool(self.selected() and self.selected().get('license_status')=='LICENSE_VERIFIED'))
