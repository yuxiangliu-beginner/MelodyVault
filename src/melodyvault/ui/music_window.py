"""User-facing shell; the original catalog/review UI remains in main_window.py."""
import json, threading, shutil, os
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from PySide6.QtCore import QThread,Signal,Qt,QTimer,QUrl,QProcess
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,
    QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QLabel,QTreeWidget,QTreeWidgetItem,
    QDialog,QFormLayout,QCheckBox,QFileDialog,QDialogButtonBox,QComboBox)
from melodyvault.database import connect
from melodyvault.database.downloads import DownloadRepository
from melodyvault.downloads.manager import DownloadManager
from melodyvault.search.platforms import PlatformSearchService
from melodyvault.catalog.models import CatalogCancelled

class MusicTask(QThread):
    completed=Signal(object);failed=Signal(str);notice=Signal(str)
    def __init__(self,path,query=None,song=None,parent=None):
        super().__init__(parent);self.path=path;self.query=query;self.song=song;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            if self.song is None:self.completed.emit(PlatformSearchService(self.path,self.cancel_event).search(self.query));return
            from melodyvault.sources.models import SourceQuery
            from melodyvault.sources.engine import SourceSearchEngine
            from melodyvault.sources.worker import default_providers
            from melodyvault.database.sources import SourceRepository
            from melodyvault.downloads.fallback import SourceFallbackManager
            from melodyvault.search.orchestrator import UnifiedCandidate
            s=self.song;artist=SimpleNamespace(mbid=s['source']+':'+s['artist'],name=s['artist'])
            q=SourceQuery(artist.mbid,s['source']+':'+s['song_id'],s['artist'],s['title'],[s['artist']],[s['title']],
                          [s['version']], [int(s['duration']*1000)] if s['duration'] else [],[])
            self.notice.emit('正在查找可下载音源…')
            repo=DownloadRepository(self.path);settings=replace(repo.settings(),automatic_download=True)
            with connect(self.path) as db:flag=db.execute("SELECT value FROM app_metadata WHERE key='ui.auto_fallback'").fetchone()
            fallback_enabled=not flag or flag[0]!='false'
            target={'song_id':q.song_id,'recording_id':s['source']+':'+s['song_id'],'namespace':s['source'],
                'artist':{'id':artist.mbid,'name':s['artist']},'title':s['title'],'version':s['version'],
                'duration':s['duration'],'confirmed':True,'urls':[s['source_url']],'work_ids':[]}
            if s['source']=='commons':target.update(namespace='commons',recording_id='commons:'+s['song_id'],source_page_url=s['source_url'])
            from melodyvault.search.recording_bridge import linked_recording
            linked=linked_recording(self.path,s)
            if linked:target.update(linked)
            def progress(e):
                self.notice.emit('下载中：'+str(e.get('bytes_received',0))+' 字节' if e['stage']=='download_progress' else '正在检查可下载音源…')
            self.manager=DownloadManager(repo)
            import logging
            runner=SourceFallbackManager(repo,self.manager,self.cancel_event,progress,lambda e:logging.getLogger(__name__).info('source attempt %s: %s %s',e.get('source'),e.get('state'),e.get('reason_code','')))
            attempts=[];errors={}
            if s['source']=='commons':
                from dataclasses import asdict
                from melodyvault.providers.commons import CommonsProvider
                from melodyvault.sources.http import SourceHTTP
                from melodyvault.sources.matching import match_candidate
                try:
                    with SourceHTTP(self.cancel_event) as http:
                        found=CommonsProvider().get_metadata(s['song_id'],http)
                    candidates=[UnifiedCandidate(c.provider,c.page_url,c.title,match_score=100,raw_source=asdict(match_candidate(q,c))) for c in found]
                    attempts=runner.run(target,candidates,settings)
                except CatalogCancelled:raise
                except Exception as error:errors['commons']=str(error)
                if attempts and attempts[-1]['state'] in {'COMPLETED','READY','PAUSED','CANCELLED'} or not fallback_enabled:
                    self.completed.emit({'download':True,'attempts':attempts,'candidates':[],'errors':errors});return
            stats=SourceSearchEngine(SourceRepository(self.path),default_providers(),self.cancel_event).search_queries(artist,[q])
            if self.cancel_event.is_set():raise CatalogCancelled('cancelled')
            raw=stats['jobs'][0]['candidates']; candidates=[UnifiedCandidate(c['provider'],c['page_url'],c['title'],match_score=c['match_score'],raw_source=c) for c in raw if not (c['provider']==s['source'] and c['external_id']==s['song_id'] and s['source']=='commons')]
            if not fallback_enabled:candidates=sorted(candidates,key=lambda c:-c.match_score)[:1]
            attempts+=runner.run(target,candidates,settings);errors.update(stats['jobs'][0]['errors'])
            self.completed.emit({'download':True,'attempts':attempts,'candidates':raw,'errors':errors})
        except CatalogCancelled:self.failed.emit('任务已取消。')
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception('Music task failed')
            self.failed.emit('查询未完成，请检查网络或稍后重试。')

