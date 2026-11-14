# MelodyVault 架构

## 当前实现：Phase 3B.1（等待验收）

新增来源发现域 `discovery/` 与 `database/discovery.py`，不替换现有目录、搜索或下载领域。schema 8 追加网站、能力、发现/核验历史和查询缓存；原 v1–7 不变。
`DiscoveryPage → DiscoveryWorker → SourceDiscoveryService` 是独立可取消的后台链；动态发现网站只产生调查数据，不创建远程插件。`providers/base.py` 定义编译适配器统一协议。
SourceSearchEngine 根据来源注册表的审核、启停、过期和健康状态控制适配器；新增 ccMixter 只读取官方 JSON。Candidate 增加格式/大小，文件身份独立于歌曲身份；资格审核每次刷新文件许可及原始字节证据。
普通网站的发现、可访问、支持搜索、完整音频证据和下载授权分开记录。网络调查复用公共 DNS 固定传输，体积/类型受限，不跟随重定向，不执行网页指令。
完整边界、缓存/停用策略和文件授权规则见 [SOURCE_DISCOVERY_DESIGN.md](design/SOURCE_DISCOVERY_DESIGN.md)，官方接口依据见 [来源调查](research/PHASE3B1_SOURCE_RESEARCH.md)。

用户已授权Phase3B。保留Song→Recording/Work、原始数据、可撤销审核及Phase2/3A目录/来源/统一搜索；新增独立下载资格、受控媒体传输、本地归档和持久队列。默认dry-run，用户明确开启后新建实际任务；不开发上传、播放、歌词、歌单或Phase3C。

## Phase 3B 独立下载层

`MainWindow → DownloadPage / DownloadSettingsPage → DownloadWorker(QThread) → DownloadManager(ThreadPoolExecutor)`；领域调用`SourceSearchEngine → DownloadEligibilityService → audio_client → files.verify_file/publish`，以DownloadRepository持久化。下载层不调用播放器/云端，SourceSearchEngine仍只读元数据，不因匹配分数发音频请求。`privacy.py`是共享的数据过滤层，来源仓储不反向依赖下载引擎。

`DownloadCandidate`记录目标身份、版本、文件URL/格式/大小/时长、许可/下载/私人保存权限、匹配/完整性、依据/时间及署名限制。资格审核每次刷新官方文件信息；不把用户确认当许可、不按同名自动选录音，Archive/浏览器缺具体权利证据时拒绝。目标与许可、元数据与媒体校验分层；真实来源原生控制ID使用独立namespace，不冒充MusicBrainz UUID。

v7只追加下载任务、尝试、已核实文件、只追加证据与设置，v1–6不变。目标及设置快照与原目录分离。进程锁保护同一队列，线程池限并发、每来源文件独立锁，支持协作暂停/取消、手动有界重试及重启恢复。临时文件只在独立目录中按任务UUID处理；校验后同卷发布且不覆盖不同内容，旁证和数据库登记成功才COMPLETED。

原来源搜索新增版本词无结果时扩大检索，仍经过原匹配及新资格审核；仅此类查询使用v3指纹，旧缓存保留。SourcePage只读取必要Work别名投影，完整Work准备在SourceWorker中，避免主线程大JSON解码。UI下载表轮询轻量SQLite投影显示真实字节/速度/ETA，线程发信号更新状态；定时器不生成进度。

下载设置单独持久在SQLite：默认实际下载关闭，默认根为项目`.local/downloads`，并发1–4、质量为原始/无损优先/较小文件优先（不转码）、总限速和临时策略。变更不会静默把旧dry-run升级为实际任务；运行任务先暂停，新任务采用新设置。关闭等待所有worker并保存状态，重启不自动执行。

