# Phase 3B.4 开发审计

2026-11-15 musicdl 专项研究：只读审阅网易、酷我、咪咕适配器，源码版本 `dca2f0967e46a8faf8d279737535471102d74ca3`（2.14.2），未运行第三方解析链。三个官方首页/robots 的真实探测分别记录；未核实第三方自动搜索授权，因此九次指定歌曲搜索均未发起，完整音频下载0，不能据此判定接口失效。网易首页HTTP200、酷我首页HTTP500、咪咕首页HTTP301仅代表该次首页请求。正式下载流程和音乐库未修改；只读数据库检查schema10、2055录音、3任务、68来源、完整性ok、外键错误0。详细结论、源码/条款链接和分项限制见 `docs/research/MUSICDL_SOURCE_RESEARCH.md`。

完成 Commons 文件直接搜索和所选录音优先核验/下载：原生GUI真实下载 [《卿雲歌》Version 1](https://commons.wikimedia.org/wiki/File:%E5%8D%BF%E9%9B%B2%E6%AD%8C_(Song_to_the_Auspicious_Cloud)_Version_1.flac) 钢琴演奏版，FLAC 2,084,272字节，SHA-256 `15f055f54c5c9b7677dfd04ad8433f1cc93442a2f45fd2175e38079dc254dfec`，完整解码0、SQLite登记成功；未知署名保守归类未知歌手。此为中国音乐器乐版，不是中文人声或商业歌曲；后两者下载仍为0。用户选中的文件先尝试，再根据设置换源，不改变录音与授权标准。

追加schema10个人音乐表；真实正式库迁移前备份并逐行核对2055原录音、3旧任务、68来源、设置/审核/文件登记无变化，完整性ok、外键错误0。个人音乐可后台复制导入 MP3/FLAC/M4A/WAV、预览和改标题歌手、按歌手分类、SHA-256去重并避免覆盖，源文件不改；失败/暂停/取消导入任务持久化。WAV的RIFF INFO标题、歌手及专辑字段可读取。原生GUI实测多文件及文件夹导入、4条重复跳过、转换结果选择入库。媒体页实测四种指定格式互转、本地视频及Commons CC0远程视频，输出可完整解码。定向回归80 passed（24.45秒），后续小改动及新增回归14 passed（4.03秒）；未重复30首网络测试。完整证据与未解决项见 `docs/validation/PHASE3B4_VALIDATION.md`。没有进入Phase3C。

# Phase 3B.3 开发审计（历史）

本轮保留现有下载引擎，增加仅凭官方录音明确URL关系及一致元数据才能使用的本地身份桥接；未找到新近可核实允许完整中文音频下载的平台。Apple真实搜索三首均返回30项，歌名/歌手相符3/5/4，但中文下载仍为0，阶段未验收。搜索表格已改为歌曲、歌手、时长、操作四列并删除商店按钮；原生GUI《晴天》真实查找后显示重试。远程视频支持仅限官方核验CC0的Commons文件页或原始直链；Ex SIN.webm 页面及直链真实转换，MP3 48,620字节、可完整解码，落入隔离数据库，取消实测通过。定向测试70 passed，正式库schema9/2055条录音完整；来源计数与上一轮早期快照存在变化，详见 `docs/validation/PHASE3B3_VALIDATION.md`。不进入3C。

# Phase 3B.2 开发审计（历史）

最终整合：应用默认采用新的三页 MusicWindow，平台搜索优先，旧目录/审核界面代码保留。Apple iTunes 官方API无需密钥，原生GUI三个中文输入各返回30条；歌名/署名完全相符条目分别3/5/4（不是核实原唱录音数量），真实耗时5.10/1.85/3.32秒。MusicBrainz不再是必需前置。音乐目录信息不授予下载许可；中文真实下载仍为0。新文件保存为歌手目录下“歌手 - 歌曲.原格式”，拒绝冲突覆盖，不迁移旧文件。下载记录按歌手分组，未完成任务仍显示；三项简洁设置保留旧高级配置。实际视频能力由未实现推进为本地视频QProcess转换，可选imageio-ffmpeg 0.7.0已安装，自生成2秒视频转换为16,834字节MP3且完整解码成功，文件与任务落库；远程链接和yt-dlp仍未实现。研究IKUN指定的七个源码文件HTTP200，借鉴职责拆分，不复用未核实授权的隐藏接口。详细报告：`docs/validation/PHASE3B2_INTEGRATION.md`。整阶段仍未验收，不进入3C。

整合验证：定向回归68 passed（17.00秒），未重跑30首或完整pytest。初次文件冲突断言失败后恢复明确拒绝覆盖，复测通过。新GUI点击《晴天》下载：Openverse不同作品，ccMixter SSL证书过期，实际下载0；证书校验未关闭。正式库schema9、2055录音、3旧任务、68来源、既有文件登记/设置/审核逐行不变，integrity=ok、外键错误0。机器证据均在被忽略的`.local/reports/final-integration/`。

2026-11-14 中文目标补充：接入 Openverse 官方音频公开检索，实际请求“林俊杰 江南”经歌手+标题及标题回退返回4条线索，包括 hctmg 的《江南小镇》，该项既非林俊杰也非《江南》，标记 REVIEW_REQUIRED / LICENSE_UNVERIFIED，不下载。Windows 原生界面选择周杰伦《晴天》现场录音 `4e7860ff-72d1-408b-8001-ca5558906942`，Openverse 返回 Dylan Tinlun Chan《晴天雨》，不等于目标；任务 SKIPPED，未创建文件。另一次原生运行遇到 Openverse HTTP 500，独立记录失败；没有绕过该错误。来源线索不使用预览 URL 下载。

主界面新增打开下载文件夹，实际归档完成时显示绝对路径。新增 `DownloadRepository.completed_files()`，只读投影已有已验证文件的 Song/Recording、歌手、标题、绝对路径、格式、大小、SHA-256、完成时间、来源和完成状态；不增加上传或更改旧数据。本轮针对来源、下载、调度及 GUI 的测试 **82 passed in 25.23s**；未重跑 30 首覆盖或完整 pytest。原生 GUI、真实 API 及模拟测试分别记录在验证报告。尚未找到并实际下载完整授权中文歌曲，不能宣称本阶段验收完成；真实来源故障后成功切换至另一个授权中文文件也尚未验证。

已加入 YouTube 官方 search/videos 元数据客户端：无 key 返回 NOT_CONFIGURED，密钥放请求头并脱敏；仅模拟测试，未真实联网验证。结果查看目前禁用，通过后续核验后数据仅驻留短期内存、独立展示，不参与录音合并或下载；官方品牌展示规范尚未验收，配置 key 后仍保持 RESTRICTED，不影响其他来源。

GD 官方文档本轮真实 HTTP 200：仅限学习参考，明确禁止下载、传播和商用，5 分钟最多 50 次请求；此类聚合数据不被作为下载授权，自动收藏用途的检索许可尚未明确。

最新进展：已连接一键界面、歌曲身份确认、SearchOrchestrator 与现有音乐来源、单文件双重资格核验、限定任务运行及来源回退；每个音乐来源独立并发并逐个展示，来源失败互不阻断；歌手目录支持选择多个已确认歌曲或明确录音版本，不自动处理整个目录。单次一键可选实际下载或 dry-run，不改变全局设置。新增 schema 9 会话和来源尝试表。

真实隔离 CLI 与 Windows GUI 均完成英文 CC 控制样本的身份搜索→Recording 选择→Commons 搜索→核验→下载→SHA-256/SQLite 归档；MP3 5,369,410 字节，SHA-256 `4303f2a73ffd4e872503eb0898f62d7d0b9f1f15c783fcb3495e01c7383b6c00`；不计中文。30 首中文真实查询 5 首候选、7 文件许可未验证、25 首无结果、0 授权下载，耗时 812.19 秒。

尚未完成：yt-dlp/FFmpeg/FFprobe 视频处理后端，中文授权音频端到端，统一会话自动断点续搜，四个平台的合规真实搜索，额外格式真实下载验证；不将测试样本或搜索命中冒充完成。完整报告：`docs/validation/PHASE3B2_VALIDATION.md` 和 `docs/validation/PHASE3B2_COVERAGE_REPORT.md`。最新启用在线测试的全量 pytest **213 passed、0 skipped（331.42 秒）**；YouTube 接口仅使用模拟响应验证。正式库已升级至 schema 9，2,055 原始录音哈希一致，3 个旧任务及 68 个来源逐行保留。

2026-11-14：正式库实际 schema 8，Recording 2,055，人工审核 0，下载任务 3，来源注册 68；开发前 Git main 干净，origin 为 MelodyVault 仓库。备份与原始录音哈希保存在 `.local/reports/phase3b2/`。开发前 pytest：192 passed、2 skipped（未启用在线测试）；网易云受限边界定向测试 2 passed。

SuiSound 项目位于 `E:\users\yliu\SuiSound`，已只读审计 `lib/services/gd_source.dart` 和 `docs/chinese-catalog-review.md`。其网易来源实际依赖第三方 GD 聚合服务，不能证明网易接口或录音下载许可；官方网易搜索 API 和应用使用条件尚未核实。已增加默认禁用的 `NeteaseMusicSearchProvider` 边界，明确报告 RESTRICTED，不访问聚合站或隐藏接口；搜索、身份匹配与下载功能尚未实现。

YouTube 官方开发者政策对音视频下载及跨内容所有者的 API 数据聚合有明确限制，需在实现前评估；参见 https://developers.google.com/youtube/terms/developer-policies/ 。当时的统一搜索、调度、回退、GUI 和迁移尚未接入；现在的状态以上述最新进展为准。媒体后端和本阶段 Git 交付仍待完成。

补充要求：以用户最新 A → B → C 方案为目标，加入 Douyin；用户确认没有 YouTube Data API 密钥，本轮需明确 NOT_CONFIGURED。抖音官方关键词视频管理接口需要申请特殊权限、用户授权及与业务紧密相关的关键词，且仅返回最近一天的视频，不能假定它允许通用歌曲检索：https://open.douyin.com/platform/resource/docs/ability/search-management/video/ 。这些限制不妨碍继续开发允许访问的其他来源。

已新增独立的统一候选结构与有界 `SearchOrchestrator` 基础，覆盖来源故障隔离、逐个返回、取消及按来源 URL/录音/版本去重；这是当时仅有的基础，随后已接入现有来源、界面及下载；来源继续复用各自的缓存、限速和请求超时。该次基础定向测试 5 passed；上述初始全量回归并非最终 Phase 3B.2 验收。

# 当前阶段总览（2026-11-14）

**Phase 3B.1 开发与测试完成，等待验收；不进入 Phase 3C。** 下文历史 Phase 0–8 记录保留；新的未来范围以本表和 README 为准。

| 阶段 | 状态 / 验收 |
|---|---|
| 0 | 初始化已完成，历史 18 项 smoke 保留 |
| 1 | 既有 Song / Recording / Work、补证、人工审核保留；未确认作品不强制合并 |
| 2 | 既有音源搜索、真实任务进度、缓存/取消保留 |
| 3A | 既有歌手/歌曲/智能搜索与身份确认保留 |
| 3B | 严格资格、队列/续传/归档保留，本轮 MP3/WAV 真实控制重测通过 |
| 3B.1 | 194 passed in 309.93s，0 失败/0 跳过；真实 30 首/8 歌手、原生 Qt、schema 8 保留检查通过，等待用户验收 |
| 3C | 未开始：Drive / 阿里云盘上传、按格式去重 |
| 4 | 未开始：歌词片段搜索 |
| 5 | 未开始：自动化与定时任务 |
| 6 | 未开始：性能优化与 SuiSound 数据对接 |
| 7 | 未开始：Windows EXE 打包发布 |
| 8 | 原历史交付规划保留；本轮不开发，后续以用户确认的新版阶段为准 |

Phase 3B.1 验收结果：正式库 2,055 条原始 Recording 哈希全部保留，原 2 个 dry-run SKIPPED 任务及设置/人工确认不变；仅增加公共来源注册与调查历史。64 个新调查域名、68 注册域名；13 可访问、3 官方中文 API、2 具有完整文件元数据线索的来源，1 来源有与目标版本一致的候选；许可通过 0，中文真实下载 0/30。无结果 25，来源失败 0，7 个文件均授权未验证；MusicBrainz 歌曲查询另有 3 次 503 错误。

真实下载控制：开放外语 MP3/WAV 各 1 成功，不计中文。MP3 续传 RANGE_ACCEPTED、重复复用通过。缓存回归 HTTP 0（来源 0.5743 秒、发现 1.1831 秒）。原生 Qt 本地目录 572 行 / 0 请求 / 3.3594 秒，发现/启停/重检/取消通过；最大 UI 心跳间隔 1.4099 秒，保留性能限制。系统级 Computer Use 捕获失败，未标为通过。

失败记录：新增测试初次 SQL 占位符/IDNA 预期错误已修复；原生测试脚本漏选歌手候选已修正并重测；上传者与演唱者及 native cover 版本已纠正并真实补测；pip freeze 在首次提交前因无 HEAD 发出仓库检测警告，依赖版本仍成功保存且 pip check 通过。原始失败输出都保留。

未解决：通用全网 API 和 Jamendo 未配置；新站点尚待编译审核；35 外链尚未访问；中文权利链覆盖仍不足；FLAC 仅真实元数据，其余格式没有本轮合法中文真实文件；Windows/Python 矩阵和系统窗口捕获未完成。下一步仅进行用户验收，不自动开发 Phase 3C。

文档：根目录 14 个历史文件已迁移，原 README 另存历史说明；本地链接全部核对。查看 [本阶段验收](validation/PHASE3B1_VALIDATION.md)、[30 首覆盖](validation/PHASE3B1_COVERAGE_REPORT.md)、[来源设计](design/SOURCE_DISCOVERY_DESIGN.md)、[官方依据](research/PHASE3B1_SOURCE_RESEARCH.md)。Git 首次提交/推送按用户授权执行，实际 SHA 与远程验证另存本地交付记录。

---

# MelodyVault 开发记录

## Phase 3B：多来源下载与本地归档（实现/真实测试通过，等待用户验收）

用户通过附件明确授权本阶段下载引擎、真实开放许可样本和Windows测试。默认dry-run，正式实际下载关闭；真实下载只在明确开启的独立QA库。不得进入Phase3C、上传、播放、歌词或受限音频抓取。

审计实际基线：schema6、**2055条Recording**（高于旧报告1520）、人工审核事件0；不是恢复到旧数量。源文件、原始2055条payload哈希、SQLite备份保存在`.local/reports/phase3b/`，原113项基线实测113 passed/200.94秒。原下载/云端占位保留，新增互相隔离的下载模型/资格/传输/文件/队列/worker/仓储/UI，mutagen按实际需求安装。

验收标准：可靠Recording身份+完整文件+自动下载来源+明确私人保存许可+来源/URL一致才通过；HTTPS/SSRF/DNS固定/重定向约束、大小/哈希/实际媒体校验、part不覆盖原子发布；持久并发队列、暂停/继续/取消/有界重试/安全续传/真正进程重启；设置/原生GUI、开放MP3及WAV真实下载、三位歌手真实来源统计、全量回归和报告。不允许把跳过、就绪或许可字段核验算成功。

实现文件：`downloads/{models,targets,eligibility,manager,files,security,worker}.py`、`database/downloads.py`、`ui/{download_page,download_settings}.py`、共享`privacy.py`。仅追加v7迁移，保留v1–6。必要修改为MainWindow/SourcePage连接、来源Work别名轻量投影及后台准备、Commons版本词无结果扩大查询、有效版本查询v3缓存指纹、源证据凭据过滤、基础依赖mutagen和Git忽略规则；不推翻旧模型/审核。已选查询别名与版本在下载快照中保留，不把用户别名当官方作品证据。

真实文件：Kevin MacLeod《Silent Night》对应官方Recording `56c6eca2-5953-45d2-a7c2-54d6ab5833ef`/ISRC USUAN1100075，Commons CC BY3.0，MP3 **5369410字节/131.213075秒**，SHA256 `4303f2a73ffd4e872503eb0898f62d7d0b9f1f15c783fcb3495e01c7383b6c00`；Commons原生控制文件《Conillet de Vellut, on t’has perdut》，作者José Galeote/ESMUC，CC BY-SA4.0，WAV **24968780字节/130.044979秒**，SHA256 `7cf0414cced10263c76d78af1d094798da82b2ecdaca07e49107910c48ed368a`。WAV原生ID不冒充MusicBrainz，不改写正式录音库。

实际续传：早期裸ETag造成HTTP200，正确从头重下，不能计为206；已更正文字及验证器。最终GUI和真正子进程中断/新进程恢复均取得206，从131072字节继续，验证Last-Modified，最终SHA一致。进程39792被测试自身中断时SQL仍DOWNLOADING，新进程17452恢复为PAUSED再明确继续成功；不是只更换对象。真实文件重复任务复用，未知来源/试听/错误版本/许可证不明均有拒绝测试。

三位歌手最终各5首（15不同标题）：周杰伦2首有候选/2文件（Archive钢琴、Commons百科朗读），1文件许可字段明确，0符合目标下载资格；林俊杰与周传雄各无候选。合计无结果13、失败0，来源搜索57 HTTP，不含独立许可复核；商业目标实际下载0。Jamendo未配置明确跳过，不混入失败。数据见`artists-release/artists.json`。

原生GUI：`native-release/`通过实际输入、选择Recording/来源、默认dry-run无音频、明确开关/保存、新实际任务、暂停、重建窗口、继续/206、完成和可读证据。1040×720截图已查看；真实MP3启动到暂停/重建/继续/归档11.301秒，心跳974次/最大0.735秒。源查询3次HTTP与下载复核/媒体请求分别统计；没有计时器模拟进度。

测试：下载/来源定向套件59项曾通过（含原来源回归）；中间全量164 passed/321.28秒；URL有效查询身份/官方JSON错误4项补测通过，之后全量168 passed/297.26秒。补充所选别名/版本快照与原来源指纹相同的回归1项通过，第一次169项为168 passed/1 failed：旧统一搜索GUI等待器未等排队信号/来源统计就绪，已修正等待条件、保留业务断言，8项UI定向通过。最终 **169 passed /301.97秒**，0失败/错误/跳过（`pytest-verified.xml`），含原113项与新增56项。真实网络、真实本地文件/GUI、合成WAV/MockTransport均分别报告，不伪造全实网。

失败与修复保留：候选ISRC404不下载；锁字节PermissionError改为QUEUE_BUSY；Commons版本词硬过滤漏报；checkbox空白区点击/路径分隔符测试假设；原生脚本括号和信号等待竞态；早轮HTTP200误述纠正；睡眠式并发断言在负载下只观察到1流，改为barrier明确验证2流/上限。旧失败XML/目录不删改。设置写失败不假报保存；批量建立期间也落实暂停/取消。

保留性检查：2055原始哈希及旧1520子集、原Song身份/归属、全部原审核/来源/统一搜索缓存逐行一致；schema7/integrity/FK通过。正式download_jobs=0、automatic_download=false、默认目录`E:\users\yliu\MelodyVault\.local\downloads`。cloud、下载包占位、Archive/Jamendo适配器及Chrome实现原hash不变，SuiSound未修改。源码downloads不再被忽略，个人音频/旁证/DB/凭据仍被Git排除。editable元数据和mutagen1.48.1锁文件已更新，pip check通过。

交付已启动正式程序，读取到唯一MelodyVault窗口且Responding=True（`app-launch.json`）；继续使用原2055条录音库，正式下载开关关闭、正式任务0。真实MP3/WAV原文件已再次按实际大小和SHA256核验一致。当前停止，等待用户Phase3B验收。

文档：更新README/ARCHITECTURE；新增`docs/validation/PHASE3B_VALIDATION.md`、`docs/design/DOWNLOAD_ENGINE_REPORT.md`、`docs/research/DOWNLOAD_SECURITY_REPORT.md`；精确依赖`requirements/requirements-phase3b-lock.txt`。实际证据全部在`.local/reports/phase3b/`。

未解决/未验收：Jamendo无client_id未实网测、Archive缺具体权利链、未知CDN/许可继续拒绝；媒体结构校验不等于逐帧解码或声纹；Win11/其他Python/独立exe/网络盘异常未验收。没有本轮已知开发阻塞。最终全量及启动检查已通过，现已停止等待用户验收，不进入Phase3C或云端/播放功能。

## Phase 3A：歌手与歌曲统一搜索（实现/测试通过，等待用户验收）

本轮仅处理歌手/歌曲身份检索和现有音源搜索连接，不进入 Phase 3B。保留原始 Recording、Song/Work、人工审核及 Phase 2 来源模块；追加 v6 迁移，v1–5 未改。开发前数据库和 1520 条原始数据哈希已备份至 `.local/reports/phase3a/`。

验收标准：智能/歌手/歌曲模式、Enter/取消/清空；同名身份不强选；本地零网络、在线候选和逐批目录、查询类型及歌手身份缓存、旧任务隔离；确认单个版本后连接原来源搜索、不改变人工分组；真实指定查询、全部 pytest 和 Windows GUI。上述实现和本轮测试已通过，用户验收仍待进行。

实际文件：新增 `search/{models,services,selection,worker}.py`、`database/search.py`、`ui/unified_results.py`、`ui/request_relay.py`；最小修改 MainWindow、迁移、SourceQuery 用户查询别名和 pyproject。新增 13 项领域测试、5 项 Qt 测试，以及 `scripts/validate_phase3a.py`、`scripts/verify_phase3a_gui.py`。更新 README/ARCHITECTURE；设计、验收与锁文件为 `docs/design/UNIFIED_SEARCH_DESIGN.md`、`docs/validation/PHASE3A_VALIDATION.md`、`requirements/requirements-phase3a-lock.txt`。

真实 API：三个指定歌手身份均正确；裸“晴天”“江南”各 52 个歌手+Recording 候选/42 个演唱者身份，精确标题分别 26/14，不代表已核实作品。“周杰伦 晴天”8 个录音候选（7 名称一致）、“林俊杰 江南”6 个（4 名称一致）；约束到正确歌手，不自动选择版本。`Jay Chou Qing Tian` 官方英文检索仍无可靠别名，提供本地 7 个拼音弱线索，全部待确认，不作为官方别名或归并证据。四个不存在查询真实空结果。最终 12 条强制在线测试共 18 GET，含 3 次自然 503 重试；重复查询全部 0 GET。12 条严格本地查询全部 0 GET，服务耗时约 0.006–0.013 秒，详表见验收文档。

真实 Windows GUI：隔离真实数据库副本，13 项记录通过；三个模式、中文输入、Enter/点击、候选选择、来源任务、缓存、取消、清空和原数据不变。三位歌手目录完整显示，0 API；首个含索引重建/并行 IO 的显示 3.172 秒，其余 0.879/0.728 秒。裸“晴天”智能模式同时保留相关歌手和歌曲两类候选，不强选周杰伦；默认 1040×720 原生截图已查看。来源单首 6 GET 找到 1 个钢琴版，版本不匹配/许可未核验；已核实授权 0、未核实 1、无结果歌曲 0、失败 0，未下载。相同录音重复来源查询 0 GET，实发 1 GET 后的取消正常。QA 2 次选择仅写入副本，正式确认事件仍 0。

测试：领域 13 passed / 22.907秒、Qt 5 passed / 14.122秒；第一次全量 113 passed / 208.32秒；最终全量 **113 passed / 254.72秒**、0失败/错误/跳过（`pytest-accepted.xml`），含原95项与新增18项。初轮2项 mock 请求次数断言失败已修正，并新增完整多词标题优先回归；原失败报告保留。429/断网/超时等以故障注入覆盖，与上表真实 503 分开。editable 安装初次无隔离构建缺少 setuptools，改为正常隔离构建成功；`pip check` 通过。

数据保护：1520 条原始 Recording 哈希逐条一致，v1–5 checksum、原审核事件（0）保留，schema6/integrity/FK 通过；downloads/cloud 原文件与迁移前 hash 一致，SuiSound 未修改。所有 QA 数据/凭据/音频缓存排除 Git。全部真实结果、原始候选与截图在 `.local/reports/phase3a/`。

交付时已启动最终正常程序（`.venv\Scripts\pythonw.exe -m melodyvault --data-dir .local\runtime`），主进程 23868，窗口标题 MelodyVault、Responding=True，记录在 `app-launch.json`。普通沙箱进程查询无法读取桌面窗口标题，改为桌面权限读取后观察正常；不是程序启动失败。窗口留供用户验收，无自动网络/下载或下一阶段任务。

未解决/限制：英文音译不是官方别名，缺 Work/版本继续待确认；官方每次 50 Recording/25 歌手候选有界、未建立任意查询准确率数据集。同步 HTTP 取消等待响应或超时，多独立进程不共享限速。Jamendo 未配置，未找到可下载原唱，Win11/其他 Python/独立 exe 未验收。当前无本轮开发阻塞；下一步仅等待用户 Phase3A 验收，不进入 Phase3B、歌词/播放/歌单/在线播放或传输功能。

## Phase 2：目录性能优化与独立音源搜索（实现/测试通过，等待用户验收）

用户已明确授权进入Phase 2，并确认Jamendo没有client_id：实现适配器但明确显示未配置；授权无法核验时保存LICENSE_UNVERIFIED、原因和原始链接，不下载且不阻断其他来源。沿用现有Song/Recording和人工审核事件。备份为 `.local/reports/phase2/before-phase2.sqlite3`，原始哈希为 `baseline-hashes.json`。

验收标准：SQLite保存目录直接显示、普通目录不再等待深度补证、首次按页显示；独立低优先级补证可取消/强制刷新、正负缓存持久化、保留审核和原始录音；官方多来源元数据查询及独立Chrome会话、逐首/批量/缺失/失败重试、真实进度、授权原因与来源链接；三位歌手真实测试、全量pytest及Windows原生GUI，不下载音频。

已实现：catalog快速路径与EvidenceWorker、批量读补证完成点、按实体/歌手缓存及no_work检查时间、重复发行JSON按ID解码复用；独立SourceSearchEngine、Archive/Commons/Jamendo适配器、来源尝试/查询快照缓存、取消/错误隔离、候选匹配/许可字段检查、独立Chrome公开搜索/页面核验、双页面/右键单首/5首与批量/真实任务区域。追加schema v5，旧v1–4未修改。Chrome只访问已核实白名单和robots允许页面，阻止音频请求；没有使用隐蔽流或反自动化绕过。

最终代码全新目录（缓存0）周杰伦710录音、63.666秒/26请求/6次503重试，首批85录音在8.611秒；林俊杰443录音、53.453秒/19请求/7次503重试，首批89在5.055秒；周传雄368录音、17.360秒/10请求/1次503重试，首批100在2.001秒。Work补证不在此路径，新的无Work条目明确待确认。既有目录后台服务本地读取分别0.390/0.320/0.107秒、请求0；最终原生显示0.707/0.485/0.381秒、请求0，UI最大心跳间隔0.251/0.168/0.135秒。

独立补证真实缓存测试：首次分别14.147/4.950/19.596秒、网络0（复用已有真实官方页面和完成点）；再次整任务缓存仅约0.003/0.004/0.003秒、网络0。保存411/377/349条no_work负缓存及检查时间；不能把缺Work当重复或已核实。原生GUI三位均验证右键单首、5首、状态/许可原因、Chrome读取原始页面；周传雄强制补证2次真实请求后取消，3.011秒退出、已有368录音/347条目保留，低优先级及操作响应通过。

发现并修复：首轮旧GUI断言仍假定自动补证后3首Work，现改为快速目录4项待确认；Playwright CLI被系统Node16拒绝，使用已安装Python Playwright自带Node26运行独立CLI并连接真实Chrome156；初次原生测量15.567/7.680/3.712秒受QTest等待器持有GIL影响，保留报告后改用Qt事件循环复测；Commons的Solr式括号分组查询会漏报，已改为三语言短语查询、更新指纹使旧缓存失效，以真实肖邦音频返回5个开放许可文件作独立对照，未混入三位歌手统计。

最终三歌手单首与五首不同显示标题的真实来源查询完成：15个批量任务全部结束，已验证授权候选0、授权未验证候选1、无结果歌曲14、失败歌曲0。周杰伦“晴天”候选来自Archive钢琴合集，VERSION_MISMATCH且LICENSE_UNVERIFIED，保存原因/链接，没有认定原唱或下载。Jamendo未配置明确跳过，不混入无结果/失败。重复五首均0HTTP；错误来源可单独重试。独立Chrome156公开搜索/候选读取、可选浏览器来源与缓存、Commons真实许可页面均通过，音频响应0。

最终完整pytest **95 passed in217.22s**，0失败/错误/跳过，`pytest-accepted.xml`；含真实目录集成、95项原始/新功能回归、许可/版本/错误隔离/缓存/取消/线程/人工审核。线上自然503共14次重试，429/超时用明确故障注入，不谎报官方线上429。上一轮95 passed in187.82s及最初修复记录保留。`pip check`通过。全库1520条原始hash一致，v1–4迁移checksum及原审核历史一致，SQLite integrity/FK通过；downloads/cloud原文件不变，SuiSound未修改，所有运行数据/浏览器快照/缓存/凭据被Git忽略。

实际文件和复现见 [PHASE2_VALIDATION.md](validation/PHASE2_VALIDATION.md)、更新后的README/ARCHITECTURE与requirements-phase2-lock.txt，全部证据在 `.local/reports/phase2/`，最终原生截图在 `native-release/`。默认1040×720窗口也已检查，中文、许可状态、原因和操作按钮正常。

结束时已启动最终正常程序，使用 `.local/runtime`，观察到MelodyVault主窗口且Responding=True；`app-launch.json`保留进程记录。窗口留供用户验收，未启动自动下载或下一阶段任务。

待完成/限制：三位歌手尚无已核实目标音源；Jamendo因未配置无法实测，开放库/关键词有界不保证整网完备，完整权利链审批与传输均未实现；Win11、其他Python和独立exe尚未验收。Phase2本轮实现与测试结束，等待用户验收，不进入Phase3；下载/上传/断点恢复遵循用户本轮指示留到后续Phase5授权。

## Phase 1 三次完善：补证与可撤销人工审核（实现/测试通过，覆盖率目标未达，等待用户验收）

仅执行 Phase 1。已备份现有数据库至 `.local/reports/phase1-review/before-review.sqlite3`，保存全部1152条原始Recording payload的SHA-256（两位歌手存在1条共享Recording，所以710+443的歌手内计数不等于全库1152）。

本轮基线及最终真实结果：林俊杰443条原始录音 / 48首已核实作品 / 355项待确认（377条录音）；周杰伦710 / 192 / 380项待确认（393条录音）。**两位待确认均没有下降，自动覆盖率提升目标尚未达成。** 新增来源不足时不以标题相似/时长接近自动归并，也不伪造用户审核。

本轮验收标准：原始Recording/现有分层保留，强证据补查和可恢复，弱证据仅建议；审核可确认/拒绝/独立且可撤销、保留审计，刷新不丢决定，冲突需重审；默认Song一行/版本展开；两歌手真实回归、SQLite迁移兼容、全部pytest及Windows GUI通过，实际报告覆盖变化原因。

已实现：

- 追加v4迁移及catalog/reviews仓储；补充 `catalog/identity.py`、`supplement.py`、`review.py` 和 `ui/review_dialog.py`，整合现有service/grouping/MainWindow。providers/licensing/downloads/cloud原文件哈希一致，SuiSound未修改。
- 官方Recording/Work双向performance、有效ISRC关联、发行完整曲目、录音派生和官方canonical重定向证据；7天完成点/页面缓存支持继续，实际错误/取消不假称成功；无明确证据不自动确认。
- 弱建议显示对象/依据/置信度/Work/演唱者/版本；手动决定必须填写理由，Recording集合/证据/actor/时间持久化。事件与分组同事务，追加undo保留历史，冲突或撤销依赖失效时提示需重审，全部版本仍恰好分配一次。
- 默认显示全部403（林）/572（周）个Song条目，已核实和独立待确认各一行，版本折叠；重复发行不增加歌曲行。统计含已核实/人工确认作品、Work核实、待确认、已人工审核和全部版本。

实际测试与结果：

- 两位首次真实官方补证分别496/592次GET（含91/128次503重试）；最终回归另60/101次GET（含12/21次重试），完成49/80个ISRC查询，复用377/393个录音补证完成点。详情见 [PHASE1_VALIDATION.md](validation/PHASE1_VALIDATION.md) 和 `.local/reports/phase1-review/`。
- 全库1152条原始payload SHA-256一致，v1–3迁移checksum一致，真实数据库integrity_check=ok、foreign_key_check通过。新增发行位置使重复收录878→879、1665→1668，未新增原始音频或伪装成新作品。
- 作品归并不变的原因：林待确认中376录音无Work、1多Work/冲突；周387无Work、6多Work/冲突。周“不爱我就拉倒”增加1条明确身份辅助证据，但该录音原已通过发行上下文归并，因此核实作品/待确认数量不变；同ISRC疑似重复建档候选2对仍全部保留。
- 原生Windows审核GUI两歌手通过：隔离副本中分别完成合并/拒绝/独立和全部撤销，保留每位6个qa_automation事件，全部原始/版本未丢失。正式数据库人工事件0，不把测试动作算作用户审核。建议、审计、主窗口原生截图均已查看，中文及弱证据/版本信息正常。
- 最终全部pytest **73 passed in 469.16s**，0失败/错误/跳过，含两位歌手真实目录服务（复用真实缓存）与审核/撤销/持久化/冲突/取消/Qt测试；`pytest-final.xml` 保留完整结果。`pip check` 通过。
- 两位原生主窗口均通过：林俊杰403个Song顶层行/443版本，153.857秒，UI心跳4888、最大间隔0.083秒；周杰伦572行/710版本，196.085秒，心跳6196、最大间隔0.286秒。均验证中文输入/点击/禁用恢复/折叠展开/持久化一致，分别复用真实缓存19/63页、API0。缓存仍遍历证据并重建分组，约2–3分钟延迟尚未优化，界面保持响应。
- 主窗口审核按钮→真实审核窗口→加载355待确认→关闭→主窗口更新的原生验证通过，未新增审核事件；`native-review-entry.json`。原生测试仅向自有Qt控件发事件，使用隔离真实目录副本，不声称外部桌面自动化通过。
- 本轮结束已启动正常Windows程序，使用 `.local/runtime` 正式目录，观察到MelodyVault主窗口且Responding=True；`app-launch.json` 记录实际进程。窗口保留供用户输入歌手并验收审核功能。

未解决/阻塞：自动覆盖率没有提高；需要可靠社区作品关系或用户人工证据，不能降低阈值解决。缓存搜索仍有上述性能限制，部分版本未核实。当前无运行阻塞；本轮授权实现与测试已结束，Phase 1未标记完成。下一步等待用户验收和后续Phase 1指示，停止开发，不进入Phase 2。

## Phase 1 二次修复：歌曲与录音两层模型（实现/测试通过，等待用户验收）

用户反馈 710 行录音直接显示为歌曲，导致龙拳、龙战骑士等大量重复。本轮撤销“Phase 1 已完成”的当前状态，先完成分层模型、保守证据归并、版本展开、统计、真实数据与在线 API 回归，再记录验收结果。只涉及 Phase 1，不进入 Phase 2。

已备份当前 SQLite 至 `.local/reports/phase1-song-model/before-song-model.sqlite3`，并保存 710 个现有录音 payload 的 SHA-256。审计发现现有录音均未获取 work relations，不能以 368 个相同规范化标题直接当作独立作品数。将保留原始录音和 API 数据，仅新增证据与分组映射。

当前状态：本轮实现和自动验证已通过，**Phase 1 等待用户验收，未标记完成**。完整实际结果与口径见 [PHASE1_VALIDATION.md](validation/PHASE1_VALIDATION.md)。不进入 Phase 2。

- 已建立 Song→Recording 两层、保守 Work/ISRC/署名/发行位置及完整再版序列规则；阻止同名不同作品和未知桥接，支持简繁/标点/空格/官方英文别名，保留现场/Remix/合作版本和证据。
- 原始710条录音全部保留且payload SHA-256逐条不变。v3新增快照/历史、Work关系与派生映射，v1/v2 checksum不变；仅重建派生Song映射，不删除录音。当前3550条原始/补充快照和148条API响应历史，均不入Git。
- 真实当前结果：192首已核实独立作品；另380项待确认，涉及393条录音。共572个派生Song/候选条目，保留710个版本，其中138个为条目下附加版本。当前发行中的重复收录为1665（2277位置−612录音）；不能与旧2182直接比较口径。
- 龙战骑士2条录音归入同一Work，正式非现场版本为主版本；龙拳7条原始录音中4条归入已知Work，另3条独立待确认。默认已核实区每首一行，待确认在独立折叠分区，全部可展开核对MBID/版本/证据。
- 首轮43 passed / 3 failed / 1 deselected：旧分页/恢复断言未区分Work证据请求，另触发旧10秒测试等待；已修正。完整复测 **50 passed in 126.31s**，0失败/错误/跳过；包含当前真实数据、原始记录保留和分层规则测试。
- 再次在线请求通过：显式忽略页面缓存，75次真实请求、12次503重试、缓存0；首次Work证据补取另为79次请求、15次重试。没有模拟歌曲替代真实来源。
- Windows Qt原生流程通过：输入/点击/后台处理/折叠/展开版本/待确认分区/统计/持久化/按钮恢复；32.268秒，968次UI心跳，最大间隔约0.120秒。该UI回归明确复用63页真实缓存，在线刷新已分开验证。
- 已启动并保留修复后的窗口，展开龙拳可见4个录音。启动复核功能通过但测得1.406秒最大心跳间隔；移除测试监视器自身在UI回调中的同步日志后，同数据复测29.254秒通过、868次心跳、最大间隔0.115秒。全部测量原样保留在验证文档和本地JSON中。
- `pip check`、SQLite integrity_check/foreign_key_check、710条唯一分配、旧payload和迁移checksum检查通过；下载/上传/授权/providers模块原文件校验一致，SuiSound未修改。
- 证据目录 `.local/reports/phase1-song-model/`，含 `pytest-final.xml`、`online-refresh.json`、`validation-data.json`、`native-gui.json`和截图；详细复现命令见验证文档。

未解决：380项仍需作品关系或人工证据；版本/正式发行证据不完备时不假定录音室或自动确认。当前没有批量人工强制归并界面。已完成本轮授权范围，停止等待用户验收，不继续Phase 2。

## 上一轮 Phase 1 验收记录（历史；歌曲归并问题已重新打开）

用户已确认进入 Phase 1。当前唯一项目位置仍为 `E:\users\yliu\MelodyVault`。本轮验收已完成，**停止等待用户确认，不进入 Phase 2**；未修改 providers、licensing、downloads、cloud。

### 验收标准与交付

- 官方 API 搜索并核对 Artist MBID，分页读取录音、发行组、正式/单曲/EP/合作曲目，规范化简繁名称，按录音身份去重并保留版本。
- 只展示歌曲名称，后台 SQLite 保存完整相关元数据；搜索使用 QThread，禁用/恢复按钮，显示真实阶段进度和实际错误，可取消并在重新搜索/重启后复用成功页面。
- 真实周杰伦 API 测试和 Windows 原生输入—点击—后台请求—显示—持久化流程均通过；下载/上传模块与 SuiSound 未修改。
- 实现文件：`catalog/{musicbrainz,service,models,normalize,worker}.py`、`database/catalog.py`、追加 v2 迁移、更新现有 UI 和 app 入口；新增 CLI 复现入口、原生 Qt 验收脚本和测试。OpenCC 为实际使用的新依赖，精确版本见 `requirements/requirements-phase1-lock.txt`。

### 真实获取数量

官方身份：[周杰倫 / Jay Chou](https://musicbrainz.org/artist/a223958d-5c56-4b2c-a30a-87e357bc121b)，TW，1979-01-18，MBID `a223958d-5c56-4b2c-a30a-87e357bc121b`。应用通过查询/别名/lookup 核对，不在生产代码中硬编码此歌手身份或歌曲。

| 指标 | 实际结果 |
|---|---:|
| 音频录音版本（Recording MBID 去重后） | 710 |
| 规范化标题（不同录音可能同名） | 368 |
| 已关联正式发行曲目的音频录音 | 612 |
| 多艺术家署名录音 | 67 |
| 发现的不同录音 MBID（含视频） | 952 |
| 排除的 video=true 条目 | 242 |
| 相同 MBID 重复收录消除次数 | 2182 |
| 关联发行组（仅后台） | 79（含 15 个 Single、5 个 EP） |
| 正式发行版本（仅后台） | 253 |
| 目标歌手相关曲目 | 2212 |

分页：直接录音 10 页/918 条，直接发行组 1 页/55 条，正式发行 6 页/223 个版本，合作/合辑发行 2 页/30 个版本。正式发行实际页大小 34/31/33/70/42/13，合作页为 17/13；按实际返回数推进 offset，未按固定 100 跳页。后台发行组包含 Single、EP 和 Album，不在 UI 展示列表。

首次完整后端调用于 2026-11-13T18:33:32Z 完成：28 次网络请求、7 次 503 重试、缓存命中 0。`.local/reports/phase1-jay-chou-live.json` 保存完整数量和录音证据。本次目录不声称歌手全部作品已经收录。

### 测试与原生 Windows 验收

- 初次回归/离线边界测试：30 passed。
- 完整 pytest（`MELODYVAULT_LIVE=1`）：**35 passed in 56.04s**，0 failed / 0 errors / 0 skipped。包括真实官方目录集成、v1→v2 保留数据、分页/去重/版本/简繁/合作曲目过滤、缓存/取消/恢复/错误、Qt 线程/心跳/按钮/关闭。JUnit：`.local/reports/pytest-phase1-final.xml`。
- 真实集成 pytest 复用第一次官方获取的 20 个页面，新增网络请求 0，得到相同 710 个录音；报告 `.local/reports/phase1-live-pytest.json`。离线 `tests/catalog_fixtures.py` 从不被生产应用导入。
- **全新数据目录的 Windows 原生 Qt E2E：通过。** 实际 `windows` Qt 平台、输入框提交“周杰伦”、Qt 鼠标点击搜索、真实 QThread/HTTP 请求、搜索中禁用按钮、完成恢复、显示 710 行、SQLite 内容与表格 MBID 一致；并确认只有歌曲列，没有专辑列表。
- 本次 E2E 历时 36.785 秒，27 次真实官方请求、6 次 503 重试、缓存 0；工作期间 UI 心跳 1160 次，最大心跳间隔 0.062 秒。输出 `NATIVE_CATALOG_E2E_OK 710`，退出 0。
- E2E 报告 `.local/reports/phase1-gui-live.json`；原生截图 `.local/reports/phase1-gui-live.png` 已查看，中文和不同录音版本正常显示。数据保存在 `.local/phase1-gui-live`；正常运行数据 `.local/runtime` 也已保存真实目录。
- `pip check`：No broken requirements found. README、ARCHITECTURE、依赖清单同步更新；所有运行数据/报告/缓存仍被 Git 忽略。
- 根据迁移前 SHA-256 清单核验，providers、licensing、downloads、cloud 四个模块内容未变化；SQLite integrity_check=ok。后台保存 3614 个完整发行曲目条目，其中目标歌手相关音频曲目为上述 2212 个，未把其他歌手的合辑曲目显示到歌曲表。

复现命令（项目根目录，PowerShell）：

```powershell
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
.\.venv\Scripts\python.exe -m melodyvault.catalog --artist '周杰伦' --data-dir .local\runtime --report .local\reports\jay-chou.json
$env:MELODYVAULT_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-new --junitxml=.local\reports\pytest-new.xml
# 原生 E2E 需要全新数据目录，确保发生真实请求
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --data-dir .local\gui-new --report .local\reports\gui-new.json
```

### 实际失败、限制与下一步

1. MusicBrainz 多次真实返回 HTTP 503 busy，已按限速/Retry-After/有限重试恢复，UI 显示实际原因。永久失败保持 failed，允许再次搜索复用已完成页面，不能伪造完成。
2. Computer Use 首次返回 `Computer Use app approval timed out`，重新选择窗口后又返回 `FrameArrived timed out: timed out waiting on channel`。未把外部桌面操控记为成功；改用自有窗口内的原生 Qt 输入/点击/真实 API 测试，已通过且保存截图。
3. MusicBrainz 社区数据存在缺失、同名不同 MBID 的重复建档或署名差异。不能仅凭标题合并；未标注版本的不同 MBID 仍分别保留，tooltip 显示原始标题与 MBID。
4. 98 个音频录音尚未在本次正式发行曲目中找到关联，UI tooltip 标明发行状态未核实；视频条目不计入音频结果。任何正式发行/目录元数据都不是下载许可。
5. 取消当前 HTTP 请求需等待其结束，HTTP 超时设为 20 秒；MusicBrainz 不提供本次跨页原子快照，数据在读取期间可能变化。缓存 7 天，可显式刷新；这不是全部作品或永久新鲜度保证。
6. 自动全库备份、跨进程统一调度、音频授权/下载/上传及 Windows 11/独立 exe 交付均未在本阶段实现或验收。无 Phase 1 阻塞。

下一步：等待用户确认 Phase 1，再按明确授权进入 Phase 2；当前停止开发。

## 2026-11-13 项目迁移

- 用户要求将项目移到当前工作区，并删除之前的项目。当前唯一开发位置调整为 `E:\users\yliu\MelodyVault`。
- 已复制并通过 SHA-256 校验 162 个文件，包含源码、文档、依赖清单、运行数据库、日志、报告和 pip 缓存，共 263,367,671 字节。
- 保留 E 盘现有 Git 仓库及 origin；D 盘独立仓库无提交历史。未复制旧虚拟环境、空 Git 元数据和可重新生成的 Python/pytest/pip 临时文件。
- 在 E 盘重建虚拟环境和 editable 安装，避免安装入口引用 D 盘旧目录；README 运行路径同步调整。本次不进入 Phase 1。
- 迁移验收已通过：`pip check` 无损坏依赖；SQLite v1 在 E 盘初始化成功且原有元数据/迁移历史完整保留；原生 Windows GUI smoke 正常退出；`pytest` 为 `18 passed in 4.07s`，无失败、错误或跳过。
- 已确认模块导入路径、虚拟环境和 `melodyvault.exe` 入口均使用 E 盘。删除前再次核验全部 162 个原文件，确认当前 Git 保留、D 盘仓库无提交历史且原目录无链接。
- 旧目录清理已完成：`D:\Development\MelodyVault` 已删除，仅保留当前 E 盘项目。未修改 SuiSound，未提交或推送 Git。
- 完整迁移校验清单与验收结果分别位于 `.local/reports/migration-source-manifest.json`、`.local/reports/migration-verification.json`；本轮 JUnit 报告为 `.local/reports/pytest-migration.xml`。迁移完成后继续停留在 Phase 0，等待用户确认后续阶段。

以下为 2026-11-12 在 D 盘执行 Phase 0 的原始历史记录，其中路径和当时目录状态仅代表原始验收时点。

记录日期：2026-11-12（America/Los_Angeles）。范围：仅 Phase 0。后续阶段划分为初步路线，每阶段开始时细化验收；必须等待用户确认，不自动继续。

## 环境审计

- 当前工作区 `E:\users\yliu\MelodyVault` 只有未提交、无历史的 `.git`，没有应用源文件；完整保留其内容，没有覆盖。
- D 盘存在，`D:\Development` 未发现同名项目；经写入授权实际创建 `D:\Development\MelodyVault`，以该目录为唯一源码项目位置。
- SuiSound 是旁边的其他项目，未读取其源码，也未向其写入。
- `python` 指向不可用 WindowsApps 别名，`py` 未发现解释器；找到并使用 `C:\Users\yuxiang\AppData\Local\Programs\Python\Python313\python.exe`，版本 3.13.2。
- `.venv` 与所有本项目缓存/临时文件放在 D 盘。未安装全局 Python 包、未更改系统 PATH、未连接任何账户。

## Phase 0–8 状态与验收

| 阶段 | 状态 | 验收标准 | 真实测试 / 结果 | 阻塞与下一步 |
|---|---|---|---|---|
| 0 初始化 | 已完成，用户已确认继续 | src 布局、模块、pyproject、配置、日志、SQLite 迁移、隐私忽略、三份文档齐全；桌面入口/DB/pytest 实测通过 | 原阶段 18 passed；迁移后 18 passed；v1→v2 回归通过 | 无阻塞 |
| 1 歌曲目录 | 已作为用户授权Phase2的现有基线；覆盖率限制保留 | 分层、强证据、人工审核与撤销、版本/统计、原始保留和真实API/UI | 原73 passed；Phase2全量95回归；原始/审核历史保留；待确认未强行减少 | 原缓存慢问题已由Phase2任务拆分解决；未知作品继续待确认，不冒充全部核实 |
| 2 性能与来源搜索 | 实现/真实测试通过，等待用户验收 | 本地直读/partial、独立补证、官方多来源/独立Chrome、许可原因/匹配、真实进度、取消重试缓存、双页UI | 95 passed；三位歌手首次在线与原生流程；15来源任务：0许可核实/1未核实/14无结果/0失败 | 已停止等待用户验收；Jamendo未配置、目标音源授权未找到，见PHASE2_VALIDATION.md |
| 3A 统一歌手/歌曲搜索 | 实现/真实测试通过，等待用户验收 | 智能/歌手/歌曲模式、身份候选、保守版本匹配、明确确认、本地与在线缓存、线程与取消、来源连接 | 最终113 passed/254.72秒；13项原生记录、真实API及本地计时，见 PHASE3A_VALIDATION.md | 英文拼音仅弱线索，官方索引有界；不宣称全部作品或音源已核实 |
| 3B 合法下载/本地归档 | 实现/真实测试通过，等待用户验收 | 独立资格/原始完整音频、持久队列/续传/文件校验/默认dry-run/GUI与数据保留 | 最终169 passed/301.97秒；真实MP3/WAV、206/新进程恢复、三歌手统计及原生GUI，见PHASE3B_VALIDATION.md | 正式实际下载关闭；不进入Phase3C；Jamendo/Archive限制保留 |
| 3C | 未开始、未授权 | 等待用户明确范围 | 尚未运行 | 本轮不得进入 |
| 3 完整授权核验（历史后续规划） | 未开始；Phase2仅来源许可元数据检查，本轮3A另列 | 可追溯完整证据、具体录音下载与私人保存明确许可、未知默认拒绝 | 后续需完整权利链与真实正反例；不能把Phase2字段检查当传输审批 | 无证据不得进入下载 |
| 4 后续保留阶段 | 未定义/未开始；用户最新将传输放在Phase5 | 范围和验收需用户明确，不自行增加功能 | 尚未运行 | 当前仅Phase3B，原Phase4下载路线以用户最新指示为准 |
| 5 下载/私人Drive/恢复（后续整合） | 本地下载部分已由用户授权3B实现，Drive仍未开始 | 完整许可音频原子下载/校验；drive.file私人文件夹上传；取消/重试/断点恢复/去重/远端确认，无公开共享 | 尚未运行；后续需真实许可音源、中断/损坏、用户测试账户OAuth/上传/撤销 | 当前未改downloads/cloud；未来需独立明确授权与配置 |
| 6 任务编排 | 未开始 | 所有网络任务可取消/重试/恢复，重启状态一致，不重复执行 | 尚未运行；需真实任务取消、进程重启与失败恢复 | 依赖各服务可恢复接口，避免 UI 主线程网络 I/O |
| 7 桌面整合 | 未开始 | 歌手到歌曲操作流、明确未找到/授权不足/失败，进度与取消，界面无专辑 | 尚未运行；需真实 GUI 完整流程与异常测试 | 不能用假成功数据通过验收 |
| 8 打包与交付 | 未开始 | PyInstaller 独立运行，Win10/Win11 干净环境，隐私扫描和回归通过 | 尚未运行；需双系统、无 Python 环境真实安装/运行 | 当前交付不是独立 exe；后续确认打包形式 |

## Phase 0 已完成

- D 盘独立项目及虚拟环境；UI / catalog / providers / licensing / downloads / cloud / tasks / database 与 tests 边界。
- PySide6 本地窗口、歌手输入、无专辑歌曲表、明确禁用尚未实现的搜索。
- 非敏感配置模板、显式 CLI 和环境覆盖、D 盘优先数据策略。
- 旋转日志、常见敏感字段脱敏、失败退出码。
- SQLite v1，事务迁移、checksum 历史核验、拒绝降级，真实文件测试。
- 可选依赖分组，浏览器/云端/音频/打包暂不安装。未实现任何外部网络业务。

## 实际失败、修复与限制

1. 初次发现 `python` 无法运行、`py` 无解释器：改用找到的 Python 3.13.2 绝对路径，无需修改全局环境。
2. 第一次源文件批量生成因 PowerShell 传递 `python -c` 引号导致 SyntaxError：当时没有生成源文件；改为 UTF-8 标准输入后创建成功。
3. 第一次广泛枚举文件时，沙箱读取 pip 正在使用的临时目录被拒绝：未影响安装或源文件，后续限定枚举源码/测试，避免递归扫描运行缓存。
4. offscreen Qt 截图字体显示方框，不能用作视觉验收：改用真实 `windows` Qt 平台重新渲染，默认 Microsoft YaHei UI 字体下中英文均正常，已人工查看原生截图。offscreen 仅用于事件循环测试。
5. pytest 首次运行 18 项全部通过，未发现产品代码测试失败。Phase 0 不测试真实歌手、合法来源、下载、OAuth 或上传，不能宣称这些能力完成。
6. 当前只在 Windows 10 build 19045 / Python 3.13.2 真实运行；Python 3.11/3.12、Windows 11 与无 Python 独立 exe 尚未验证。无 Phase 0 阻塞。

## 测试实录

实际工作目录：`D:\Development\MelodyVault`。下列命令均已执行，退出码均为 0：

```powershell
.\.venv\Scripts\python.exe -m pip install -e 'D:\Development\MelodyVault[test]'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m melodyvault --version
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --init-db
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --init-db
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --smoke
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-tmp --junitxml=.local\reports\pytest.xml
```

- 安装版本：PySide6 6.12.0、httpx 0.28.1、pytest 9.2.0；其余精确版本在 `requirements/requirements-phase0-lock.txt`。
- `pip check`：`No broken requirements found.`
- CLI：`MelodyVault 0.1.0`；SQLite 3.45.3，schema v1。
- 两次初始化均返回 schema_version=1；pytest 进一步验证数据持久化、不重复迁移、关闭连接、WAL/外键、checksum、失败回滚与修复后升级重试、拒绝未来版本。
- 原生 Windows 桌面 smoke：`GUI_SMOKE_OK: MelodyVault window visible; event loop running`，窗口自动关闭，进程退出 0。
- pytest：`18 passed in 2.60s`，0 failures、0 errors、0 skipped。范围：8 项配置、5 项 SQLite、1 项日志、4 项入口（其中 1 项实际 Qt 事件循环）。
- 真实 Qt 控件检查：搜索按钮禁用，歌曲目录为空，表头无专辑；原生截图已查看，中英文显示正常。
- Git：D 盘初始化独立本地仓库，未提交、未推送。`git check-ignore` 检验 `.local` 数据库、credentials、token、client_secret、音乐、缓存、本地配置和虚拟环境共 8 个路径均被忽略；原 E 盘仓库仍为空、未修改。
- 报告：`.local/reports/pytest.xml`、`phase0-verification.json`、`phase0-window-native.png`、`phase0-results.md`。offscreen 截图另存为 `phase0-window.png`，其字体限制见上。
- 数据库：`.local/runtime/database/melodyvault.sqlite3`；日志：`.local/runtime/logs/melodyvault.log`。以上运行文件均被 Git 忽略。

## 下一步

Phase0已验收，Phase1/2作为现有基线保留，用户已授权本轮Phase3B。当前用户已授权Phase3B并完成本地下载实现与真实验证；最终检查后停止等待Phase3B验收，不进入Phase3C、歌词/播放或云端上传。


## Phase 3B.1 — 开发中，等待本阶段验收

2026-11-14：重新审计正式库 schema 7 / 2,055 Recording / 2 个 dry-run SKIPPED 任务；备份、原始 payload 哈希已保存 `.local/reports/phase3b1/`。开发前真实执行旧测试：169 passed in 307.60s。现有 Git main 无提交，origin 空仓库；用户原有文件均保留。

验收标准：动态来源注册与审计、默认待审核、严格文件权利链、中文固定 30 首/8 歌手真实统计、全部回归、原生 GUI、数据哈希保留、文档迁移、敏感文件排除及授权 Git 推送。

已实现：schema 8 追加迁移、公开百科外链/可选 Brave API、查询计划、robots 与受限页面拒绝、公共 DNS 固定、大小/类型/重定向限制、缓存和失效停用、编译适配器审批、ccMixter 元数据适配器、独立后台和音源发现页面。候选的文件格式/大小及不同文件 ID 保留。

开发测试：原下载/来源/UI 定向回归 69 passed；新增调查测试初次 5 failed（SQL 占位符数量和测试 IDNA 预期值），已修复，20 passed。不是最终验收结果。

阻塞/限制：无全网搜索 API / Jamendo client_id；公开目录外链不等同全网覆盖；ccMixter 中文翻唱和传统歌曲权利链未核实则拒绝下载。下一步：30 首真实网络测试、原生 GUI、完整回归、数据保留核对及真实授权音频验证；最终结果见本阶段验证文档。
