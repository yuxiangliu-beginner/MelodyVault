"""User-facing shell; the original catalog/review UI remains in main_window.py."""
import json, threading, shutil, os
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from PySide6.QtCore import QThread,Signal,Qt,QTimer,QUrl,QProcess
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,
    QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QLabel,QTreeWidget,QTreeWidgetItem,
    QDialog,QFormLayout,QCheckBox,QFileDialog,QDialogButtonBox)
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
            stats=SourceSearchEngine(SourceRepository(self.path),default_providers(),self.cancel_event).search_queries(artist,[q])
            if self.cancel_event.is_set():raise CatalogCancelled('cancelled')
            raw=stats['jobs'][0]['candidates']; candidates=[UnifiedCandidate(c['provider'],c['page_url'],c['title'],match_score=c['match_score'],raw_source=c) for c in raw]
            repo=DownloadRepository(self.path);settings=replace(repo.settings(),automatic_download=True)
            with connect(self.path) as db:flag=db.execute("SELECT value FROM app_metadata WHERE key='ui.auto_fallback'").fetchone()
            if flag and flag[0]=='false':candidates=sorted(candidates,key=lambda c:-c.match_score)[:1]
            target={'song_id':q.song_id,'recording_id':s['source']+':'+s['song_id'],'namespace':s['source'],
                'artist':{'id':artist.mbid,'name':s['artist']},'title':s['title'],'version':s['version'],
                'duration':s['duration'],'confirmed':True,'urls':[s['source_url']],'work_ids':[]}
            def progress(e):
                self.notice.emit('下载中：'+str(e.get('bytes_received',0))+' 字节' if e['stage']=='download_progress' else '正在检查可下载音源…')
            self.manager=DownloadManager(repo)
            attempts=SourceFallbackManager(repo,self.manager,self.cancel_event,progress).run(target,candidates,settings)
            self.completed.emit({'download':True,'attempts':attempts,'candidates':raw,'errors':stats['jobs'][0]['errors']})
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
        self.setWindowTitle('MelodyVault');self.resize(1020,700)
        root=QWidget();outer=QVBoxLayout(root);bar=QHBoxLayout();bar.addWidget(QLabel('MelodyVault'));bar.addStretch()
        settings=QPushButton('设置');settings.clicked.connect(self.settings);bar.addWidget(settings);outer.addLayout(bar)
        self.tabs=QTabWidget();outer.addWidget(self.tabs);self.setCentralWidget(root)
        search=QWidget();layout=QVBoxLayout(search);row=QHBoxLayout();self.input=QLineEdit();self.input.setPlaceholderText('搜索歌曲或歌手，例如：周杰伦 晴天')
        self.search_button=QPushButton('搜索');self.cancel_button=QPushButton('取消');self.cancel_button.setEnabled(False)
        row.addWidget(self.input,1);row.addWidget(self.search_button);row.addWidget(self.cancel_button);layout.addLayout(row)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['歌曲','歌手','时长','来源','操作']);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table)
        self.status=QLabel('搜索音乐平台，选择歌曲后查找可下载音源。');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.source_info=QLabel();self.source_info.setWordWrap(True);layout.addWidget(self.source_info)
        self.tabs.addTab(search,'音乐搜索');self.search_button.clicked.connect(self.search);self.input.returnPressed.connect(self.search);self.cancel_button.clicked.connect(self.cancel)
        history=QWidget();hl=QVBoxLayout(history);self.filter=QLineEdit();self.filter.setPlaceholderText('搜索下载历史');hl.addWidget(self.filter)
        self.history=QTreeWidget();self.history.setHeaderLabels(['歌手 / 歌曲','格式','状态 / 进度']);hl.addWidget(self.history)
        actions=QHBoxLayout();hl.addLayout(actions)
        for label,fn in [('打开所在文件夹',self.folder),('重试 / 继续',self.retry),('取消任务',self.cancel_history)]:
            b=QPushButton(label);b.clicked.connect(fn);actions.addWidget(b)
        self.tabs.addTab(history,'下载记录');self.filter.textChanged.connect(self.refresh_history)
        self.video=VideoPage(self.repo);self.tabs.addTab(self.video,'视频转 MP3')
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
        if getattr(self,'_close_requested',False):QTimer.singleShot(0,self.close)
    def cancel(self):
        if self.worker:
            if hasattr(self.worker,'cancel'):self.worker.cancel()
            self.status.setText('正在取消…')
    def search(self):
        if self.worker or not self.input.text().strip():return
        self.status.setText('正在搜索音乐平台…');self.launch(MusicTask(self.path,query=self.input.text(),parent=self),self.results)
    def results(self,result):
        self.songs=result['rows'];self.table.setRowCount(len(self.songs))
        for i,s in enumerate(self.songs):
            for j,v in enumerate([s['title'],s['artist'],f"{int(s['duration'])//60}:{int(s['duration'])%60:02d}",'Apple Music / iTunes']):
                item=QTableWidgetItem(v);item.setToolTip(s['source_url']);self.table.setItem(i,j,item)
            box=QWidget();row=QHBoxLayout(box);row.setContentsMargins(0,0,0,0);b=QPushButton('下载');b.clicked.connect(lambda checked=False,s=s:self.download(s));row.addWidget(b)
            link=QPushButton('商店');link.clicked.connect(lambda checked=False,s=s:QDesktopServices.openUrl(QUrl(s['source_url'])));row.addWidget(link);self.table.setCellWidget(i,4,box)
        self.status.setText(f"找到 {len(self.songs)} 条歌曲信息。商店结果不提供本程序的完整音频下载许可。")
        self.source_info.setText('网易云 / QQ / 酷我 / 酷狗 / 咪咕 / Bilibili：检索使用条件尚未核实；YouTube：未配置。')
        self.source_info.setToolTip('部分音乐平台尚未取得适用的搜索接口权限；已配置来源会独立运行。')
        if result['statuses'].get('apple',{}).get('status')=='FAILED':self.status.setText('音乐平台查询失败，请稍后重试。')
    def download(self,s):
        if not self.worker:self.launch(MusicTask(self.path,song=s,parent=self),self.download_done)
    def download_done(self,r):
        completed=next((a for a in r['attempts'] if a['state']=='COMPLETED'),None)
        if completed:
            path=self.repo.get(completed['job_id'])['result']['path'];self.status.setText('下载完成：'+path)
            with connect(self.path) as db:flag=db.execute("SELECT value FROM app_metadata WHERE key='ui.auto_open'").fetchone()
            if flag and flag[0]=='true':QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
        else:
            self.status.setText('暂时没有可下载的音源。'+(' 部分来源查询失败，可稍后重试。' if r['errors'] else ''))
            self.status.setToolTip('\n'.join(c['page_url']+' · '+c.get('license_reason','') for c in r['candidates']))
    def refresh_history(self):
        selected=self.history.currentItem();key=selected.data(0,Qt.ItemDataRole.UserRole) if selected else None
        expanded={self.history.topLevelItem(i).text(0) for i in range(self.history.topLevelItemCount()) if self.history.topLevelItem(i).isExpanded()}
        with connect(self.path) as db:rows=db.execute('SELECT id,state,target_json,result_json,candidate_json,bytes_received,total_bytes,reason FROM download_jobs ORDER BY created_at DESC').fetchall()
        self.history.clear();groups={};q=self.filter.text().casefold()
        labels={'COMPLETED':'已完成','FAILED':'下载失败','SKIPPED':'未找到可下载文件','CANCELLED':'已取消','PAUSED':'已暂停','QUEUED':'等待中','READY':'等待开始','DOWNLOADING':'下载中','SEARCHING':'查找中','VERIFYING':'检查中'}
        for r in rows:
            t=json.loads(r['target_json']);out=json.loads(r['result_json']);c=json.loads(r['candidate_json']);artist=t.get('artist',{}).get('name') or '未知歌手';title=t.get('title','')
            if q and q not in (artist+' '+title).casefold():continue
            group=artist if r['state']=='COMPLETED' else '未完成任务'
            if group not in groups:
                groups[group]=QTreeWidgetItem(self.history,[group]);groups[group].setExpanded(group in expanded or not getattr(self,'_history_initialized',False))
            state=labels.get(r['state'],'处理中');p=out.get('path','')
            if r['state']=='COMPLETED' and not Path(p).is_file():state='文件不存在'
            if r['total_bytes'] and r['state']!='COMPLETED':state+=f" {100*r['bytes_received']/r['total_bytes']:.0f}%"
            item=QTreeWidgetItem(groups[group],[title,out.get('format') or c.get('file_format',''),state]);item.setData(0,Qt.ItemDataRole.UserRole,r['id']);item.setToolTip(0,p or r['reason'])
            if r['id']==key:self.history.setCurrentItem(item)
        self._history_initialized=True
    def selected_job(self):
        item=self.history.currentItem();key=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        return self.repo.get(key) if key else None
    def folder(self):
        r=self.selected_job()
        if r and r['result'].get('path'):QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(r['result']['path']).parent)))
    def retry(self):
        r=self.selected_job()
        if not r or self.worker:return
        if r['state'] not in {'FAILED','PAUSED','READY'}:return
        if r['target'].get('namespace')=='local_video':
            source=r['target'].get('local_video_path','')
            if not source or not Path(source).is_file():self.status.setText('原视频文件不存在，无法重新转换。');return
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
    def closeEvent(self,event):
        if self.worker:self._close_requested=True;self.cancel();event.ignore();return
        if self.video.process.state()!=QProcess.ProcessState.NotRunning:self._close_requested=True;self.video.cancel();event.ignore();return
        event.accept()