详细状态/续传/原子边界见[DOWNLOAD_ENGINE_REPORT.md](design/DOWNLOAD_ENGINE_REPORT.md)，域名/DNS固定/许可/文件/凭据边界见[DOWNLOAD_SECURITY_REPORT.md](research/DOWNLOAD_SECURITY_REPORT.md)，实际文件、失败和测试证据见[PHASE3B_VALIDATION.md](validation/PHASE3B_VALIDATION.md)。

## Phase 3A 搜索层

`search/models.py` 定义 SearchRequest、SongCandidate 和 SearchResult；`search/services.py` 提供 ArtistSearchService、SongSearchService、UnifiedSearchEngine；`search/selection.py` 将用户选择的精确 Recording 关联现有 Song 模型；`search/worker.py` 负责后台执行。`database/search.py` 维护派生索引与带模式、歌手身份、目录 revision 的缓存。领域层不依赖 Qt，UI 通过 `RequestRelay(QObject)` 在主线程接收带 generation 的消息，旧任务结果不能覆盖新搜索。

输入框支持智能/歌手/歌曲、Enter、取消、清空、可选歌手条件及严格零网络本地模式。歌曲候选保留演唱者/Work/版本，裸歌名不因本地只存一位歌手就默认选中。已有明确歌手绑定可直接进入保存目录，其他歧义展示两类结果。目录完整分页和审核仍由原 catalog 承担；确认歌曲后只将所选 Recording 送入现有 SourceSearchEngine，允许缺少 Work 但不把匹配当下载成功。

v6 只追加统一索引、查询缓存、用户目标选择审计和用户查询别名表，以及目录变更 revision 触发器；v1–5 不变。既存 Recording 的确认不更新原始数据/现有 Song/人工历史。新 Recording 先核对官方署名和版本，不覆盖已人工审核组。原始页面、关系快照与可重建搜索索引分开。用户选择审计 append-only，不是原 merge/reject/independent 审核命令。

查询结果成功缓存 7 天、真实空结果 6 小时，错误不负缓存；强制刷新跳过结果及页面缓存。拼音仅是弱线索，全部保留待确认，不伪装官方别名。细节、并发/版本边界和限速见 [UNIFIED_SEARCH_DESIGN.md](design/UNIFIED_SEARCH_DESIGN.md)，实际验收见 [PHASE3A_VALIDATION.md](validation/PHASE3A_VALIDATION.md)。

## Phase 2 独立任务和数据边界

- `CatalogWorker → CatalogService.search_catalog`：保存目录只读SQLite，不调用HTTP。明确刷新或首次获取才遍历官方目录页，真实页完成即发partial信号，使用现有Work和人工决定重建分组。legacy `CatalogService.search` 保留完整流程供历史回归，应用和普通CLI使用快速路径。
- `EvidenceWorker(LowPriority) → enrich_artist`：只对已存歌手补证，不搜索/刷新目录。按Recording集合摘要缓存整任务；每Recording正/负Work检查及时间、逐录音补证完成点、Work/API页面缓存保留。刷新目录优先时请求取消旧补证，结束后异步开始刷新；已有目录和来源任务仍可操作。缓存读取和批量完成点查询避免逐录音SQLite连接/无意义写入；发行JSON按ID解码复用。
- `SourceWorker → SourceSearchEngine → injected providers / SourceHTTP`：领域引擎不依赖Qt。每首歌/每来源独立尝试，失败不取消其他来源；当前队列总数/实际完成/候选/许可/无结果/失败计数由引擎生成。单首、批量、缺失（无已核实匹配来源）、失败/取消重试均使用同一入口。
- `providers/archive.py`使用官方高级搜索和文件metadata；上传者声明的许可不自动视为已核实权利，保留原因。`commons.py`按简/繁/英文短语分别查询CirrusSearch，不能使用Archive的Solr括号表达式；每变体最多5个音频页，只解析官方imageinfo/许可metadata。`jamendo.py`仅配置官方client_id后发请求，明确检查audiodownload_allowed和CC许可。
- `sources.matching`的分数仅作筛选，名称一致不确认原唱/同一录音；钢琴合集、翻唱、伴奏、现场、重录等有独立版本判断。Commons作者/上传者不填充演唱者。未知候选时长保持未知，不借用目标录音时长伪造匹配。
- `licensing/source_evidence.py`仅核对Phase2官方文件级许可字段；未知/限制/无明确许可保持LICENSE_UNVERIFIED和理由。LICENSE_VERIFIED表示来源元数据有明确开放许可；仍不颁发下载执行审批，录音身份和完整权利链需后续核验。已核实匹配来源统计同时要求元数据匹配；不是对所有互联网来源或版权真实性的保证。
- `sources.browser.PublicBrowser`自行启动Playwright Chrome及空白临时context。白名单公开Archive搜索/详情、Commons文件说明页；先读robots，不登录、不隐身绕过、不共享用户资料。候选网页按公开DOM读取，Archive搜索等待实际结果标题和结果feed，不能将未渲染页面/导航链接当结果。媒体/下载端点及第三方主机请求阻止；访问控制或验证码停止。API已失败时不自动改用Chrome绕过。API和浏览器属于独立来源尝试，可选补充浏览器搜索；读取授权页面不升级已有许可。
- SourcePage保留工作线程自己的歌手/查询快照；切换歌手不把旧来源结果应用到新歌手。所有界面更新通过排队signal，关闭等待全部目录/证据/来源/浏览器线程结束。原生测试用Qt事件循环等待，避免Python循环QTest.qWait持有GIL污染工作线程耗时。

