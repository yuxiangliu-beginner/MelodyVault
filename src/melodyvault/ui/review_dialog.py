"""Local review UI. Evidence/replay/persistence run in a worker, never in paint slots."""
import threading
from PySide6.QtCore import QThread,Signal,Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,
    QTableWidget,QTableWidgetItem,QPlainTextEdit,QSplitter,QHeaderView,QAbstractItemView,QTabWidget,QWidget)
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.catalog.grouping import version_kind
from melodyvault.catalog.review import ReviewService,suggestions
from melodyvault.database.catalog import CatalogRepository


class ReviewWorker(QThread):
    ready=Signal(object)
    failed=Signal(str)
    progress=Signal(str)
    def __init__(self,path,artist,operation='load',arguments=None,actor='local_user',parent=None):
        super().__init__(parent);self.path=path;self.artist=artist;self.operation=operation
        self.arguments=arguments or {};self.actor=actor;self.cancel_event=threading.Event()
    def run(self):
        try:
            repo=CatalogRepository(self.path);service=ReviewService(repo,self.actor)
            if self.operation=='enrich':
                from melodyvault.catalog.musicbrainz import MusicBrainzClient
                from melodyvault.catalog.evidence import enrich_artist
                with MusicBrainzClient(repo,self.cancel_event) as client:
                    enrich_artist(repo,client,self.artist,lambda p:self.progress.emit(p.message))
                snapshot=service.load(self.artist)
            elif self.operation=='decide':snapshot=service.decide(self.artist,**self.arguments)
            else:snapshot=service.load(self.artist)
            self.ready.emit(snapshot)
        except CatalogCancelled as error:self.failed.emit(str(error))
        except Exception as error:self.failed.emit(f'{type(error).__name__}: {error}')