class VideoPage(QWidget):
    def __init__(self,repo):
        super().__init__();self.repo=repo;self.process=QProcess(self);layout=QVBoxLayout(self)
        layout.addWidget(QLabel('本地视频转 MP3 · 请选择你有权提取和保存的文件'))
        self.input=QLineEdit();self.input.setPlaceholderText('本地视频文件路径');layout.addWidget(self.input)
        choose=QPushButton('选择视频文件');choose.clicked.connect(lambda:self.input.setText(QFileDialog.getOpenFileName(self,'选择视频')[0] or self.input.text()));layout.addWidget(choose)
        self.start=QPushButton('转为 MP3');layout.addWidget(self.start);self.start.clicked.connect(self.convert)
        cancel=QPushButton('取消');cancel.clicked.connect(self.cancel);layout.addWidget(cancel)
        self.status=QLabel('远程视频平台提取尚未集成；不会将公开链接当作下载授权。');self.status.setWordWrap(True);layout.addWidget(self.status);layout.addStretch()
        self.process.finished.connect(self.done);self.process.errorOccurred.connect(self.process_error)
    def process_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:self.done(-1)
    def cancel(self):
        self.cancel_requested=True;self.process.kill()
    def convert(self):
        if self.process.state()!=QProcess.ProcessState.NotRunning:return
        ff=shutil.which('ffmpeg')
        if not ff:
            try:
                from imageio_ffmpeg import get_ffmpeg_exe
                ff=get_ffmpeg_exe()
            except (ImportError,RuntimeError):pass
        if not ff:self.status.setText('未安装 FFmpeg，当前无法转换。');return
        source=Path(self.input.text())
        if not source.is_file():self.status.setText('请选择存在的本地视频文件。');return
        from uuid import uuid4
        from melodyvault.downloads.files import contained,safe_component
        root=self.repo.settings().directory;folder=contained(root,'Video to MP3');folder.mkdir(parents=True,exist_ok=True)
        self.output=folder/(safe_component(source.stem)+'.mp3');self.part=folder/(uuid4().hex+'.part.mp3')
        if self.output.exists():self.status.setText('同名文件已存在，请更改文件名；不会覆盖。');return
        from melodyvault.downloads.models import DownloadCandidate
        from melodyvault.database.catalog import utc_now
        identity='local-video:'+uuid4().hex
        self.candidate=DownloadCandidate(identity,identity,'Video to MP3',source.stem,'unknown','local_video','',file_format='mp3')
        self.candidate.evidence={'user_selected_local_file':str(source.resolve())};self.candidate.verified_at=utc_now()
        target={'song_id':identity,'recording_id':identity,'namespace':'local_video','local_video_path':str(source.resolve()),'title':source.stem,'artist':{'id':'local','name':'Video to MP3'},'version':'unknown','confirmed':True}
        self.jid=self.repo.enqueue(target,replace(self.repo.settings(),automatic_download=True));self.repo.update(self.jid,state='DOWNLOADING',reason='正在转换本地视频')
        self.cancel_requested=False
        self.start.setEnabled(False);self.status.setText('正在转换…');self.process.start(ff,['-nostdin','-v','error','-n','-i',str(source.resolve()),'-vn','-codec:a','libmp3lame',str(self.part)])
    def done(self,code,*args):
        self.start.setEnabled(True)
        if code==0:
            from mutagen.mp3 import MP3
            try:
                if MP3(self.part).info.length<=0:raise ValueError()
                if os.name=='nt':os.rename(self.part,self.output)
                else:os.link(self.part,self.output);self.part.unlink()
                from melodyvault.downloads.files import hashes
                media={'format':'mp3','duration':MP3(self.output).info.length,'bytes':self.output.stat().st_size,**hashes(self.output)}
                self.repo.register_file(self.jid,self.candidate,self.output,media)
                self.status.setText('转换完成：'+str(self.output));return
            except Exception:pass
        if hasattr(self,'part'):self.part.unlink(missing_ok=True)
        if hasattr(self,'jid'):self.repo.update(self.jid,state='CANCELLED' if self.cancel_requested else 'FAILED',reason='本地视频转换取消或未完成')
        self.status.setText('转换未完成，可能已取消或文件无法读取。')
