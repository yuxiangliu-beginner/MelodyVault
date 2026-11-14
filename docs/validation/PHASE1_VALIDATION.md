# MelodyVault Phase 1 验证记录

## 当前轮次：补证、人工审核和可撤销审计

日期：2026-11-13（America/Los_Angeles）。**Phase 1 仍等待用户验收，未标记完成；没有进入 Phase 2。** 以下为本轮当前结果，后文旧报告只保留作历史对照。

### 实际覆盖率结果

**新增证据没有实际降低这两位歌手的待确认数量，提高自动归并覆盖率的目标尚未达成。** 已完成补证和审核机制，没有用相同歌名、相近时长或自动生成的人工决定来降低待确认数。

| 指标 | 林俊杰：补证前 → 后 | 周杰伦：补证前 → 后 |
|---|---:|---:|
| 原始音频 Recording | 443 → 443 | 710 → 710 |
| Work 已核实作品 | 48 → 48 | 192 → 192 |
| 待确认 Song 项目 | 355 → 355 | 380 → 380 |
| 待确认涉及的 Recording | 377 → 377 | 393 → 393 |
| 主列表 Song 行数 | 403 → 403 | 572 → 572 |
| 全部录音版本数 | 443 → 443 | 710 → 710 |
| 同一条目内额外版本 | 40 → 40 | 138 → 138 |
| 重复发行收录位置 | 878 → 879 | 1665 → 1668 |
| 当前有效人工审核项 | 0 | 0 |
| 相同有效ISRC的疑似重复建档对 | 0 | 2 |

两位歌手共1152条全库不同Recording（存在1条共享录音），原始payload逐条SHA-256全部一致。各歌手所有Recording仍恰好分配一次，不能把表中版本数相加当作全库不同Recording数。

原因核查：林俊杰待确认录音中376条无明确Work，1条含多Work/冲突；周杰伦387条无明确Work、6条含多Work/冲突。新增关联没有为这些未知实体提供可用的单一作品身份。周杰伦“不爱我就拉倒”录音 `7c9de99c-b6ef-4044-97b3-49437aad2de5` 新增了来自 `0457a49a-5ad6-4d0a-bd15-f89038a0a47f`、ISRC `TWK971801201` 的同署名/相同名称/明确Work证据，Work为 `7a0ccd26-68e3-4b8d-9b55-71877a40246a`；该录音原先已通过发行上下文归入相应Song，因此证据增强但待确认数不下降。

补查发现林俊杰1个、周杰伦3个额外正式发行上下文，增加了上述重复发行位置统计；这些位置不增加歌曲行或录音版本，也不代表新增作品。ISRC相同仅表示可疑重复实体，仍保留全部不同Recording ID；没有把“2对候选”宣布为已核实重复建档。实际未发现官方Recording合并重定向（两位均0）；重定向分支由离线HTTP契约测试验证。

### 实现和证据门槛

- 保留Song/Recording，追加v4迁移，v1–3 SQL与checksum不变。原始录音不删除、不改写；补充关系/响应另存，辅助视频等实体仅作证据。
- 待确认Recording定向读取Work、ISRC、recording关系及发行；补查Work反向performance、未知正式发行完整曲目、有效ISRC关联实体。每项完成点和API页持久化，失败可重试、成功可恢复，显式刷新忽略完成点；取消在当前请求结束后退出。
- 明确反向Recording ID和兼容署名的作品关联可确认身份。ISRC辅助需要合法格式、一致演唱者、标题/官方别名兼容及明确单一Work，已知版本冲突时拒绝该推断；不同Work冲突不隐藏。简繁、标点、空格、英文别名、相似标题和时长均不能单独触发自动归并。规则为 `song-evidence-v2`。
- 同一作品的现场、录音室、Remix和重新录制保留各自Recording和版本标注；版本冲突不借ISRC桥接。没有足够正式录音室证据不指定主版本。
- 默认列表每个已核实作品及独立待确认Song各一行，状态明确，所有版本可展开。重复发行位置只后台保存，界面不展示专辑。
- 新增“待确认作品审核”：显示建议对象、类别置信度、来源理由、Work、演唱者/MBID、版本/ISRC/时长及发行曲目位置；高/中/低并非统计概率。弱候选只有用户填写理由并主动确认才成为本地人工决定，不伪造MusicBrainz Work。
- 支持确认合并、拒绝此建议、保持独立、撤销。保存稳定的源/目标Recording集合、证据快照、理由、操作者和UTC时间；事件与派生映射原子提交，乐观检查防覆盖其他审核历史，触发器拒绝更新/删除事件。
- 刷新重放有效人工决定。撤销追加undo事件，原决定保留；后续依赖目标已拆分或新Work证据冲突时标记需重审，不能暗中重新合并。版本始终保留，跨歌手无关联、不同明确Work、串烧禁止手动归入单一作品。

