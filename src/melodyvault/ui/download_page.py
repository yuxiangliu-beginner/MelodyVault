"""Queue UI reads actual persisted counters, never simulated timer progress."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,Signal,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPlainTextEdit
from melodyvault.database.downloads import DownloadRepository
from melodyvault.downloads.manager import DownloadManager
from melodyvault.downloads.worker import DownloadWorker


class DownloadPage(QWidget):
    workers_finished=Signal()
    def __init__(self,path,parent=None):
        super().__init__(parent);self.repository=DownloadRepository(path);self.manager=DownloadManager(self.repository);self.worker=None;self.catalog=None;self._view=None
        try:self.manager.recover();recovery='中断任务已安全恢复为暂停；点击继续后重新核验'
        except Exception:recovery='队列可能正由另一进程处理；本窗口不会重复执行'
        layout=QVBoxLayout(self)
        self.mode=QLabel();layout.addWidget(self.mode)
        row=QHBoxLayout();layout.addLayout(row)
        self.enqueue_button=QPushButton('建立当前歌曲/歌手目录任务');self.start_button=QPushButton('开始任务');self.pause_all=QPushButton('暂停全部');self.resume_all=QPushButton('继续全部暂停任务');self.cancel_all=QPushButton('取消全部');self.retry_button=QPushButton('仅重试失败任务')
        for b in (self.enqueue_button,self.start_button,self.pause_all,self.resume_all,self.cancel_all,self.retry_button):row.addWidget(b)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['歌曲','歌手','来源','状态','字节进度 / 剩余时间','速度','操作 / 原因'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.pause_button=QPushButton('暂停所选');self.resume_button=QPushButton('继续所选');self.cancel_button=QPushButton('取消所选');self.evidence_button=QPushButton('查看授权与失败原因');self.folder_button=QPushButton('打开下载文件夹')
        for b in (self.pause_button,self.resume_button,self.cancel_button,self.evidence_button,self.folder_button):actions.addWidget(b)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(160);layout.addWidget(self.details)
        self.status=QLabel(recovery);self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.enqueue_button.clicked.connect(lambda:self.enqueue_catalog(self.catalog));self.start_button.clicked.connect(self.start)
        self.pause_all.clicked.connect(self.pause_tasks);self.cancel_all.clicked.connect(self._cancel_all);self.resume_all.clicked.connect(self._resume_all);self.retry_button.clicked.connect(lambda:self._launch('retry'))
        self.pause_button.clicked.connect(lambda:self._stop('PAUSED'));self.cancel_button.clicked.connect(lambda:self._stop('CANCELLED'));self.resume_button.clicked.connect(self._resume)
        self.evidence_button.clicked.connect(self._evidence);self.folder_button.clicked.connect(self._folder)
        self.table.itemSelectionChanged.connect(self._selection)
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()
    def set_catalog(self,result):self.catalog=result;self.enqueue_button.setEnabled(self.worker is None)
    def enqueue_catalog(self,catalog,source=None):
        if self.worker is not None or catalog is None:return
        self.catalog=catalog;self._launch('enqueue',catalog,source)
    def _launch(self,action='run',catalog=None,source=None):
        if self.worker:return
        worker=DownloadWorker(self.manager,action,catalog,source,self);self.worker=worker
        worker.completed.connect(self.status.setText);worker.failed.connect(self._failed);worker.finished.connect(self._finished)
        self.enqueue_button.setEnabled(False);self.start_button.setEnabled(False);self.retry_button.setEnabled(False);worker.start()
    def start(self):self._launch()
    def pause_tasks(self):
        if self.worker and self.worker.action=='enqueue':self.worker.request_stop('PAUSED')
        self.manager.stop_all('PAUSED')
    def _cancel_all(self):
        if self.worker and self.worker.action=='enqueue':self.worker.request_stop('CANCELLED')
        self.manager.stop_all('CANCELLED')
        if self.worker is None:self._launch('cleanup')
    def _failed(self,text):self.status.setText('任务未完成：'+text)
    def _finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        self.start_button.setEnabled(True);self.retry_button.setEnabled(True);self.enqueue_button.setEnabled(self.catalog is not None);self.refresh();self.workers_finished.emit()
    def selected(self):
        row=self.table.currentRow();item=self.table.item(row,0) if row>=0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None
    def _stop(self,action):
        jid=self.selected()
        if jid:self.manager.stop(jid,action);self.refresh()
    def _resume(self):
        jid=self.selected()
        if jid:self.manager.resume(jid)
        self.start()
    def _resume_all(self):
        self.manager.resume_all();self.start()
    def _selection(self):
        enabled=self.selected() is not None
        for b in (self.pause_button,self.resume_button,self.cancel_button,self.evidence_button):b.setEnabled(enabled)
    def _evidence(self):
        jid=self.selected()
        if not jid:return
        row=self.repository.get(jid);events=self.repository.evidence_rows(jid)
        c=row['candidate'];result=row['result']
        readable='\n'.join([f"状态：{row['state']} · {row['reason_code']} · {row['reason']}",
            f"歌曲：{row['target']['title']} / {row['target']['artist']['name']} · 版本：{row['target']['version']}",
            f"许可：{c.get('license_status','尚未核验')} · {c.get('license_name','')} · {c.get('license_url','')}",
            f"下载许可：{c.get('download_permission',False)}；私人保存许可：{c.get('personal_storage_permission',False)}",
            f"来源：{c.get('provider','')} · {c.get('source_page_url','')}",f"署名：{c.get('attribution','')}；条件：{'；'.join(c.get('restrictions',[]))}",
            f"核验依据：{'；'.join(c.get('verification_reason',[]))}",f"SHA-256：{result.get('sha256','未完成文件校验')}",f"本地文件：{result.get('path','尚未归档')}",
            '原始核验证据（已隐藏凭据）：'])
        self.details.setPlainText(readable+'\n'+json.dumps({'state':row['state'],'reason_code':row['reason_code'],'reason':row['reason'],'dry_run':bool(row['dry_run']),'candidate':c,'result':result,'evidence':events},ensure_ascii=False,indent=2))
    def _folder(self):QDesktopServices.openUrl(QUrl.fromLocalFile(self.repository.settings().directory))
    def save_settings(self,settings):
        # SettingsPage persists first and emits only on success.
        if self.worker:self.pause_tasks()
        self.refresh()
    def refresh(self):
        settings=self.repository.settings();self.mode.setText(('实际下载已开启' if settings.automatic_download else 'DRY-RUN · 自动下载关闭')+' · 只归档通过身份/完整性/许可核验的完整原始文件')
        rows=self.repository.rows();summary=self.repository.summary()
        self.summary.setText(f"任务总数 {summary['total']} · 验证归档完成 {summary['COMPLETED']} · 失败 {summary['FAILED']} · 跳过 {summary['SKIPPED']} · 就绪/dry-run {summary['READY']} · 排队 {summary['QUEUED']} · 暂停 {summary['PAUSED']} · 取消 {summary['CANCELLED']}。下方显示最近200项；跳过和许可不明不算成功。")
        if rows:
            batch=self.repository.summary(rows[0]['batch_id']);done=sum(batch[k] for k in ('COMPLETED','FAILED','SKIPPED','CANCELLED'))
            self.summary.setText(self.summary.text()+f" 最新批次已结束处理 {done}/{batch['total']}（{100*done/max(1,batch['total']):.1f}%）；实际归档{batch['COMPLETED']}项。")
        view=[(r['id'],r['updated_at']) for r in rows]
        if view==self._view:return
        selected=self.selected();self._view=view;self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            target=json.loads(row['target_json']);candidate=json.loads(row['candidate_json']);percent=100*row['bytes_received']/row['total_bytes'] if row['total_bytes'] else None
            if row['state']=='COMPLETED':percent=100.
            progress=f"{percent:.1f}%" if percent is not None else '总量未知'
            if percent is not None and percent>=100 and row['state']!='COMPLETED':progress+=' 字节/未归档'
            if row['eta'] is not None:progress+=f" / {row['eta']:.0f}秒"
            values=[target['title'],target['artist']['name'],candidate.get('provider',''),row['state']+(' · dry-run' if row['dry_run'] else ''),progress,f"{row['speed']/1024:.1f} KiB/s",row['reason_code']+' '+row['reason']]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value);self.table.setItem(i,j,item)
            self.table.item(i,0).setData(Qt.ItemDataRole.UserRole,row['id'])
            if row['id']==selected:self.table.selectRow(i)
        self.enqueue_button.setEnabled(self.catalog is not None and self.worker is None);self._selection()
