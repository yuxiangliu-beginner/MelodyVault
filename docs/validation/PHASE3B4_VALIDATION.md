# Phase 3B.4 实际验证记录

## 音乐搜索与下载

搜索入口并行使用现有 Apple iTunes 目录和 Wikimedia Commons 官方文件搜索；完整候选保留各自身份，不按名称强制合并。三个真实搜索各发出2次请求：周杰伦《晴天》返回30条、歌名及署名一致3条（0.81秒）；林俊杰《江南》30条、一致5条（2.77秒）；周传雄《黄昏》30条、一致4条（3.05秒）。此处“一致”仅指目录元数据，不能认定完整文件或录音身份。测试机器结果 `.local/reports/phase3b4/import-final/searches.json`。

用户现在可以直接选择 Commons 具体录音，系统优先对该原始文件进行身份和许可核验、使用原 DownloadManager 保存；失败时按设置尝试其他候选。真实 Windows GUI 搜索《卿雲歌》，选择 [Version 1](https://commons.wikimedia.org/wiki/File:%E5%8D%BF%E9%9B%B2%E6%AD%8C_(Song_to_the_Auspicious_Cloud)_Version_1.flac)，按钮显示“已完成”。官方文件注明 **钢琴演奏**、CC BY-SA 4.0，作者/上传者未被程序当作已核实的表演者，因此归入“未知歌手”。实际保存原始 FLAC **2,084,272 字节**，SHA-256 `15f055f54c5c9b7677dfd04ad8433f1cc93442a2f45fd2175e38079dc254dfec`，FFmpeg完整解码退出码0，SQLite登记成功；隔离测试路径 `.local/reports/phase3b4/native-fast/music/未知歌手/`，点击后耗时27.45秒。原始文件版权证据按原下载流程保存。

这是一首中国音乐的器乐录音，**不是中文人声歌曲、周杰伦或其他商业歌曲下载成功**。本轮中文人声及商业歌曲实际下载均为0。真实授权首选源失败后切换到备用源成功仍未验证；保留有界重试、自动换源和现有故障注入测试，不能将模拟测试计为真实切换。没有关闭SSL校验或访问受限接口。

## 音乐库与转换

Windows 原生GUI对自生成的MP3、FLAC、M4A、WAV控制音频执行文件夹扫描、4文件批量复制和手动修改歌手/标题：实际导入4个；再次选择4个文件均按SHA-256跳过；源文件哈希全部不变。模拟冲突和取消测试验证同名不同内容不覆盖、临时文件清理。扫描和复制在后台线程，记录真实字节进度；失败/取消/暂停任务保留在现有任务表中。测试 `.local/reports/phase3b4/import-release/result.json`。

“我的音乐”从 SQLite 读取下载、导入及用户选入库的转换文件，按歌手分组，展示格式、状态、文件路径；支持过滤、打开文件夹、缺失提示和失败重试。原生GUI实际选择将转换结果加入音乐库，SQLite `source_type=conversion` 记录1条；没有选择时不会显示为已入库音乐。截图 `.local/reports/phase3b4/import-release/screen.png`。

原生GUI实测 WAV→MP3、FLAC→MP3、M4A→MP3、MP3→WAV，输出均由FFmpeg完整解码、退出码0；注明MP3转WAV不恢复音质。本地自生成视频→MP3和选择入库成功。Commons CC0远程视频 [Ex SIN.webm](https://commons.wikimedia.org/wiki/File:Ex_SIN.webm) 在媒体页面变更后再次真实下载并转换成功、完整解码退出码0；88次UI心跳。其他远程平台仍不支持。记录 `.local/reports/phase3b4/media-native-v2/results.json`、`import-release/final-join.json` 和 `remote-native/result.json`。

## 数据与回归

迁移前正式库 SQLite 备份 `.local/reports/phase3b4/before-migration.sqlite3`，追加 schema10 `personal_music` 表与索引。实际迁移后：原始Recording 2,055、旧下载任务3、来源68及旧文件登记、下载设置、人工审核和app_metadata均与紧邻迁移前备份逐行一致；`integrity_check=ok`、外键错误0。导入和转换真实测试使用隔离数据库，未向正式库写入测试音频。导入和下载独立锁，应用重启可把上次未结束的导入标为暂停，不影响其他进程的活动导入。

定向回归 **80 passed in 24.45s**；后续界面、损坏文件去重、WAV RIFF元数据、歌手简繁体分类及取消状态回归 **14 passed in 4.03s**。四种格式的标题和歌手均使用真实生成的元数据文件验证。测试覆盖原下载安全、目录、迁移、GUI、远程来源、四格式导入、去重/冲突、原文件保护、取消及导入锁恢复。测试生成的音频是控制数据。未重复进行30首网络测试或完整pytest。最初导入界面实测发现Qt信号名称冲突，修复后重测通过；同内容转换结果入库曾被其自身文件登记判为重复，修复后真实GUI重测通过。

仍需：找到明确允许保存的完整中文人声录音及主流商业歌曲的合法来源，验证真实授权备用来源切换；其他视频网址暂不支持。Phase 3B.4 的本地媒体管理已完成上述验证，但不能据此声称中文人声或商业歌曲下载成功。不进入 Phase 3C。
