# Phase 3B 实测与验收

项目路径 `E:\users\yliu\MelodyVault`。本机 Windows 10 build 19045、CPython3.13.2、PySide6 6.12.0、SQLite3.45.3、httpx0.28.1/httpcore1.0.9、mutagen1.48.1。测试在本机 2026-11-13（America/Los_Angeles）执行；SQLite/证据UTC日期可显示2026-11-14。

实现范围：多来源候选、独立下载资格审核、明确开启后的真实下载、完整性校验和本地归档、持久队列、暂停/继续/取消/失败重试/重启恢复及Windows界面。默认dry-run；不开发上传、播放器、歌词或Phase3C。当前等待用户验收，不代表已获用户验收通过。

## 审计和实际基线

本次正式库实际为 **schema6、2055条Recording**，不是旧描述的1520；已先保存`before-phase3b.sqlite3`、2055条原始SHA-256和源文件基线。原113项测试在变更前实际 **113 passed / 200.94秒**。未覆盖旧项目、清库或修改SuiSound。

之后仅追加schema7。`preservation.json`验证2055条原始payload逐条一致、旧1520条子集一致、v1–6迁移checksum一致、Song身份/归属一致、审核/原来源缓存/统一搜索缓存逐行保留，integrity_check=ok、FK无错误。正式download_jobs=0、automatic_download=false；所有真实下载和测试确认都在隔离QA库。

## 真实授权音频端到端

正常流程为真实MusicBrainz歌曲检索 → 明确选择Recording → 原SourceSearchEngine真实查询 → 独立官方文件/许可/ISRC核验 → 明确开启的下载任务 → 原始文件保存 → 实际媒体和校验值 → COMPLETED。未用测试音调或商业原唱未知文件替代这些真实样本。

| 实际样本 | 身份 | 来源和许可 | 格式 | 字节 | 实际秒 |
|---|---|---|---|---:|---:|
| Silent Night / Kevin MacLeod | MusicBrainz `56c6eca2-5953-45d2-a7c2-54d6ab5833ef`；Artist `8292bf44-2dd1-4bad-8019-276ec38f28e7`；ISRC `USUAN1100075` | Commons文件64756585，CC BY3.0 | MP3 | 5369410 | 131.213075 |
| Conillet de Vellut, on t’has perdut / 来源作者José Galeote | Commons原生文件 `commons:145596320`，明确来源文件ID，不冒充MusicBrainz或商业歌手版本 | Commons文件145596320，CC BY-SA4.0；ESMUC来源 | PCM WAV | 24968780 | 130.044979 |