class MusicWindow(QMainWindow):
    def __init__(self,path):
        super().__init__();self.path=path;self.repo=DownloadRepository(path);self.worker=None;self.songs=[]
        try:DownloadManager(self.repo).recover()
        except Exception:pass  # another process may own the queue lock
        try:
            from melodyvault.library.imports import recover_imports
            recover_imports(path)
        except Exception:pass  # an import may be running in another window
        self.setWindowTitle('MelodyVault');self.resize(1020,700)
        root=QWidget();outer=QVBoxLayout(root);bar=QHBoxLayout();bar.addWidget(QLabel('MelodyVault'));bar.addStretch()
        settings=QPushButton('设置');settings.clicked.connect(self.settings);bar.addWidget(settings);outer.addLayout(bar)
        self.tabs=QTabWidget();outer.addWidget(self.tabs);self.setCentralWidget(root)
        search=QWidget();layout=QVBoxLayout(search);row=QHBoxLayout();self.input=QLineEdit();self.input.setPlaceholderText('搜索歌曲或歌手，例如：周杰伦 晴天')
        self.search_button=QPushButton('搜索');self.cancel_button=QPushButton('取消');self.cancel_button.setEnabled(False)
        row.addWidget(self.input,1);row.addWidget(self.search_button);row.addWidget(self.cancel_button);layout.addLayout(row)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['歌曲','歌手','时长','操作']);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header=self.table.horizontalHeader();header.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed);header.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(2,75);self.table.setColumnWidth(3,95);layout.addWidget(self.table)
        self.status=QLabel('搜索音乐平台，选择歌曲后查找可下载音源。');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.tabs.addTab(search,'音乐搜索');self.search_button.clicked.connect(self.search);self.input.returnPressed.connect(self.search);self.cancel_button.clicked.connect(self.cancel)
        history=QWidget();hl=QVBoxLayout(history);self.filter=QLineEdit();self.filter.setPlaceholderText('搜索我的音乐');hl.addWidget(self.filter)
        import_button=QPushButton('导入音乐');import_button.clicked.connect(self.import_music);hl.addWidget(import_button)
        self.history=QTreeWidget();self.history.setHeaderLabels(['歌手 / 歌曲','格式','状态 / 进度','文件位置']);self.history.setColumnWidth(0,250);self.history.setColumnWidth(1,80);self.history.setColumnWidth(2,140);hl.addWidget(self.history)
        actions=QHBoxLayout();hl.addLayout(actions)
        for label,fn in [('打开所在文件夹',self.folder),('重试 / 继续',self.retry),('取消任务',self.cancel_history)]:
            b=QPushButton(label);b.clicked.connect(fn);actions.addWidget(b)
        self.tabs.addTab(history,'我的音乐');self.filter.textChanged.connect(self.refresh_history)
        self.video=VideoPage(self.repo);self.tabs.addTab(self.video,'媒体转换')
        self.video.process.finished.connect(lambda:QTimer.singleShot(0,self.close) if getattr(self,'_close_requested',False) else None)
        self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.refresh_history);self.timer.start();self.refresh_history()
    def launch(self,worker,callback):
        if self.worker:return
        self.worker=worker;self.search_button.setEnabled(False);self.cancel_button.setEnabled(True)
        worker.completed.connect(callback);worker.failed.connect(self.status.setText);worker.notice.connect(self.status.setText);worker.finished.connect(self.finished);worker.start()
    def finished(self):
        w=self.worker;self.worker=None
        if w:w.deleteLater()
        self.search_button.setEnabled(True);self.cancel_button.setEnabled(False);self.refresh_history()
        if getattr(self,'active_download_button',None):
            self.active_download_button.setEnabled(True)
            if self.active_download_button.text() in ('查找中','下载中'):self.active_download_button.setText('重试')
            self.active_download_button=None
        if getattr(self,'_close_requested',False):QTimer.singleShot(0,self.close)
    def cancel(self):
        if self.worker:
            if hasattr(self.worker,'cancel'):self.worker.cancel()
            self.status.setText('正在取消…')
    def search(self):
        if self.worker or not self.input.text().strip():return
        self.status.setText('正在搜索音乐平台…');self.launch(MusicTask(self.path,query=self.input.text(),parent=self),self.results)
    def results(self,result):
        self.songs=result['rows'];self.table.setRowCount(len(self.songs));self.active_download_button=None
        for i,s in enumerate(self.songs):
            duration=f"{int(s['duration'])//60}:{int(s['duration'])%60:02d}" if s['duration'] else '--:--'
            label=s['title']+({'instrumental':'（演奏版）','cover':'（翻唱）','live':'（现场）','remix':'（混音）'}.get(s['version'],'') if s['source']=='commons' else '')
            for j,v in enumerate([label,s['artist'],duration]):
                item=QTableWidgetItem(v);item.setToolTip(v);self.table.setItem(i,j,item)
            b=QPushButton('下载');b.clicked.connect(lambda checked=False,s=s,b=b:self.download(s,b));self.table.setCellWidget(i,3,b)
        self.status.setText(f"找到 {len(self.songs)} 条歌曲信息；选择目标后可查找可下载音源。")
        if any(v.get('status')=='FAILED' for v in result['statuses'].values()):
            self.status.setText('部分音乐平台查询失败，已显示可用结果。' if self.songs else '音乐平台查询失败，请稍后重试。')
    def download(self,s,button=None):
        if not self.worker:
            self.active_download_button=button
            if button:button.setText('查找中');button.setEnabled(False)
            task=MusicTask(self.path,song=s,parent=self)
            if button:task.notice.connect(lambda text:button.setText('下载中' if text.startswith('下载中') else '查找中'))
            self.launch(task,self.download_done)
    def download_done(self,r):
        if r['attempts'] and r['attempts'][-1]['state'] in {'CANCELLED','PAUSED'}:
            if self.active_download_button:self.active_download_button.setText('重试')
            self.status.setText('任务已取消。' if r['attempts'][-1]['state']=='CANCELLED' else '任务已暂停。')
            self.refresh_history();return
        completed=next((a for a in r['attempts'] if a['state']=='COMPLETED'),None)
        if completed:
            if self.active_download_button:self.active_download_button.setText('已完成')
            path=self.repo.get(completed['job_id'])['result']['path'];self.status.setText('下载完成：'+path)
            with connect(self.path) as db:flag=db.execute("SELECT value FROM app_metadata WHERE key='ui.auto_open'").fetchone()
            if flag and flag[0]=='true':QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
        else:
            if self.active_download_button:self.active_download_button.setText('重试' if r['errors'] or any(a['state']=='FAILED' for a in r['attempts']) else '不可下载')
            self.status.setText('暂时没有可下载的音源。'+(' 部分来源查询失败，可稍后重试。' if r['errors'] else ''))
            self.status.setToolTip('\n'.join(c['page_url']+' · '+c.get('license_reason','') for c in r['candidates']))
    def refresh_history(self):
        selected=self.history.currentItem();key=selected.data(0,Qt.ItemDataRole.UserRole) if selected else None
        expanded={self.history.topLevelItem(i).text(0) for i in range(self.history.topLevelItemCount()) if self.history.topLevelItem(i).isExpanded()}
        with connect(self.path) as db:
            rows=db.execute('SELECT id,state,target_json,result_json,candidate_json,bytes_received,total_bytes,reason FROM download_jobs ORDER BY created_at DESC').fetchall()
            imported=db.execute('SELECT * FROM personal_music ORDER BY created_at DESC').fetchall()
        self.history.clear();groups={};q=self.filter.text().casefold()
        labels={'COMPLETED':'已完成','FAILED':'下载失败','SKIPPED':'未找到可下载文件','CANCELLED':'已取消','PAUSED':'已暂停','QUEUED':'等待中','READY':'等待开始','DOWNLOADING':'下载中','SEARCHING':'查找中','VERIFYING':'检查中'}
        for r in imported:
            artist=r['artist'] or '未知歌手';title=r['title'];path=r['path']
            if q and q not in (artist+' '+title).casefold():continue
            if artist not in groups:
                groups[artist]=QTreeWidgetItem(self.history,[artist]);groups[artist].setExpanded(artist in expanded or not getattr(self,'_history_initialized',False))
            item=QTreeWidgetItem(groups[artist],[title,r['format'],'已完成' if Path(path).is_file() else '文件不存在',path]);item.setData(0,Qt.ItemDataRole.UserRole,{'library_path':path});item.setToolTip(0,path)
            if key=={'library_path':path}:self.history.setCurrentItem(item)
        for r in rows:
            t=json.loads(r['target_json']);out=json.loads(r['result_json']);c=json.loads(r['candidate_json']);artist=t.get('artist',{}).get('name') or '未知歌手';title=t.get('title','')
            if t.get('namespace')=='local_video' and r['state']=='COMPLETED':continue
            if t.get('namespace')=='local_import' and r['state'] in {'COMPLETED','SKIPPED'}:continue
            if q and q not in (artist+' '+title).casefold():continue
            group=artist if r['state']=='COMPLETED' else '未完成任务'
            if group not in groups:
                groups[group]=QTreeWidgetItem(self.history,[group]);groups[group].setExpanded(group in expanded or not getattr(self,'_history_initialized',False))
            state=labels.get(r['state'],'处理中');p=out.get('path','')
            if r['state']=='COMPLETED' and not Path(p).is_file():state='文件不存在'
            if r['total_bytes'] and r['state']!='COMPLETED':state+=f" {100*r['bytes_received']/r['total_bytes']:.0f}%"
            item=QTreeWidgetItem(groups[group],[title,out.get('format') or c.get('file_format',''),state,p]);item.setData(0,Qt.ItemDataRole.UserRole,r['id']);item.setToolTip(0,p or r['reason'])
            if r['id']==key:self.history.setCurrentItem(item)
        self._history_initialized=True
    def selected_job(self):
        item=self.history.currentItem();key=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        return self.repo.get(key) if key and not isinstance(key,dict) else None
    def folder(self):
        item=self.history.currentItem();data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if isinstance(data,dict):QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(data['library_path']).parent)));return
        r=self.selected_job()
        if r and r['result'].get('path'):QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(r['result']['path']).parent)))
    def retry(self):
        r=self.selected_job()
        if not r or self.worker:return
        if r['state'] not in {'FAILED','PAUSED','READY'}:return
        if r['target'].get('namespace')=='local_import':
            source=r['target'].get('source_path','')
            if not source or not Path(source).is_file():self.status.setText('原音乐文件不存在，无法重新导入。');return
            from melodyvault.ui.import_dialog import ImportDialog
            dialog=ImportDialog(self.repo,self,[source]);dialog.exec();self.refresh_history();return
        if r['target'].get('namespace')=='local_video':
            source=r['target'].get('remote_source_url') or r['target'].get('local_video_path','')
            if not source or not source.startswith('https://') and not Path(source).is_file():self.status.setText('原视频文件不存在，无法重新转换。');return
            self.tabs.setCurrentWidget(self.video);self.video.input.setText(source);self.video.convert();return
        from melodyvault.downloads.worker import DownloadWorker
        manager=DownloadManager(self.repo)
        if r['state']=='READY' and r['dry_run']:
            jid=self.repo.enqueue(r['target'],replace(self.repo.settings(),automatic_download=True),candidate=r['target'].get('source_hint'))
            r=self.repo.get(jid)
        if r['state']=='FAILED':self.repo.update(r['id'],state='QUEUED',reason_code='',reason='等待重试',attempt_count=0)
        else:manager.resume(r['id'])
        # Explicit task ID isolates other queued jobs.
        class Retry(QThread):
            def cancel(inner):manager.stop(r['id'],'CANCELLED')
            def run(inner):manager.run(job_ids=[r['id']])
        self.retry_manager=manager;self.retry_id=r['id'];self.worker=Retry(self);self.worker.finished.connect(self.finished);self.worker.start()
    def cancel_history(self):
        r=self.selected_job()
        if r:
            if r['target'].get('namespace')=='local_video' and r['id']==getattr(self.video,'jid',None) and self.video.process.state()!=QProcess.ProcessState.NotRunning:
                self.video.cancel();return
            manager=getattr(self.worker,'manager',None) or (getattr(self,'retry_manager',None) if r['id']==getattr(self,'retry_id',None) else None)
            (manager or DownloadManager(self.repo)).stop(r['id'],'CANCELLED');self.refresh_history()
    def settings(self):
        d=QDialog(self);d.setWindowTitle('设置');form=QFormLayout(d);directory=QLineEdit(self.repo.settings().directory);choose=QPushButton('选择');row=QHBoxLayout();row.addWidget(directory);row.addWidget(choose)
        choose.clicked.connect(lambda:directory.setText(QFileDialog.getExistingDirectory(d,'下载目录',directory.text()) or directory.text()));form.addRow('下载目录',row)
        fallback=QCheckBox('自动换源');auto=QCheckBox('完成后打开文件夹')
        with connect(self.path) as db:flags=dict(db.execute("SELECT key,value FROM app_metadata WHERE key LIKE 'ui.%'").fetchall())
        fallback.setChecked(flags.get('ui.auto_fallback','true')=='true');auto.setChecked(flags.get('ui.auto_open','false')=='true');form.addRow(fallback);form.addRow(auto)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject)
        if d.exec():
            try:
                self.repo.save_settings(replace(self.repo.settings(),directory=directory.text().strip()))
                with connect(self.path) as db:
                    for k,v in [('ui.auto_fallback',fallback.isChecked()),('ui.auto_open',auto.isChecked())]:db.execute('INSERT OR REPLACE INTO app_metadata(key,value) VALUES (?,?)',(k,json.dumps(v)))
            except ValueError:self.status.setText('设置未保存：请选择有效的绝对路径。')
    def import_music(self):
        from melodyvault.ui.import_dialog import ImportDialog
        dialog=ImportDialog(self.repo,self);dialog.exec();self.refresh_history()
    def closeEvent(self,event):
        if self.worker:self._close_requested=True;self.cancel();event.ignore();return
        if self.video.remote_worker:self._close_requested=True;self.video.cancel();event.ignore();return
        if self.video.process.state()!=QProcess.ProcessState.NotRunning:self._close_requested=True;self.video.cancel();event.ignore();return
        event.accept()

