"""No website-provided code or blanket download approval controls."""
import json
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,QLabel,
    QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QProgressBar)
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.discovery.worker import DiscoveryWorker


class DiscoveryPage(QWidget):
    workers_finished=Signal()
    def __init__(self,path,parent=None):
        super().__init__(parent);self.path=path;self.repository=DiscoveryRepository(path);self.worker=None;self.rows=[];self._ended_early=False
        layout=QVBoxLayout(self)
        self.notice=QLabel('公开目录/百科外链发现；全网搜索 API 未配置时不抓取搜索引擎网页。发现网站不代表找到歌曲或具有下载权限。')
        self.notice.setWordWrap(True);layout.addWidget(self.notice)
        controls=QHBoxLayout();layout.addLayout(controls)
        self.artist=QLineEdit();self.artist.setPlaceholderText('歌手（可选）');self.title=QLineEdit();self.title.setPlaceholderText('歌曲（可选）')
        self.start_button=QPushButton('自动发现新网站');self.cancel_button=QPushButton('取消发现')
        for w in (self.artist,self.title,self.start_button,self.cancel_button):controls.addWidget(w)
        self.start_button.clicked.connect(self.start);self.artist.returnPressed.connect(self.start);self.title.returnPressed.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.progress=QProgressBar();self.progress.setRange(0,1);layout.addWidget(self.progress)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['网站 / 域名','审核','访问状态','可搜索','完整音频证据','下载许可','格式','启用'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.details);layout.addWidget(self.table,1)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.check_button=QPushButton('重新检查');self.enable_button=QPushButton('启用');self.disable_button=QPushButton('禁用')
        self.adapters_button=QPushButton('检查官方适配器');actions.addWidget(self.adapters_button)
        self.adapters_button.clicked.connect(lambda:self.launch(DiscoveryWorker(self.path,domain='__compiled__',parent=self)) if self.worker is None else None)
        for w in (self.check_button,self.enable_button,self.disable_button):actions.addWidget(w)
        self.check_button.clicked.connect(self.recheck);self.enable_button.clicked.connect(lambda:self.enable(True));self.disable_button.clicked.connect(lambda:self.enable(False))
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);layout.addWidget(self.detail)
        self.status=QLabel('准备就绪。新来源默认 PENDING_REVIEW；启用不会授予下载权限。');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.refresh()
    def refresh(self):
        selected=self.selected();domain=selected['domain'] if selected else None
        self.rows=self.repository.rows();self.table.setRowCount(len(self.rows))
        for i,row in enumerate(self.rows):
            cap=row['capabilities']
            for j,value in enumerate([row['name']+' / '+row['domain'],row['review_status'],row['state'],cap.get('chinese_search'),cap.get('full_audio'),cap.get('download_permission','LICENSE_UNVERIFIED'),','.join(cap.get('formats',[])),bool(row['enabled'])]):
                label='未核实' if value is None else '是' if value is True else '否' if value is False else str(value)
                item=QTableWidgetItem(label);item.setToolTip(label);self.table.setItem(i,j,item)
            if row['domain']==domain:self.table.selectRow(i)
        self.summary.setText(f"已发现 {len(self.rows)} · 已审核 {sum(r['review_status']=='APPROVED' for r in self.rows)} · 可访问 {sum(r['capabilities'].get('accessible') is True for r in self.rows)} · 中文搜索 {sum(r['capabilities'].get('chinese_search') is True for r in self.rows)} · 完整候选 {sum(r['capabilities'].get('full_audio') is True for r in self.rows)} · 文件授权通过来源 {sum(r['capabilities'].get('download_permission')=='DOWNLOAD_PERMISSION_VERIFIED' for r in self.rows)} · 失效 {sum(r['state']=='UNAVAILABLE' for r in self.rows)} · 待审核 {sum(r['review_status']=='PENDING_REVIEW' for r in self.rows)}")
        self.controls()
    def selected(self):
        i=self.table.currentRow();return self.rows[i] if 0<=i<len(self.rows) else None
    def details(self):
        row=self.selected()
        if row:
            cap=row['capabilities'];history=self.repository.history(row['domain'])
            self.detail.setPlainText('\n'.join([
                f"网站：{row['domain']} · {row['review_status']} · {row['state']}",
                f"调查原始链接：{row['first_url']}",f"支持格式（仅线索）：{', '.join(cap.get('formats',[])) or '未核实'}",
                f"授权：{cap.get('download_permission','LICENSE_UNVERIFIED')}；启用来源不会批准文件下载。",
                f"检查依据：{cap.get('reason') or cap.get('error') or '尚未检查'}",
                f"自动访问依据：{cap.get('automation_evidence','未核实')}",
                f"真实请求尝试 {row['attempts']} · 返回候选次数 {row['hits']} · 连续失败 {row['failures']}",
                '\n发现证据与检查历史（各最近 100 条）：',json.dumps(history,ensure_ascii=False,indent=2)]))
        self.controls()
    def enable(self,value):
        row=self.selected()
        if row:self.repository.set_enabled(row['domain'],value);self.refresh();self.details()
    def start(self):
        if self.worker:return
        if not (self.artist.text().strip() or self.title.text().strip()):self.status.setText('请输入歌手或歌曲。');return
        self.launch(DiscoveryWorker(self.path,self.artist.text().strip(),self.title.text().strip(),parent=self))
    def recheck(self):
        row=self.selected()
        if row and not self.worker:self.launch(DiscoveryWorker(self.path,domain=row['domain'],force=True,parent=self))
    def launch(self,worker):
        self.worker=worker;self._ended_early=False;self.progress.setRange(0,0);self.status.setText('后台执行真实来源调查…')
        worker.progress.connect(lambda e:self.status.setText(e['message']))
        worker.completed.connect(self.complete);worker.failed.connect(self.failed);worker.finished.connect(self.finished)
        self.controls();worker.start()
    def complete(self,result):
        if result.get('cancelled'):
            self._ended_early=True;message='已取消；已保存的调查记录保留。'
        elif 'domains' in result:
            message=f"本次发现 {result['discovered']} 个候选域名，检查 {result['checked']} 个，缓存查询 {result['cached_queries']} 个；请求 {result['api_requests']} / 重试 {result['retries']}，耗时 {result['elapsed_seconds']:.2f} 秒。{result['general_search']}。查询错误 {len(result['errors'])}。"
        elif 'sources' in result:message=f"官方适配器检查结束；请求 {result['api_requests']} / 重试 {result['retries']}。具体状态及原因见来源详情。"
        else:message=f"检查结束：{result.get('state','未知')}。{result.get('reason') or result.get('error') or '详细证据已保存。'}"
        self.status.setText(message);self.refresh();self.details()
    def failed(self,message):
        self._ended_early=True;self.status.setText('调查失败：'+message)
    def finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        self.progress.setRange(0,1);self.progress.setValue(0 if self._ended_early else 1);self.refresh();self.workers_finished.emit()
    def cancel(self):
        if self.worker:self.worker.cancel()
    def controls(self):
        self.start_button.setEnabled(self.worker is None);self.cancel_button.setEnabled(self.worker is not None)
        self.adapters_button.setEnabled(self.worker is None)
        for b in (self.check_button,self.enable_button,self.disable_button):b.setEnabled(self.worker is None and self.selected() is not None)