官方依据：[API与ISRC lookup](https://musicbrainz.org/doc/MusicBrainz_API)、[Work语义](https://musicbrainz.org/doc/How_to_Use_Works)、[限速规则](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)。MusicBrainz元数据和Work关联均不代表音频保存授权。

### 真实在线与Windows测试

| 实际在线运行 | 林俊杰 | 周杰伦 |
|---|---:|---:|
| 首轮关系/发行/录音补证网络请求（含重试） | 496 | 592 |
| 该轮503重试次数 | 91 | 128 |
| 待确认录音定向完成 | 377 | 392新取+1复用 |
| 最终两歌手回归新增网络请求（含重试） | 60 | 101 |
| 该轮503重试次数 | 12 | 21 |
| 该轮真实API缓存页命中 | 20 | 63 |
| 有效ISRC关联查询 | 49 | 80 |
| 回归复用录音补证完成点 | 377 | 393 |

这些是实际官方GET请求；没有Mock替代在线路径。503实际错误通过进度报告并依限速/Retry-After有限重试恢复，两位最终均成功，404/not_found为0。首次补证分别967.287秒、1096.259秒；最终回归分别132.891秒、310.155秒，缓存可恢复但首次补证并非即时完成。

原生审核GUI测试：**通过，Qt平台为windows**。在真实生产数据库的SQLite备份副本中，两位歌手分别选择真实低置信度建议，点击合并→撤销→拒绝→保持独立→撤销独立→撤销拒绝。每位保留6个 `qa_automation` 审计事件，全部决定效果撤销，原始录音与版本仍完整。正式数据库审核事件为0；不把QA测试动作计入用户确认或覆盖率。

最终全量pytest：**73 passed in 469.16s，0 failed / 0 errors / 0 skipped**。包括两位歌手真实目录服务、原始哈希保留、同名不同Work/歌手、简繁/英文别名、合作/现场/重新录制、ISRC冲突、辅助Work补证、失败重试/取消恢复、只追加审计、撤销依赖/新Work冲突需重审，以及实际Qt控件/线程测试。JUnit为 `pytest-final.xml`。两项live测试复用真实官方缓存，新增网络请求0，分别命中63/19页、复用393/377录音和80/49 ISRC完成点；在线访问已由上表另行验证。

原生主窗口：**两位均通过**，中文输入、点击搜索、工作期间禁用/完成恢复、默认折叠/展开和SQLite一致性均核对，Qt平台windows。

| 原生主窗口实际测量 | 林俊杰 | 周杰伦 |
|---|---:|---:|
| 顶层Song行 / 全部录音版本 | 403 / 443 | 572 / 710 |
| 已核实作品 / 待确认 | 48 / 355 | 192 / 380 |
| 耗时（秒） | 153.857 | 196.085 |
| 工作期间UI心跳 | 4888 | 6196 |
| 最大UI心跳间隔（秒） | 0.083 | 0.286 |
| API请求 / 真实缓存页 | 0 / 19 | 0 / 63 |

原生测试使用生产真实目录的隔离副本，未添加人工作品判断。复用页面仍会遍历证据并重建分组，不能把缓存理解为即时显示；当前缓存搜索仍需约2–3分钟，这是已记录的性能限制。两位主窗口原生截图及建议、审计截图均已实际查看。

另以真实数据副本验证主窗口按钮→审核模态窗口→加载355个待确认源条目→正常关闭→主窗口结果更新，`native-review-entry.json` 为通过；此流程没有新增审核事件。已查看原生建议和审计截图，中文、置信度、弱证据说明和版本信息显示正常。`pip check` 通过；下载/上传/授权/来源模块原文件hash均一致。

### 证据文件和复现

本地 `.local/reports/phase1-review/`（全部被Git忽略）：

- `before-review.sqlite3`、`baseline-raw-hashes.json`、`baseline.json`：升级前快照和1152条原始基线。
- `<artist-mbid>-enrichment.json`：首次补证请求数和结果；`<artist-mbid>-regression.json`、`regression-summary.json`：最终前后对比、未归并原因、原始保留和迁移检查。
- `native-isolated/review-gui.json`、`isolated-review.sqlite3`和两位歌手的截图：仅隔离副本中人工操作和撤销证据。
- `pytest-final.xml`、`<artist-mbid>-pytest-live.json`：73项全量测试及两歌手真实缓存回归。
- `native-jj.json/.png`、`native-jay.json/.png`、`native-review-entry.json/.png`：真实目录副本上的主窗口及审核入口原生验证；`native-main-runtime/` 是隔离的完整目录副本。
- `scope-verification.json`：providers、licensing、downloads、cloud原文件SHA-256未变。

```powershell
Set-Location E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
# 输入歌手 → 搜索 → 待确认作品审核 → 填理由并选择动作 → 审计历史与撤销
$env:MELODYVAULT_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-review-new --junitxml=.local\reports\phase1-review\pytest-new.xml
.\.venv\Scripts\python.exe scripts\validate_phase1_review.py
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --artist '林俊杰' --data-dir .local\runtime --report .local\reports\jj-ui-new.json --allow-cached
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --artist '周杰伦' --data-dir .local\runtime --report .local\reports\jay-ui-new.json --allow-cached
# 输出目录必须未使用，避免覆盖隔离测试审计
.\.venv\Scripts\python.exe scripts\verify_review_gui.py --database .local\runtime\database\melodyvault.sqlite3 --output .local\reports\review-new
```

### 未解决问题和验收边界

待确认数量没有下降是实际未解决项，不能据本轮机制实现宣布覆盖率提升。下一步需要用户逐项审核明确证据，或MusicBrainz新增可靠关系后刷新；不代替用户提交人工决定，不写入MusicBrainz服务器。官方lookup返回的发行关联并不保证一次包含全部历史发行，保留现有分页获取范围，不宣称完整作品库。部分版本元数据仍缺失；无证据维持“版本未核实”。

此次Windows验证为当前Windows 10 / Python 3.13.2环境；Windows 11、其他Python版本和独立exe仍未验收。外部桌面操控未作为本轮测试路径，原生测试只向自己拥有的Qt控件发事件。停止在Phase 1，等待用户验收，不进入Phase 2。

---

## 历史：Song/Recording两层模型首轮验证

日期：2026-11-13（America/Los_Angeles）。状态：**本轮实现和自动验证通过，Phase 1 仍等待用户验收，未标记完成；不进入 Phase 2。**

数据来源为当前真实周杰伦目录，Artist MBID `a223958d-5c56-4b2c-a30a-87e357bc121b`。没有用模拟歌曲替换真实目录；离线测试样例只在 tests 中使用。

## 修复前后

| 指标 | 修复前 | 本轮实际结果 |
|---|---|---|
| 原始音频录音记录 | 710 | **710，所有原始 payload 的 SHA-256 一致** |
| 默认主列表 | 710 条录音平铺，存在同名重复行 | **192 首已核实作品，每首一行，版本折叠**；另有1个“待确认”根节点 |
| 独立歌曲身份 | 没有 Song 层；368 只是规范化标题数 | **192 首有单一 Work 身份的作品**，不能解释为歌手全部歌曲数 |
| 派生歌曲/候选条目总数 | 无 | 572：192 个已核实 Song + 380 个待确认条目 |
| 原始录音版本 | 710 | **710**，全部在相应 Song 或待确认条目下，可展开核对 |
| 已归并的附加版本 | 无 | 138，即 710−572；保留全部 Recording MBID |
| 重复发行收录 | 未独立统计；旧2182包含录音浏览重复出现 | **1665**，口径见下文 |
| 待确认 | 未区分 | **380 项，涉及393条录音**；不计入已核实独立歌曲数 |
| 直接有 Work 关系的录音 | 旧存储未请求 Work 关系 | 299 条 |
| 主版本 | 无可靠优先级 | 250 个条目有正式非现场/录音室依据的候选主版本，其中161个属于已核实 Song |

**368 个同名规范化标题不等于368首作品。** 本轮没有为了达到某个歌曲数量而把所有同名条目强行合并，也没有把未知记录假称为已经核实的独立作品。

统计定义：原始录音数为目标歌手已保存的不同 Recording MBID；版本数为分层后仍保留的不同 Recording 数。重复发行收录数统计当前已保存发行中同一 Recording MBID 的额外曲目位置：2277 个收录位置 − 612 个有发行关联的不同录音 = 1665。旧的2182是“录音浏览出现次数+相关曲目出现次数−录音数”，两者口径不同，不能把差值解释为录音被删除。

## 真实例子

### 龙战骑士

Work：`039d2a3e-4ca6-35ed-b11d-f1609617fc42`。以下2条 Recording 属于同一个 Song，并可展开分别查看：

- `bec2d851-614a-4216-baee-9c977ef8f379`：正式非现场发行，选为主版本；主版本依据可在 tooltip 查看。
- `797f2daa-10cf-4018-81ab-15ed7955ac7b`：现场版本，保留但不作为录音室主版本。

### 龙拳

Work：`9d860de6-1dd2-3f2f-8c8e-a335aff393e4`。7条现有原始录音中，**4条有足够证据归入该 Song，另3条仍独立待确认**。默认已核实作品区只有一行“龙拳”，未确认条目在单独分区，不伪装成已核实版本。

- `05c22cea-605f-42c5-a176-d358dc9c49e8`：直接 Work 关系、正式非现场发行和 ISRC；选为主版本。
- `1fde9808-7307-4911-9f47-86b94ad7eaa8`：同一 Work 的现场版。
- `8f72028c-ede1-49db-8638-ecb34b09840c`：简体标题的发行录音，发行组/介质/曲目位置及歌手证据支持归入。
- 另1条通过完整正式再版曲目序列及逐曲时长证据归入；其 Recording ID、对应发行和完整理由见本地 `validation-data.json` 的 examples。
- 剩余3条缺少可靠 Work/收录关联，不因“龙拳”同名就自动归入已知 Work。原始数据和候选提示保留供后续核对。

## 归并规则和限制

1. Song 和 Recording 分层。相同单一 performance Work ID 是优先作品身份；录音身份始终保留为 Recording MBID。
2. 缺少直接 Work 时，额外证据可以是相同 ISRC，或相同发行组/介质/曲目位置；要求标题/已知官方别名兼容及目标歌手署名关联。
3. 再版/套装跨发行组时，仅对完整正式介质使用整套有序曲目、兼容歌手署名和时长证据：至少3曲、至少80%具有时长、所有已知时长逐曲差不超过2秒。单个同名曲目不满足此规则。
4. 组件若涉及不同 Work ID，不能通过无 Work 的中间记录桥接。多作品串烧独立待确认；单一 Work 的片段可作为版本，但不选为录音室主版本。
5. 简繁、空格、标点、英文大小写和官方 Work 别名只规范化匹配/提供候选。相同歌名或别名本身绝不产生归并边。
6. 同一作品的合作、现场、Remix 等录音保留为版本。不同歌手没有目标署名关联时，即便标题或 Work 一致，也不混入目标歌手的已核实条目。
7. 主版本要求正式非现场发行上下文或明确 studio 标注；不能因未写“live”就推定为录音室版。非现场发行仍是元数据层面的推定，不是对音频内容的核验。

规则版本：`song-evidence-v1`。完整证据保存到 SQLite 的派生 Song 映射；原始 Recording payload 不改写，新增数据作为快照及附加证据保存。只替换派生分组，不删除录音。

官方定义依据：[Recording](https://musicbrainz.org/doc/Recording)、[Work](https://musicbrainz.org/doc/Work)、[performance 关系](https://musicbrainz.org/relationships/recording-work)。MusicBrainz 不保证资料完整、署名无误或全部版本已关联同一 Work。

## 实际测试结果

- 第一轮：43 passed、3 failed、1 deselected。两项旧测试没有区分新增的 Work 关系分页；另一项触发旧10秒测试等待上限。修正分页断言、恢复断言与30秒测试等待后复测。
- 完整复测：**50 passed in 126.31s，0 failed / 0 errors / 0 skipped**。包含同名不同作品、重复发行、现场/Remix、简繁/标点/英文别名、合作歌手、禁止未知桥接、多Work串烧、主版本、v2→v3原始数据保留，以及真实周杰伦回归。
- 对710条旧录音逐条核验 payload SHA-256：全部不变；旧v1/v2迁移 checksum 不变。所有710个录音恰好归入一个目标歌手的派生条目，未丢失、未多重分配。SQLite integrity_check / foreign_key_check 均通过。
- 官方 Work 证据首次补取：79 次请求、15 次503重试、缓存0；成功获取10页录音关系、30个发行专属录音 lookup、3页歌手关联 Work，以及21个额外 Work lookup。
- **再次在线获取成功**：显式忽略页面缓存，75次真实请求、12次503重试、缓存0，完成官方录音/发行及Work主要页面处理；结果仍为710条原始录音。该次报告为 `online-refresh.json`。额外关联 Work 在持久存储中仍保留，当前刷新逻辑也会重新查询浏览结果之外的 Work。
- Windows 原生 Qt 端到端通过：输入“周杰伦”、点击搜索、后台处理、默认折叠、展开“龙拳”的录音版本、待确认分区、统计、SQLite和按钮恢复均核对。在线已单独验证，此次 UI 回归复用63页真实官方缓存，新增请求0；耗时32.268秒，工作期间UI心跳968次，最大间隔约0.120秒。
- 最后启动并保留窗口的复核也功能通过（`native-gui-final.json`），耗时54.948秒，最大心跳间隔1.406秒。检查发现测试心跳回调自身有同步stdout/文件写入，已移除此测量干扰；随后使用相同真实数据复测通过（`native-no-ui-io.json`），耗时29.254秒，868次心跳，最大间隔0.115秒。产品界面没有引入这些测试日志输出，未把慢测量隐去或解释为网络失败。
- `pip check`：No broken requirements found。providers、licensing、downloads、cloud 与原校验清单一致，未开发 Chrome 搜索、音频下载或 Google Drive 上传。

## 本地证据与复现

以下均在 `.local/reports/phase1-song-model/`，被 Git 忽略：

- `before-song-model.sqlite3`、`baseline-recording-hashes.json`：修复前备份和710条基线。
- `validation-data.json`：实际统计、逐条保留核验、规则例子和全部待确认条目的理由。
- `online-refresh.json`：真实在线获取数量与记录。
- `pytest-final.xml`、`live-pytest.json`：完整测试和真实数据回归结果。
- `native-gui.json` / `.png`：Windows Qt 流程及截图；`native-gui-final.json` / `.png` 为最后启动程序的复核结果。
- `native-no-ui-io.json` / `.png`：移除测试监视器主线程同步日志后的原生复测；保留窗口仍运行在相同产品 MainWindow 上。

```powershell
Set-Location E:\users\yliu\MelodyVault
$env:MELODYVAULT_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-new --junitxml=.local\reports\pytest-new.xml
.\.venv\Scripts\python.exe -m melodyvault.catalog --artist '周杰伦' --data-dir .local\runtime --refresh --report .local\reports\new-online.json
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --data-dir .local\runtime --report .local\reports\new-ui.json --allow-cached
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
```

## 仍存在的问题与验收状态

380项待确认（393条录音）尚缺可靠作品身份。需要补齐 MusicBrainz 关系或进行有证据的人工核对，当前不会按标题自动确认；本轮没有提供人工批量强制归并入口。部分版本信息缺失时明确显示“版本未核实”，无正式录音室证据则不指定主版本。

本轮解决了平铺录音和强制标题去重之间的模型问题，但不宣称已完整核实歌手全部歌曲。**Phase 1 保留“修复已实现、等待用户验收”状态，不标记为已完成，不进入 Phase 2。**