class VideoPage(QWidget):
    def __init__(self,repo):
        super().__init__();self.repo=repo;self.process=QProcess(self);layout=QVBoxLayout(self)
        layout.addWidget(QLabel('媒体转换 · 请选择你有权提取和保存的文件'))
        self.input=QLineEdit();self.input.setPlaceholderText('本地视频路径或 Wikimedia Commons 视频网址');layout.addWidget(self.input)
        choose=QPushButton('选择本地文件');choose.clicked.connect(lambda:self.input.setText(QFileDialog.getOpenFileName(self,'选择音视频')[0] or self.input.text()));layout.addWidget(choose)
        self.output_format=QComboBox();self.output_format.addItems(['MP3','WAV']);layout.addWidget(self.output_format)
        self.join_library=QCheckBox('转换后选择加入我的音乐');layout.addWidget(self.join_library)
        layout.addWidget(QLabel('MP3 转 WAV 不会恢复已损失的音质。'))
        self.start=QPushButton('开始转换');layout.addWidget(self.start);self.start.clicked.connect(self.convert)
        cancel=QPushButton('取消');cancel.clicked.connect(self.cancel);layout.addWidget(cancel)
        self.remote_worker=None;self.remote_temp=None;self.output_root=None
        choose_dir=QPushButton('选择输出目录');choose_dir.clicked.connect(self.choose_output);layout.addWidget(choose_dir)
        open_dir=QPushButton('打开输出文件夹');open_dir.clicked.connect(self.open_folder);layout.addWidget(open_dir)
        self.status=QLabel('网址支持 Wikimedia Commons 可核验 CC0 视频文件页或原始文件。');self.status.setWordWrap(True);layout.addWidget(self.status);layout.addStretch()
        self.process.finished.connect(self.done);self.process.errorOccurred.connect(self.process_error)
        self.process.readyReadStandardOutput.connect(self.conversion_progress)
        self.progress_buffer=''
    def conversion_progress(self):
        self.progress_buffer+=bytes(self.process.readAllStandardOutput()).decode('utf8','replace')
        lines=self.progress_buffer.split('\n');self.progress_buffer=lines.pop()
        for line in lines:
            if line.startswith('out_time='):self.status.setText('正在转换，已处理 '+line.split('=',1)[1].strip())
    def process_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:self.done(-1)
    def cancel(self):
        self.cancel_requested=True
        if self.remote_worker:self.remote_worker.cancel()
        if self.process.state()!=QProcess.ProcessState.NotRunning:self.process.kill()
    def choose_output(self):
        selected=QFileDialog.getExistingDirectory(self,'选择输出目录',str(self.output_root or self.repo.settings().directory))
        if selected:self.output_root=selected
    def open_folder(self):
        folder=self.output.parent if getattr(self,'output',None) else Path(self.output_root or self.repo.settings().directory)/'Video to MP3'
        if not folder.is_dir():folder=Path(self.output_root or self.repo.settings().directory)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    def convert(self,remote=None):
        if self.process.state()!=QProcess.ProcessState.NotRunning:return
        ff=shutil.which('ffmpeg')
        if not ff:
            try:
                from imageio_ffmpeg import get_ffmpeg_exe
                ff=get_ffmpeg_exe()
            except (ImportError,RuntimeError):pass
        if not ff:self.status.setText('未安装 FFmpeg，当前无法转换。');return
        if not remote and self.input.text().strip().startswith(('http://','https://')):
            from melodyvault.downloads.remote_video import CommonsVideoWorker
            if self.remote_worker:return
            self.start.setEnabled(False);self.cancel_requested=False
            self.remote_worker=CommonsVideoWorker(self.input.text().strip(),Path(self.output_root or self.repo.settings().directory)/'Video to MP3',self)
            self.remote_worker.progress.connect(self.status.setText);self.remote_worker.failed.connect(self.status.setText)
            self.remote_worker.ready.connect(self.remote_ready);self.remote_worker.finished.connect(self.remote_finished);self.remote_worker.start();return
        source=Path(remote['path'] if remote else self.input.text())
        if not source.is_file():self.status.setText('请选择存在的本地视频文件。');return
        from uuid import uuid4
        from melodyvault.downloads.files import contained,safe_component
        root=self.output_root or self.repo.settings().directory;folder=contained(root,'Video to MP3');folder.mkdir(parents=True,exist_ok=True)
        name=remote['title'] if remote else source.stem
        fmt=self.output_format.currentText().lower();self.output=folder/(safe_component(name)+'.'+fmt);self.part=folder/(uuid4().hex+'.part.'+fmt)
        if self.output.exists():self.status.setText('同名文件已存在，请更改文件名；不会覆盖。');return
        from melodyvault.downloads.models import DownloadCandidate
        from melodyvault.database.catalog import utc_now
        identity='local-video:'+uuid4().hex
        self.candidate=DownloadCandidate(identity,identity,'Video to MP3',name,'unknown','commons' if remote else 'local_video',remote['source_url'] if remote else '',file_format=fmt)
        self.candidate.evidence=({'license_url':remote['license_url'],'source_url':remote['source_url']} if remote else {'user_selected_local_file':str(source.resolve())});self.candidate.evidence['source_type']='conversion';self.candidate.verified_at=utc_now()
        target={'song_id':identity,'recording_id':identity,'namespace':'local_video','local_video_path':str(source.resolve()),'title':name,'artist':{'id':'local','name':'Video to MP3'},'version':'unknown','confirmed':True}
        if remote:target['remote_source_url']=remote['source_url']
        self.jid=self.repo.enqueue(target,replace(self.repo.settings(),automatic_download=True));self.repo.update(self.jid,state='DOWNLOADING',reason='正在转换本地视频')
        self.cancel_requested=False
        codec='libmp3lame' if fmt=='mp3' else 'pcm_s16le'
        self.progress_buffer='';self.start.setEnabled(False);self.status.setText('正在转换…');self.process.start(ff,['-nostdin','-v','error','-progress','pipe:1','-n','-i',str(source.resolve()),'-vn','-codec:a',codec,str(self.part)])
    def remote_ready(self,record):
        self.remote_temp=Path(record['path']);self.convert(record)
        if self.process.state()==QProcess.ProcessState.NotRunning:self.remote_temp.unlink(missing_ok=True);self.remote_temp=None
    def remote_finished(self):
        worker=self.remote_worker;self.remote_worker=None
        if worker:worker.deleteLater()
        if self.process.state()==QProcess.ProcessState.NotRunning:self.start.setEnabled(True)
        if getattr(self.window(),'_close_requested',False):QTimer.singleShot(0,self.window().close)
    def done(self,code,*args):
        self.start.setEnabled(True)
        if self.remote_temp:self.remote_temp.unlink(missing_ok=True);self.remote_temp=None
        if code==0:
            try:
                from melodyvault.downloads.files import verify_file
                media=verify_file(self.part,self.candidate,self.repo.settings().max_file_bytes)
                if os.name=='nt':os.rename(self.part,self.output)
                else:os.link(self.part,self.output);self.part.unlink()
                self.repo.register_file(self.jid,self.candidate,self.output,media)
                self.status.setText('转换完成：'+str(self.output))
                if self.join_library.isChecked():QTimer.singleShot(0,self.add_to_library)
                return
            except Exception:pass
        if hasattr(self,'part'):self.part.unlink(missing_ok=True)
        if hasattr(self,'jid'):self.repo.update(self.jid,state='CANCELLED' if self.cancel_requested else 'FAILED',reason='本地视频转换取消或未完成')
        self.status.setText('转换未完成，可能已取消或文件无法读取。')
    def add_to_library(self):
        from melodyvault.ui.import_dialog import ImportDialog
        dialog=ImportDialog(self.repo,self,[str(self.output)],'conversion');dialog.exec()
        window=self.window()
        if hasattr(window,'refresh_history'):window.refresh_history()
