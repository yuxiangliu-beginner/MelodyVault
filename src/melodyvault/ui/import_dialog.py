import threading
from pathlib import Path
from uuid import uuid4
from dataclasses import replace
from PySide6.QtCore import QThread,Signal,Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QLabel,QFileDialog)
from melodyvault.library.imports import FORMATS,inspect_audio,destination,import_one

class ScanWorker(QThread):
    progress=Signal(str);completed=Signal(object)
    def __init__(self,paths,folder=None,parent=None):super().__init__(parent);self.paths=paths;self.folder=folder;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        items=[];errors=0
        paths=Path(self.folder).rglob('*') if self.folder else self.paths
        for path in paths:
            if self.cancel_event.is_set():break
            p=Path(path)
            if p.suffix.lower() not in FORMATS or not p.is_file():continue
            self.progress.emit(f'正在读取音乐信息：{p.name}')
            try:items.append(inspect_audio(p))
            except Exception:errors+=1
        self.completed.emit({'items':items,'errors':errors})

class ImportWorker(QThread):
    progress=Signal(str);completed=Signal(object)
    def __init__(self,path,root,items,parent=None):super().__init__(parent);self.path=path;self.root=root;self.items=items;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        from melodyvault.database.downloads import DownloadRepository
        from melodyvault.downloads.manager import RunLock
        repo=DownloadRepository(self.path);results=[]
        try:
            with RunLock(str(self.path)+'.imports'):results=self.import_files(repo)
        except Exception as error:results=[{'state':'FAILED','reason':str(error)}]
        self.completed.emit(results)
    def import_files(self,repo):
        results=[]
        for i,item in enumerate(self.items):
            if self.cancel_event.is_set():break
            identity='local-import:'+uuid4().hex
            target={'song_id':identity,'recording_id':identity,'namespace':'local_import','source_path':item['path'],'title':item['title'],'artist':{'id':'local','name':item['artist'] or '未知歌手'},'version':'unknown','confirmed':True}
            jid=repo.enqueue(target,replace(repo.settings(),automatic_download=True))
            try:
                repo.update(jid,state='DOWNLOADING',reason='正在复制导入文件')
                def progress(done,total):
                    self.progress.emit(f'正在导入 {i+1}/{len(self.items)}：{done}/{total} 字节');repo.update(jid,bytes_received=done,total_bytes=total)
                result=import_one(self.path,self.root,item,self.cancel_event,progress)
                if result['state']=='IMPORTED':
                    import json
                    repo.update(jid,state='COMPLETED',reason='文件已导入',result_json=json.dumps({'path':result['path'],'format':item['format'],'sha256':result['sha256'],'bytes':result['bytes']}))
                else:repo.update(jid,state='SKIPPED',reason_code='DUPLICATE',reason='文件内容已存在，已跳过')
            except InterruptedError:
                repo.update(jid,state='CANCELLED',reason='导入已取消');break
            except Exception as e:
                result={'state':'FAILED','reason':str(e),'path':item['path']};repo.update(jid,state='FAILED',reason_code='IMPORT_FAILED',reason=str(e))
            results.append(result)
        return results

class ImportDialog(QDialog):
    def __init__(self,repo,parent=None,paths=None,source_type='import'):
        super().__init__(parent);self.repo=repo;self.worker=None;self.items=[];self.source_type=source_type;self.setWindowTitle('导入音乐');self.resize(850,500)
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.files=QPushButton('选择文件');self.folder=QPushButton('选择文件夹');row.addWidget(self.files);row.addWidget(self.folder);self.files.clicked.connect(self.pick_files);self.folder.clicked.connect(self.pick_folder)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['歌曲','歌手','格式','目标位置']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table)
        self.table.itemChanged.connect(self.update_target)
        self.status=QLabel('导入会复制文件；可修改歌曲和歌手。');self.status.setWordWrap(True);layout.addWidget(self.status)
        actions=QHBoxLayout();layout.addLayout(actions);self.start=QPushButton('开始导入');cancel=QPushButton('取消');actions.addWidget(self.start);actions.addWidget(cancel);self.start.clicked.connect(self.run_import);cancel.clicked.connect(self.cancel)
        if paths:self.add_paths(paths)
    def pick_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'选择音乐文件','','音频 (*.mp3 *.flac *.m4a *.wav)');self.add_paths(files)
    def pick_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'选择音乐文件夹')
        if folder:self.scan([],folder)
    def add_paths(self,paths):
        if paths:self.scan(paths)
    def scan(self,paths,folder=None):
        if self.worker:return
        self.start.setEnabled(False);self.files.setEnabled(False);self.folder.setEnabled(False)
        self.worker=ScanWorker(paths,folder,self);self.worker.progress.connect(self.status.setText);self.worker.completed.connect(self.scanned);self.worker.finished.connect(self.worker_finished);self.worker.start()
    def scanned(self,result):
        for item in result['items']:
            item['source_type']=self.source_type
            if item['path'] not in {x['path'] for x in self.items}:self.items.append(item)
        self.table.blockSignals(True);self.table.setRowCount(len(self.items))
        for row,item in enumerate(self.items):
            for col,val in enumerate([item['title'],item['artist'],item['format'],str(destination(self.repo.settings().directory,item))]):
                cell=QTableWidgetItem(val)
                if col>=2:cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row,col,cell)
        self.table.blockSignals(False)
        self.status.setText(f"已读取 {len(result['items'])} 个文件；{result['errors']} 个文件无法读取。")
    def update_target(self,cell):
        if cell.column()>1:return
        item={**self.items[cell.row()],'title':self.table.item(cell.row(),0).text(),'artist':self.table.item(cell.row(),1).text()}
        self.table.item(cell.row(),3).setText(str(destination(self.repo.settings().directory,item)))
    def run_import(self):
        if self.worker or not self.items:return
        items=[{**v,'title':self.table.item(i,0).text(),'artist':self.table.item(i,1).text()} for i,v in enumerate(self.items)]
        self.start.setEnabled(False);self.worker=ImportWorker(self.repo.path,self.repo.settings().directory,items,self);self.worker.progress.connect(self.status.setText);self.worker.completed.connect(self.import_done);self.worker.finished.connect(self.worker_finished);self.worker.start()
    def import_done(self,results):
        count=lambda state:sum(r['state']==state for r in results)
        self.status.setText(f"已导入 {count('IMPORTED')}，重复跳过 {count('DUPLICATE')}，失败 {count('FAILED')}。"+(' 已取消。' if self.worker.cancel_event.is_set() else ''))
    def worker_finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        self.start.setEnabled(True);self.files.setEnabled(True);self.folder.setEnabled(True)
    def cancel(self):
        if self.worker:self.worker.cancel();self.status.setText('正在取消…')
        else:self.reject()
    def closeEvent(self,event):
        if self.worker:self.worker.cancel();event.ignore();return
        event.accept()