v5仅追加 `catalog_task_cache`、`source_runs/jobs/attempts/browser_checks` 和缓存索引，v1–4不变。来源尝试追加保存查询（包括Recording集合）、provider、时间、错误、候选及许可理由/链接。成功候选24小时、空结果6小时；失败不复用为成功。指纹版本为source-query-v2，防止修正查询语法后沿用旧空结果。人工决定与派生映射原子提交时一并保存审核统计快照，本地读不必重新播放昂贵证据任务。

来源搜索有明确的有界结果数，空结果指本次已配置来源/关键词和结果上限内没有可用候选，不代表整网没有合法来源。来源子系统不请求音频；Phase3B实际传输仅由资格审核后的独立下载层执行，Drive不变。Jamendo未配置不混记为真实无结果/失败；配置情况保留在任务记录。

采用 `src/melodyvault` 布局，入口 `app.main` 只组合配置、日志、数据库和 Qt 界面，无网络请求。`python -m melodyvault` 与安装后的 `melodyvault` 命令使用同一入口。

| 模块 | 边界 | 当前实现 |
|---|---|---|
| `ui` | 只显示歌手和歌曲，不显示专辑；通过 Qt signal 接收任务进度 | 主列表/版本、审核撤销、SourcePage、独立任务进度 |
| `search` | 歌手与歌曲身份发现、候选、明确目标选择；不执行来源下载 | UnifiedSearchEngine / SongSearchService / SearchWorker |
| `catalog` | 歌手身份、作品与录音、证据归并；专辑只作后台元数据 | 快速目录/partial、独立evidence任务及原有保守归并/审核 |
| `providers` | 官方 API 优先，适配器隔离来源与允许的浏览器访问 | Archive / Commons / Jamendo |
| `sources` | 查询快照、匹配线索、搜索编排、浏览器元数据、真实进度 | SourceSearchEngine / SourceWorker / PublicBrowser |
| `licensing` | 保存授权依据，默认未核实；不能授权下载执行 | Phase2 source_evidence元数据检查，后续完整审批未实现 |
| `downloads` | 候选、资格、受控传输、校验、原始归档及域内队列 | Phase3B DownloadEligibilityService / DownloadManager，默认dry-run |
| `cloud` | 最小 OAuth、用户私人文件夹、可恢复上传和去重 | 包骨架 |
| `tasks` | 编排、取消、重试、重启恢复，调度来源和迁移后的状态 | 包骨架 |
| `database` | 连接生命周期、事务、版本迁移及领域仓储 | catalog / reviews / sources / evidence / search / downloads，v1–6保留、追加v7 |
| `config.py` | 非敏感 TOML、环境变量与 CLI 覆盖、显式运行目录 | 已实现 |
| `logging_setup.py` | 应用专属日志、旋转、常见敏感字段脱敏 | 已实现 |
| `tests/` | 配置、真实 SQLite 文件、日志、入口及真实 Qt 事件循环 | 已实现 |