原始说明页：[Silent Night](https://commons.wikimedia.org/wiki/File:Silent_Night_%28ISRC_USUAN1100075%29.mp3)、[WAV说明页](https://commons.wikimedia.org/wiki/File:Conillet_de_Vellut,_on_t%27has_perdut.wav)。许可：[CC BY3.0](https://creativecommons.org/licenses/by/3.0/)、[CC BY-SA4.0](https://creativecommons.org/licenses/by-sa/4.0/)。署名、原始页面、许可条件和原始字节未改动声明保存在各音频旁的`.evidence.json`和SQLite。

SHA-256：

```text
MP3  4303f2a73ffd4e872503eb0898f62d7d0b9f1f15c783fcb3495e01c7383b6c00
WAV  7cf0414cced10263c76d78af1d094798da82b2ecdaca07e49107910c48ed368a
```

源端SHA-1分别为`35af01267f55489127dc293b361995d5eda13e8d`和`bab62b5c13d6edd8d36d672ecec458f5e70d49e2`，与实际文件一致；SHA-256是另行计算保存，不把SHA-1误报为SHA-256。保留原始文件，不转码、写音频标签、补帧或填静音。

实际路径：

```text
.local/reports/phase3b/native-release/music/Kevin MacLeod/Silent Night/
  Silent Night [instrumental] a85e38c695-4303f2a73ffd.mp3
.local/reports/phase3b/network-fixed/music/José Galeote/Conillet de Vellut, on t'has perdut/
  Conillet de Vellut, on t'has perdut [unknown] a08771acb5-7cf0414cced1.wav
```

WAV真实从SourceSearchEngine找到原生文件、核验、下载、媒体与哈希校验、归档耗时 4.554秒（含核验/归档，不是只计socket读）。最终GUI MP3从实际开始、暂停、重建窗口、继续到归档耗时 11.301秒。早期CLI MP3完整保存 7.455秒，**那轮续传收到200，是安全重下**；不把它计为206通过。CLI重复同一来源文件结果reused=true，未新增音频请求。

WAV使用独立来源namespace只用于验证来源原生公开完整音频；未伪造Song/Recording MBID。MP3则确实经过现有Phase3A歌曲选择和Song/Recording关联；QA原始库2056（多一条真实开放录音），正式库仍2055。

## 真正的续传和进程重启

- 最终Windows GUI：在131072字节处点击暂停，关闭并重新创建主窗口；未自动执行；用户点击继续，实际206，Content-Range起点131072、总量5369410，最后文件SHA一致。
- Commons返回裸ETag而非标准带引号强ETag；修正后不用它批准拼接，采用符合Date/Last-Modified时间条件的验证器。最终`resume`证据明确为`RANGE_ACCEPTED`、`validator=last_modified`。
- 真正进程中断测试`process-restart/`：测试自己创建的子进程39792在写入131072字节后被中断，SQL状态仍DOWNLOADING，部分文件也为131072；另一个新进程17452取得队列锁后恢复为PAUSED/RESTART_RECOVERY，再明确继续，取得206并完成同一SHA-256。不是仅更换Python对象来冒充进程重启。
- 无Range/服务器200、强ETag变化、弱/裸ETag、错误范围、超时/断流后实际前缀恢复另有故障注入。没有为测试放行localhost/私网下载。

## Windows原生GUI

使用windows Qt平台、真实控件、输入法提交、Enter及鼠标点击，未替换来源provider。最终`native-release/`证明：中文原界面保留、四个页面（目录/来源/下载任务/下载设置）、默认关闭、实际歌曲候选选择、来源行加入审核、dry-run READY无音频目录、点击开关和保存、新建实际任务、真实下载进度/暂停/继续、重建窗口、COMPLETED及可读许可/来源/署名/SHA证据。

最终截图`dry-run-native.png`、`paused-native.png`、`completed-native.png`已实际查看，1040×720中文与按钮正常。事件循环心跳 974次、最大间隔 0.735秒；这是观测数据，不生成下载进度。网络和媒体校验均在worker/线程池，界面可操作。真实GUI来源搜索 3次元数据请求；下载资格复核和媒体传输属于独立任务，不混入该来源计数。

## 三位歌手真实来源搜索

每位使用现有SQLite目录、真实已确认Artist MBID，选5个不同标题，明确强制查询已配置官方来源。不是全目录/全网覆盖率测试。Jamendo未配置明确跳过，没有下载这些商业目标。

| 歌手 | 不同标题 | 有候选歌曲 / 文件 | 来源许可字段已核实文件 | 独立审核许可字段已核实 | 全部下载资格通过 | 无结果歌曲 | 失败歌曲 | 来源HTTP | 搜索秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 周杰伦 | 5 | 2 / 2 | 1 | 1 | 0 | 3 | 0 | 22 | 22.383 |
| 林俊杰 | 5 | 0 / 0 | 0 | 0 | 0 | 5 | 0 | 15 | 14.694 |
| 周传雄 | 5 | 0 / 0 | 0 | 0 | 0 | 5 | 0 | 20 | 18.835 |

合计15首、2首有候选/2个文件、1个来源文件许可字段明确，**0个满足目标录音全部下载资格**、无结果13、失败0。来源搜索共57次HTTP，表中不含独立许可复核请求，不夸大为所有网络总次数。

周杰伦“晴天”命中Archive钢琴合集，VERSION_MISMATCH且许可未核验；“If”命中Commons的Jay Chou百科朗读（文件本身有开放许可），与目标时长/录音不符，INCOMPLETE_AUDIO保守拒绝。百科朗读不是该歌曲。其余无结果。1个文件许可字段已核实不等于1首可下载音乐。

## 自动回归与模拟测试

变更前113 passed /200.94秒；最终安全补测前全量 **164 passed /321.28秒**。最后加入URL有效身份参数和官方API JSON错误归类后，4项定向测试通过，全量 **168 passed /297.26秒**；随后补充所选别名/版本快照指纹保留测试1项通过。第一次169项遇到旧Phase3A GUI等待器竞态（168 passed/1 failed），改为等待排队信号及来源统计就绪，业务断言保留；8项UI定向通过。**最终169 passed /301.97秒，0 failures / errors / skipped**，`pytest-verified.xml`，包含原113项与新增56项。真实MusicBrainz旧目录集成开启MELODYVAULT_LIVE，复用有效官方缓存；不将这些缓存读取冒充强制联网。

新增测试使用真实临时SQLite和合成测试音调WAV、httpx.MockTransport；它们不算真实公开音乐下载。Qt单元验证真实控件/主线程信号，但音频HTTP为Mock。下面区分覆盖来源：

| 验收项 | 真实网络/文件/GUI | 故障注入或回归 |
|---|---|---|
| 正常MP3、WAV | Commons两原始文件；MP3真实GUI端到端 | 真实临时文件媒体解析 |
| Range续传 | 最终GUI与独立新进程实际206 | 强ETag、Last-Modified、错误验证器/范围 |
| 服务器不支持Range | 早轮实际200走安全重下；不据此断言服务器不支持Range | 模拟服务器忽略有效Range返回200，核对最终字节未拼错 |
| URL过期 | 未制造线上过期凭据 | 403后官方元数据换URL再成功；不可用地址有界失败 |
| 网络中断/超时 | 真实子进程中断有部分文件 | 首字节前和65536字节后ReadError/ReadTimeout，人工重试按实际文件长度续传 |
| 大小、SHA-256、格式不符 | 两实际文件官方大小/SHA-1及本地SHA-256一致 | 错长度、错SHA-256/SHA-1、HTML、声明数据被截断、不依赖扩展名 |
| 试听/版本/授权/权限拒绝 | 商业目标钢琴/百科朗读拒绝 | PREVIEW_ONLY、VERSION_MISMATCH、LICENSE_UNVERIFIED、DOWNLOAD_NOT_PERMITTED分别断言 |
| 重复与并发 | 实际已验证文件复用 | 同源文件并发仅1次GET；不同同名录音独立；并发2个实际流用barrier同步验证 |
| 暂停、取消、重启 | 原生点击及真正新进程 | 批量建立期间也应用暂停/取消；退出恢复；失败重试审计保留 |
| 磁盘/路径/安全 | 本机NTFS，现有2055原始数据与缓存保留 | 空间不足、冲突不覆盖、保留名、越界、HTTPS/私网/DNS固定、凭据过滤 |
| GUI/旧阶段 | 最终原生截图/输入/点击 | 全部Phase1/2/3A回归、UI线程、旧任务隔离、设置写失败不假报保存 |

未进行真实线上磁盘填满、真实超时制造或商业原唱强制下载。没有把这些mock写成实网通过。

## 失败记录与修复

1. Gymnopedie样本ISRC官方404，未下载；换用已由官方Recording与文件ISRC核对的Silent Night。
2. Windows重复取得队列锁时读取锁字节先抛PermissionError，修正为安全QUEUE_BUSY；初轮32 passed/1 failed保留XML。
3. 版本词硬过滤导致已知开放文件搜索不到；允许无结果时扩大检索，但版本/身份审核保持严格，相关查询指纹升级v3，不删旧缓存。
4. 初轮GUI测试点击了checkbox拉伸后的空白中心，以及断言Windows斜杠方向不一致；改用实际指示器坐标和Path比较，未降低下载资格。
5. 原生测试脚本括号错误、等待器在排队信号启动来源任务前抢先读取，分别修正；旧目录/部分报告保留。
6. 早期HTTP200被文字误述为Range，核对证据后已更正；裸ETag不再作为强验证器，实际206已另证。
7. 第一轮全量158 passed/1 failed：睡眠式并发测试在系统负载下只观察到1流；改用barrier要求真实两流同时进入并保持上限断言，再通过全量164项。

8. 最后一次旧统一搜索GUI测试等待器只看线程isRunning，在结果信号尚未派发时读取last_stats；增加当前搜索收尾和统计就绪条件后，8项定向与最终169项全部通过，不改变应用流程或降低断言。

原始XML、`network-initial/`、`native-initial/`、`native-fixed/`等失败证据仍保留，没有覆盖或删除来制造全通过。

## 依赖、文件与复现

已安装mutagen1.48.1并更新editable项目元数据，pip check通过；准确版本见`requirements/requirements-phase3b-lock.txt`。实现边界见[DOWNLOAD_ENGINE_REPORT.md](../design/DOWNLOAD_ENGINE_REPORT.md)，安全、许可和未验收范围见[DOWNLOAD_SECURITY_REPORT.md](../research/DOWNLOAD_SECURITY_REPORT.md)。

```powershell
cd E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
# 查看目录/来源或右键建立下载审核；默认仅dry-run
# 在下载设置保存实际下载开关后，重新建立实际任务并点击开始
$env:MELODYVAULT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-my-3b --junitxml=.local\reports\phase3b\my-pytest.xml
# 以下真实下载仅限明确许可QA样本；每次指定未使用过的报告目录
.\.venv\Scripts\python.exe scripts\validate_phase3b_network.py --execute-downloads --report-dir .local\reports\phase3b\my-network
.\.venv\Scripts\python.exe scripts\verify_phase3b_gui.py --execute-downloads --report-dir .local\reports\phase3b\my-native
.\.venv\Scripts\python.exe scripts\verify_phase3b_restart.py --execute-downloads --report-dir .local\reports\phase3b\my-restart --target-report .local\reports\phase3b\my-native\native-gui.json
.\.venv\Scripts\python.exe scripts\validate_phase3b_artists.py --report-dir .local\reports\phase3b\my-artists
```

尚未验收：Jamendo实际账号、Archive具体权利链、未知/特殊编码、逐帧解码或声纹识别、Win11/其他Python/独立exe、网络盘异常。metadata有界且可能不完整，不能保证所有歌曲找到来源。当前不增加来源白名单或放宽证据去补齐商业原唱下载数量。

实现及上述最终测试已完成，当前停止等待用户验收，不进入Phase3C。

交付启动检查：唯一MelodyVault窗口、Responding=True，正式schema7/2055条录音、实际下载关闭、下载任务0；`app-launch.json`留存进程记录。最终原始MP3/WAV已重新读取字节数和SHA-256，与上述记录一致。程序留供验收，没有自动网络或下载任务。