class ReviewDialog(QDialog):
    catalog_changed=Signal(object)
    def __init__(self,path,artist,parent=None,source_song_id=None,actor='local_user'):
        super().__init__(parent);self.path=path;self.artist=artist;self.actor=actor
        self.worker=None;self.snapshot=None;self.candidates=[];self.sources=[];self._close_pending=False
        self._preferred_source=source_song_id
        self.setWindowTitle(f'待确认作品审核 · {artist.name}');self.resize(1180,780)
        layout=QVBoxLayout(self)
        notice=QLabel('建议不是事实：标题/时长等弱证据不会自动归并。手动合并只改变作品分组，保留现场、重录等全部 Recording；所有决定可撤销并保留审计。')
        notice.setWordWrap(True);layout.addWidget(notice)
        self.stats_label=QLabel('正在读取审核数据……');self.stats_label.setWordWrap(True);layout.addWidget(self.stats_label)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        review_page=QWidget();review_layout=QVBoxLayout(review_page);self.tabs.addTab(review_page,'待确认与已审核')
        self.filter_input=QLineEdit();self.filter_input.setPlaceholderText('筛选源歌曲名称（包含已人工审核条目）');self.filter_input.textChanged.connect(self._fill_sources)
        review_layout.addWidget(self.filter_input)
        splitter=QSplitter();review_layout.addWidget(splitter,1)
        self.source_table=self._table(['源条目','状态','版本数']);splitter.addWidget(self.source_table)
        self.candidate_table=self._table(['建议归并对象','置信度','主要依据']);splitter.addWidget(self.candidate_table)
        splitter.setSizes([420,700])
        self.source_table.itemSelectionChanged.connect(self._select_source)
        self.candidate_table.itemSelectionChanged.connect(self._select_candidate)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(175);review_layout.addWidget(self.details)
        self.reason_input=QLineEdit();self.reason_input.setPlaceholderText('填写审核理由（确认、拒绝和独立均写入审计）');review_layout.addWidget(self.reason_input)
        row=QHBoxLayout();review_layout.addLayout(row)
        self.merge_button=QPushButton('确认合并');self.reject_button=QPushButton('拒绝此建议');self.independent_button=QPushButton('保持独立')
        for button,action in ((self.merge_button,'merge'),(self.reject_button,'reject'),(self.independent_button,'independent')):
            row.addWidget(button);button.clicked.connect(lambda checked=False,a=action:self._decide(a))
        history_page=QWidget();history_layout=QVBoxLayout(history_page);self.tabs.addTab(history_page,'审计历史与撤销')
        self.history_table=self._table(['时间','动作','理由','当前状态','操作者']);history_layout.addWidget(self.history_table)
        self.history_table.itemSelectionChanged.connect(self._controls)
        self.undo_reason_input=QLineEdit();self.undo_reason_input.setPlaceholderText('撤销理由（可选；留空记录为用户撤销决定）');history_layout.addWidget(self.undo_reason_input)
        self.undo_button=QPushButton('撤销选中决定（保留原事件）');self.undo_button.clicked.connect(self._undo);history_layout.addWidget(self.undo_button)
        note=QLabel('撤销会重新播放剩余历史；依赖被撤销合并的后续决定若目标已拆分，将标记需重审，不会重新合并已撤销的记录。新证据冲突也不会被旧决定强行覆盖。')
        note.setWordWrap(True);history_layout.addWidget(note)
        bottom=QHBoxLayout();layout.addLayout(bottom)
        self.reload_button=QPushButton('刷新审核列表');self.enrich_button=QPushButton('补充待确认证据');self.cancel_button=QPushButton('取消补证/任务');self.close_button=QPushButton('关闭')
        for button in (self.reload_button,self.enrich_button,self.cancel_button,self.close_button):bottom.addWidget(button)
        self.reload_button.clicked.connect(lambda:self._start('load'))
        self.enrich_button.clicked.connect(self._request_enrichment)
        self.cancel_button.clicked.connect(self._cancel);self.close_button.clicked.connect(self.close)
        self.status_label=QLabel('正在加载……');self.status_label.setTextFormat(Qt.TextFormat.PlainText);self.status_label.setWordWrap(True);layout.addWidget(self.status_label)
        self._controls();QTimer.singleShot(0,lambda:self._start('load'))

    @staticmethod
    def _table(headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _request_enrichment(self):
        parent=self.parent()
        if parent is not None and hasattr(parent,'start_evidence'):
            self.accept();parent.start_evidence()
        else:self._start('enrich')

    def _start(self,operation,arguments=None):
        if self.worker is not None:return
        self.status_label.setText('正在后台处理；原始录音不会删除。')
        worker=ReviewWorker(self.path,self.artist,operation,arguments,self.actor,self)
        self.worker=worker;worker.ready.connect(self._loaded);worker.failed.connect(self.status_label.setText)
        worker.progress.connect(self.status_label.setText);worker.finished.connect(self._finished)
        self._controls();worker.start()

    def _loaded(self,snapshot):
        self.snapshot=snapshot
        summary=snapshot['result'].summary
        self.stats_label.setText(f"已核实/人工确认作品 {summary['independent_song_count']} · 待确认 {summary['pending_song_count']}项 · 已人工审核 {summary['manually_reviewed_item_count']}项/{summary['manually_reviewed_recording_count']}录音 · 版本 {summary['version_count']} · 需重审历史 {summary['stale_review_count']}")
        self._fill_sources();self._fill_history()
        self.status_label.setText('已加载。请核对版本、Work、演唱者和证据后作决定；无可靠证据可保持独立。')
        self.catalog_changed.emit(snapshot['result'])

    def _fill_sources(self):
        if not self.snapshot:return
        query=self.filter_input.text().casefold().strip()
        self.sources=[s for s in self.snapshot['result'].songs if (s.pending_confirmation or s.reviewed) and query in s.title.casefold()]
        self.source_table.blockSignals(True);self.source_table.setRowCount(len(self.sources))
        for row,song in enumerate(self.sources):
            values=[song.title,('待确认' if song.pending_confirmation else '人工确认')+(' · 已审核' if song.reviewed else ''),str(len(song.recordings))]
            for column,value in enumerate(values):self.source_table.setItem(row,column,QTableWidgetItem(value))
        self.source_table.blockSignals(False)
        if self.sources:
            preferred=next((i for i,s in enumerate(self.sources) if s.id==self._preferred_source),0)
            self.source_table.selectRow(preferred)
            self._select_source()
        else:self.candidate_table.setRowCount(0);self.candidates=[];self.details.setPlainText('没有符合筛选条件的待确认条目。')
        self._controls()

    def _source(self):
        row=self.source_table.currentRow()
        return self.sources[row] if 0<=row<len(self.sources) else None

    def _candidate(self):
        row=self.candidate_table.currentRow()
        return self.candidates[row] if 0<=row<len(self.candidates) else None

    def _select_source(self):
        source=self._source()
        if source is None:return
        self._preferred_source=source.id
        self.candidates=suggestions(self.artist,source,self.snapshot['result'].songs,self.snapshot['works'])
        self.candidate_table.blockSignals(True);self.candidate_table.setRowCount(len(self.candidates))
        for row,candidate in enumerate(self.candidates):
            for col,value in enumerate((candidate['target_title'],candidate['confidence'],'；'.join(candidate['reasons']))):
                item=QTableWidgetItem(value);item.setToolTip(value);self.candidate_table.setItem(row,col,item)
        self.candidate_table.blockSignals(False)
        if self.candidates:self.candidate_table.selectRow(0)
        self._select_candidate()

    def _select_candidate(self):
        source=self._source();candidate=self._candidate();lines=[]
        if source:
            lines=[f'源：{source.title}',f'Work：{", ".join(source.work_ids) or "尚无明确关联"}']
            for recording in source.recordings:
                performers=' / '.join(f"{c.get('name') or c.get('artist',{}).get('name','')} [{c.get('artist',{}).get('id','')}]" for c in recording.credits if isinstance(c,dict))
                lines.append(f'{recording.mbid} | {recording.original_title} | {version_kind(recording)[0]} | 时长 {recording.length_ms}ms | ISRC {", ".join(set(recording.payload.get("isrcs",[]))|set(recording.details.get("isrcs",[]))) or "缺失"} | 演唱者 {performers}')
                for context in recording.contexts[:3]:
                    lines.append(f"  发行曲目关联 {context['release_mbid']} / 介质{context.get('medium_position')} / 曲目{context.get('position')}")
        if candidate:
            target=next(s for s in self.snapshot['result'].songs if s.id==candidate['target_song_id'])
            lines += ['','建议：'+candidate['target_title'],'目标Work：'+(', '.join(target.work_ids) or '尚无明确关联'),'置信度：'+candidate['confidence'],*candidate['reasons'],candidate['warning']]
            for recording in target.recordings:
                performers=' / '.join(c.get('name') or c.get('artist',{}).get('name','') for c in recording.credits if isinstance(c,dict))
                lines.append(f'  目标版本 {recording.mbid} | {version_kind(recording)[0]} | 演唱者 {performers}')
        else:lines+=['','暂无建议。没有可靠对象时可保持独立，不能按同名强制合并。']
        self.details.setPlainText('\n'.join(lines));self._controls()

    def _fill_history(self):
        events=list(reversed(self.snapshot['events']));self._history=events
        self.history_table.setRowCount(len(events))
        names={'merge':'确认合并','reject':'拒绝建议','independent':'保持独立','undo':'撤销'}
        for row,event in enumerate(events):
            status=self.snapshot['statuses'].get(event['id'],{})
            values=[event['created_at'],names[event['action']],event['reason'],status.get('status','')+' · '+status.get('message',''),event['actor']]
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value+'\nEvent ID: '+event['id']);self.history_table.setItem(row,column,item)

    def _decide(self,action):
        source=self._source();candidate=self._candidate()
        if source is None:return
        self._start('decide',{'action':action,'source_song_id':source.id,'target_song_id':candidate['target_song_id'] if candidate else None,'reason':self.reason_input.text()})

    def _undo(self):
        row=self.history_table.currentRow()
        if row<0 or row>=len(getattr(self,'_history',[])):return
        self._start('decide',{'action':'undo','undo_of':self._history[row]['id'],'reason':self.undo_reason_input.text().strip() or '用户撤销审核决定'})

    def _cancel(self):
        if self.worker:
            if self.worker.operation=='enrich':
                self.worker.cancel_event.set();self.status_label.setText('已请求取消补证；当前HTTP请求结束后退出，成功项可恢复。')
            else:self.status_label.setText('正在完成本地审核事务，结束后关闭；已保存决定可在历史中撤销。')

    def _finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        self._controls()
        if self._close_pending:self.close()

    def _controls(self):
        busy=self.worker is not None;source=self._source();candidate=self._candidate()
        self.source_table.setEnabled(not busy);self.candidate_table.setEnabled(not busy)
        self.merge_button.setEnabled(not busy and source is not None and candidate is not None and candidate['allowed'])
        self.reject_button.setEnabled(not busy and source is not None and candidate is not None)
        self.independent_button.setEnabled(not busy and source is not None)
        self.reload_button.setEnabled(not busy);self.enrich_button.setEnabled(not busy);self.cancel_button.setEnabled(busy and self.worker.operation=='enrich')
        row=self.history_table.currentRow();history=getattr(self,'_history',[])
        undoable=0<=row<len(history) and history[row]['action']!='undo' and self.snapshot is not None and self.snapshot['statuses'].get(history[row]['id'],{}).get('status') not in {'undone','undo'}
        self.undo_button.setEnabled(not busy and undoable)

    def closeEvent(self,event):
        if self.worker:
            self._close_pending=True;self._cancel();event.ignore();return
        super().closeEvent(event)

    def reject(self):
        if self.worker:
            self._close_pending=True;self._cancel();return
        super().reject()

    def accept(self):
        if self.worker:
            self._close_pending=True;self._cancel();return
        super().accept()
