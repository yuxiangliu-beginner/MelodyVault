from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QHeaderView
from melodyvault.search.models import identity_key


class UnifiedResults(QWidget):
    artist_chosen=Signal(object);song_chosen=Signal(object);more_requested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.result=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.summary=QLabel('歌手与歌曲搜索结果');self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.summary)
        self.tree=QTreeWidget();self.tree.setColumnCount(4);self.tree.setHeaderLabels(['候选名称','歌手/身份','类型/版本','证据状态'])
        self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.tree.setMaximumHeight(245);layout.addWidget(self.tree)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(100);layout.addWidget(self.details)
        row=QHBoxLayout();layout.addLayout(row)
        self.artist_button=QPushButton('进入所选歌手目录');self.song_button=QPushButton('确认所选歌曲版本并搜索音源');self.more_button=QPushButton('联网补充其他歌手/版本')
        for b in (self.artist_button,self.song_button,self.more_button):row.addWidget(b)
        self.artist_button.clicked.connect(self._artist);self.song_button.clicked.connect(self._song);self.more_button.clicked.connect(self.more_requested)
        self.tree.itemSelectionChanged.connect(self._selected);self.tree.itemDoubleClicked.connect(lambda *args:self._double())
        self.clear()
    def clear(self):
        self.result=None;self.tree.clear();self.details.clear();self.artist_button.setEnabled(False);self.song_button.setEnabled(False);self.more_button.setEnabled(False)
    def show_result(self,result):
        self.clear();self.result=result
        self.summary.setText(f"歌手 {len(result.artists)} 个 · 歌曲录音版本 {len(result.songs)} 个 · 范围 {result.scope} · API {result.api_requests} / 重试 {result.retries} · {result.elapsed_seconds:.3f}秒。请选择身份；同名不等于同一作品。"+
            (' 达到本次返回上限，可细化歌手/歌名。' if result.truncated else '')+
            (' 部分查询失败：'+'；'.join(result.errors.values()) if result.errors else '')+
            (' 未找到精确名称；以下仅为相关候选。' if not any(s.title_exact for s in result.songs) and not any(identity_key(result.request.query) in {identity_key(n) for n in (a.name,*a.aliases)} for a in result.artists) else '')+
            (' 本地结果仅覆盖已保存目录，可联网补充。' if result.scope=='sqlite' else ''))
        artists=QTreeWidgetItem(['歌手候选']);songs=QTreeWidgetItem(['歌曲/录音候选'])
        self.tree.addTopLevelItems([artists,songs])
        for artist in result.artists:
            exact=identity_key(result.request.query) in {identity_key(n) for n in (artist.name,*artist.aliases)}
            item=QTreeWidgetItem([artist.name,' · '.join(x for x in (artist.country,artist.begin,artist.disambiguation,artist.mbid) if x),'歌手','名称/别名精确' if exact else '相关身份，需选择'])
            item.setData(0,Qt.ItemDataRole.UserRole,('artist',artist));artists.addChild(item)
        for song in result.songs:
            item=QTreeWidgetItem([song.title,song.artist.name+' · '+song.artist.mbid,song.version,'待确认' if song.pending_confirmation else '作品有关联，仍需选择版本'])
            item.setData(0,Qt.ItemDataRole.UserRole,('song',song));songs.addChild(item)
        artists.setExpanded(True);songs.setExpanded(True);self.tree.setCurrentItem(None)
        self.more_button.setEnabled(not result.request.local_only);self._selected();self.show()
    def choice(self):
        item=self.tree.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
    def _selected(self):
        choice=self.choice();self.artist_button.setEnabled(bool(choice));self.song_button.setEnabled(bool(choice and choice[0]=='song'))
        if not choice:return
        kind,data=choice
        if kind=='artist':self.details.setPlainText(data.label+'\n别名：'+', '.join(data.aliases)+'\n进入目录不会确认其他同名歌手。')
        else:self.details.setPlainText(f"歌曲：{data.title}\n歌手：{data.artist.name} [{data.artist.mbid}]\nRecording：{data.recording_mbid}\nWork：{', '.join(data.work_ids) or '缺少明确关系'}\n版本：{data.version}；时长：{data.length_ms or '未知'}ms\n"+'\n'.join(data.reasons)+'\n确认仅选择目标录音，不确认版权或下载成功，不覆盖已有人工分组。')
    def _artist(self):
        choice=self.choice()
        if choice:self.artist_chosen.emit(choice[1] if choice[0]=='artist' else choice[1].artist)
    def _song(self):
        choice=self.choice()
        if choice and choice[0]=='song':self.song_chosen.emit(choice[1])
    def _double(self):
        choice=self.choice()
        if choice:
            if choice[0]=='artist':self._artist()
            else:self._song()