后续依赖方向为 UI → tasks → catalog / providers / licensing / downloads / cloud；领域逻辑通过 repository 访问 database，不导入 UI，适配器不相互调用。provider 只提供候选和证据，不能自行下载；downloads 必须验证授权决策，不接受任意网页音频 URL。长任务通过工作线程或专用 async 执行器运行，不阻塞 Qt 主线程。Phase 0 仅启动时执行很小的本地初始化，不创建网络任务框架。

原Phase1的目录调用方向仍为 `MainWindow → CatalogWorker(QThread) → CatalogService → MusicBrainzClient / CatalogRepository`，Phase2改用search_catalog并新增独立任务。领域服务/模型不导入Qt；worker单独处理signal/thread。Phase2增加providers和licensing元数据检查，Phase3B增加独立downloads执行与域内持久队列；cloud仍保留占位。通用跨领域任务编排未实现。

## Phase 1 获取与去重

1. 对输入执行 Unicode NFKC、空白和 OpenCC 简繁规范化，按 artist/alias 搜索。唯一精确名称/别名匹配才自动进入 Artist lookup，否则要求选择。lookup MBID 必须一致，已确认身份随查询保存。
2. 分页浏览 `recording?artist=...&inc=artist-credits+isrcs`，按 MBID 收集音频录音。`video=true` 排除，原始响应仍保存在 API 缓存。
3. 分页浏览 release-groups；分别遍历正式 `release?artist=...` 和 `release?track_artist=...`，读取 media/tracks/recordings/credits。只收集曲目或录音署名包含目标歌手的曲目，不把合辑的其他歌手曲目加入目录。
4. 请求上限 100，但发行页受 500 曲目限制时可能只返回几十条，offset 必须增加实际返回数。提前空页、重复页、错误 offset 或不完整音轨列表视为失败。
5. Recording MBID 是录音层去重键，不再直接作为歌曲身份。任何旧录音及歌手关联都保留；只在完整处理成功后以事务替换派生 Song 映射，失败/取消保留成功页面与上次映射。

## Song / Recording 分层与原始数据保留

- `Recording` 保存原始 MBID、标题、署名和时长，独立附加官方 Work 关系与发行曲目上下文；同一 MBID 在多个发行中只出现一个录音版本，不删除原始记录。
- `Song` 使用目标歌手范围内稳定 UUID，包含 Work IDs、Recording 列表、待确认状态、证据和主版本。UUID 是本地派生 Song ID，不伪装成 MusicBrainz MBID。
- 相同单一 performance Work ID 可跨录音室、现场、Remix 等版本归入同一 Song。多 Work 串烧独立待确认；单 Work 的片段仍是该作品的版本，不作为录音室主版本。
- 无直接 Work 的记录需有额外强证据：匹配的 ISRC 或相同发行组/介质/曲目位置，并且标题或已知官方别名一致、歌手署名兼容。再版/套装可使用整张正式介质的完整有序曲目序列、歌手署名以及时长匹配（至少3曲，至少80%具有时长，已知时长逐曲差不超过2秒）；单个同名曲目不满足此规则。
- 先建立整个候选证据组件再决策：组件若指向不同 Work，未知记录独立待确认，不依赖遍历顺序，也不会桥接不同作品。无 Work 的上下文簇保留待确认状态；只有标题/别名的匹配只是提示，不自动并入已知作品。
- 主版本优先正式非现场 Album/Single/EP 上下文或明确 studio 标注；排除现场、Remix、串烧等。有直接 Work、ISRC 和较早正式发行者优先；没有足够证据则为空。非现场发行只能支持录音室推定，UI/证据不宣称音频内容已经核验。
- 默认树形 UI 每个已核实作品和独立待确认 Song 各一行、版本折叠。发行位置不成为额外歌曲行，未知作品明确显示待确认，不以标题去掉这些独立条目。

