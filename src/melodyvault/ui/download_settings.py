from dataclasses import asdict
import sqlite3
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QFormLayout,QHBoxLayout,QVBoxLayout,QLineEdit,QPushButton,QSpinBox,QComboBox,QCheckBox,QFileDialog,QLabel
from melodyvault.downloads.models import DownloadSettings


class DownloadSettingsPage(QWidget):
    saved=Signal(object)
    def __init__(self,repository,parent=None):
        super().__init__(parent);self.repository=repository;settings=repository.settings()
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.directory=QLineEdit(settings.directory);browse=QPushButton('选择目录');row=QHBoxLayout();row.addWidget(self.directory);row.addWidget(browse);form.addRow('本地音乐目录',row)
        browse.clicked.connect(self._browse)
        self.concurrent=QSpinBox();self.concurrent.setRange(1,4);self.concurrent.setValue(settings.max_concurrent);form.addRow('最大并发数',self.concurrent)
        self.automatic=QCheckBox('明确开启实际下载（关闭时仅dry-run审核）');self.automatic.setChecked(settings.automatic_download);form.addRow('实际下载',self.automatic)
        self.quality=QComboBox()
        for label,value in [('原始文件','original'),('无损格式优先（可用时）','lossless'),('较小原始文件优先','small')]:self.quality.addItem(label,value)
        self.quality.setCurrentIndex(self.quality.findData(settings.quality));form.addRow('质量偏好',self.quality)
        self.speed=QSpinBox();self.speed.setRange(0,102400);self.speed.setSuffix(' KiB/s（0不限速）');self.speed.setValue(settings.speed_limit//1024);form.addRow('队列总速度限制',self.speed)
        self.keep=QCheckBox('保留失败/取消任务的临时文件');self.keep.setChecked(settings.keep_temporary);form.addRow('临时文件',self.keep)
        self.size=QSpinBox();self.size.setRange(1,2048);self.size.setSuffix(' MiB');self.size.setValue(settings.max_file_bytes//1024**2);form.addRow('单文件上限',self.size)
        self.save_button=QPushButton('保存下载设置');layout.addWidget(self.save_button);self.save_button.clicked.connect(self._save)
        self.message=QLabel('默认自动下载关闭。开启后仍须建立并开始任务，每个文件独立核验身份、完整性及许可。不会转码或自动播放。');self.message.setWordWrap(True);layout.addWidget(self.message);layout.addStretch()
    def _browse(self):
        path=QFileDialog.getExistingDirectory(self,'选择本地音乐目录',self.directory.text())
        if path:self.directory.setText(path)
    def _save(self):
        try:
            previous=asdict(self.repository.settings());previous.update(directory=self.directory.text().strip(),max_concurrent=self.concurrent.value(),automatic_download=self.automatic.isChecked(),quality=self.quality.currentData(),speed_limit=self.speed.value()*1024,keep_temporary=self.keep.isChecked(),max_file_bytes=self.size.value()*1024**2)
            settings=DownloadSettings(**previous).validate();self.repository.save_settings(settings);self.saved.emit(settings)
            self.message.setText('设置已保存；'+('实际下载已明确开启' if settings.automatic_download else 'dry-run模式，不下载音频')+'。当前运行任务会暂停，新任务使用新设置；恢复旧任务沿用其原目录。')
        except (ValueError,OSError,sqlite3.Error) as error:self.message.setText('设置未保存：'+str(error))