v3 迁移新增原始录音快照、API 响应历史、录音附加关系、Work、Song 及 Song-Recording 关联六张表。v1/v2 SQL/checksum 未修改。原始 `catalog_recordings.payload_json` 首次保存后不可变；新响应与关系保存为快照/附加证据。原 v2 内容完整回填快照，重建派生映射不会删除原始表。现有实例升级前已做 SQLite backup 和710条原始payload SHA-256基线，真实回归逐条核验。

## 待确认补证和人工审核

`CatalogService → enrichment → supplement_pending → identity → grouping → ReviewService`。补证只调用官方 API：完整 Recording 的 work/recording/release 关系，未知正式发行的完整曲目，Work 的反向 performance，以及待确认录音的有效 ISRC 查询。官方合并重定向限 HTTPS musicbrainz.org 的 Recording UUID 路径、最多3次；原ID保留，canonical ID另存证据。辅助视频/重复实体只保存为证据，不增加原始音频版本数。已完成的每录音补证及ISRC查询有7天完成点；404作为明确 not_found 保留并可强制刷新，失败/取消不冒充成功。

`identity.py` 仅接受精确反向 Recording ID、兼容演唱者的明确录音派生关系，或有效共同ISRC+一致署名+明确单一Work+标题/官方别名兼容。ISRC不是作品ID，已知现场/录音室等版本冲突阻止单靠ISRC推断。不同Work冲突保留全部证据并待确认。`review.py` 的标题相似/时长接近建议不回写自动证据；置信度为高/中/低/冲突类别，不是经统计校准的概率。

v4追加 auxiliary recordings、canonical redirects、补证完成点、按歌手派生的 identity evidence、review events，扩展Song的本地审核状态。v1–3 checksum保持不变，真实升级前保存1152条原始payload哈希和SQLite备份。原始Recording、关系响应历史和审计与可重建的Song映射分开。

`MainWindow → ReviewDialog → ReviewWorker(QThread) → ReviewService / ReviewRepository`。人工决定记录稳定的源/目标Recording ID集合、证据快照、理由、操作者、时间和事件ID，不能只依赖可能重建的Song ID。合并只修改Song分组，所有Recording版本仍恰好分配一次；不同明确Work、串烧和不属于目标歌手的记录禁止手动合并。保持独立属于本地用户确认，不创造MusicBrainz作品身份。

审核事件和派生分组同事务提交，使用每歌手最后事件作乐观并发检查；事件表触发器拒绝UPDATE/DELETE。撤销追加undo事件，重新播放剩余事件。刷新保留确认/拒绝/独立；若新证据冲突或撤销使后续合并目标拆分，后续事件标记stale并提示重审，不静默覆盖。此为本地审计完整性约束，并非防SQLite文件管理员篡改的签名系统。

统计分别保留Work核实作品数、本地人工确认、待确认项、有效人工审核项/录音数、版本和重复发行位置数；撤销/失效的决定仍在历史，但不计入有效人工审核。原生QA仅在隔离数据库副本写入qa_automation事件，不污染正式用户审核数量。

client 固定官方 HTTPS API，使用含项目联系 URL 的 User-Agent；进程内请求起始间隔至少 1.1 秒。429/5xx 和网络错误最多尝试 5 次，遵循 Retry-After 或指数退避。20 秒 HTTP 超时，Event 可取消等待/退避，并在当前请求结束后退出。成功页面 SQLite 缓存 7 天；重试或重启重新搜索会重建已缓存部分并继续缺失页面，用户可显式忽略缓存刷新。

UI 只启动线程和处理排队信号；线程自行建立/关闭 SQLite 连接。QThread.finished 恢复按钮；关闭窗口时先取消，线程结束后才关闭，避免销毁运行中的 QThread。进度为当前步骤真实条数，不推算虚假的全局进度。

范围限制：社区数据可能缺失、重复建档或署名不一致；区分录音版本数与规范化标题数。只有录音目录、没有正式发行关联的条目保留未核验状态。作曲/制作关系不等同于演唱署名，元数据不是音频下载授权。

## 数据库和升级约定

SQLite 位于独立可配置的数据根目录。每次操作使用独立连接，上下文退出必定关闭，启用外键、WAL、10 秒 busy timeout。`connect` 默认 autocommit；业务多语句写入必须自行使用显式事务，不能把连接上下文当作事务。

迁移定义位于 `database/migrations.py`，只能追加版本；版本必须从 1 连续递增。初始化在 `BEGIN IMMEDIATE` 内核验 `PRAGMA user_version` 和 `schema_migrations` 的版本、名称、SHA-256，逐条执行 SQL 并提交。任何异常回滚当前整次迁移；下次可重试。拒绝较新数据库，拒绝历史缺失、篡改或不一致。历史时间使用 UTC。

初始 v1 仅建立 `schema_migrations` 和 `app_metadata`，不提前固化后续目录、授权、下载和上传业务表。未来迁移应先备份、测试现有数据升级并保留回滚策略；本阶段没有自动备份或业务数据恢复工具。禁止在迁移中使用会隐式提交的 `executescript`。

v2 追加 10 个 catalog 表：歌手、查询身份、录音、歌手—录音关联、发行组、歌手—发行组关联、发行版本、曲目、运行状态和 API 页面缓存。v1 SQL/checksum 未修改，真实 v1 文件升级测试验证数据和历史保留。按页显式事务提交，failed/cancelled/needs_selection 不会成为 completed。

## 后续数据流与强制约束（尚未实现）

歌手消歧 → recording 目录 → 多来源候选 → 授权证据审查 → 完整音频下载与校验 → 私人 Drive 上传。每步都需要 SQLite 状态和幂等键，恢复时不能重复搜索、下载和上传。计划状态包括 pending / running / succeeded / not_found / blocked / failed / cancelled；任务状态须与文件完整性分别核验，上传成功须有 Drive 确认。

授权证据需要来源、权利人/许可证、适用曲目、下载和私人保存许可、完整性依据、核验时间及条款版本；网页可播放或下载按钮不足以通过。浏览器来源须记录允许自动访问的依据；验证码或访问限制立即停止。服务端超时/限流按来源策略退避，取消须关闭连接并保存恢复点。上述细节在对应阶段实现和实测，Phase 0 不提供假的成功路径。

Google Drive 仅用 drive.file，文件夹必须是应用创建或用户通过受支持流程授予应用访问的私人文件夹。不得因为 folder ID 可填写就假设有访问权；不得扩大权限来遍历全盘。绝不创建 anyone/domain 共享权限。token 和密钥存于独立忽略目录，后续在 Windows 上选用合适的凭据保护，不把明文持久化骨架当作安全存储完成。

## 交付边界

本阶段交付源码和可运行开发环境，已实现真实目录/来源元数据网络任务及独立Chrome。PyInstaller独立exe、干净系统和Win10/Win11矩阵、OAuth、音频传输与上传恢复仍属于后续阶段；用户本轮明确Phase5再扩展传输/恢复，当前不提前实施。每阶段需真实测试，等待用户确认再推进。

参考官方资料：[Qt for Python](https://doc.qt.io/qtforpython-6/gettingstarted.html)、[pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)、[Drive OAuth scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)。
