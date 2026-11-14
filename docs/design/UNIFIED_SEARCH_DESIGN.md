# Phase 3A：统一搜索设计

范围为歌手身份、歌曲/录音候选和现有多来源查询的连接。没有歌词、播放器、歌单、在线播放、下载或上传实现。

## 调用方向

```text
MainWindow / UnifiedResults
  → SearchWorker(QThread) → UnifiedSearchEngine
      → ArtistSearchService / SongSearchService
      → SearchRepository → SQLite 派生索引及查询缓存
      → MusicBrainzClient → 官方 /ws/2/artist、recording
  → 用户选择歌手 → 原 CatalogWorker / CatalogService.search_catalog
  → 用户选择歌曲版本 → SongSelectionService → 单录音 CatalogResult
      → 原 SourcePage / SourceWorker / SourceSearchEngine
```

领域服务不导入 Qt；worker 只负责线程、取消和信号。MainWindow 保留原目录、版本展开、审核撤销、低优先级补证及整位歌手音源搜索。

## 查询与身份

`SearchRequest` 保存 smart/artist/song、原查询、可选歌手文字、已约束 Artist MBID 集合、本地模式和强制联网。`SearchResult` 分开返回歌手身份与歌曲录音候选，不通过关键词长短决定类型。界面不默认选中歌曲，必须选择具体版本。

`SongCandidate.id = Artist MBID + Recording MBID`。另存当前 Song ID、Work IDs、演唱署名、版本、时长、原始候选字段、命中依据和待确认标记。同标题不同歌手/Work/录音保留为不同候选；同一 Recording 的重复 API 命中只保留一次。候选不是新作品分组，也不是可下载授权。

- 歌手模式复用 Phase 1 的身份核对、同名选择窗口及逐页目录。保存过的明确身份直接读取 SQLite。
- 歌曲模式先读 SQLite。裸歌名即使本地只有一位歌手，也先显示本地候选并补查官方 Recording 搜索，不据此认定原唱；勾选“仅本地搜索”时完全不访问网络。
- 智能模式同时保留歌手和歌曲两类候选；若已有用户确认的歌手绑定、唯一精确身份且没有歌曲歧义，可直接进入保存目录。
- 已知的完整歌手名称/别名可拆出剩余歌名，例如“周杰伦 晴天”。英文别名前缀须满足词边界。歌手修正框可显式约束身份。
- 未知的多词输入先查询完整歌名，存在精确完整标题时不把它拆成某位歌手；否则最多尝试三个分词边界，只有官方精确歌手名称/别名才能成为歌手条件。存在多个同名歌手时保留全部身份，最终歌曲仍需选择。
- API 分数、相似名称和时长不是作品或演唱者确认。在线搜索命中缺少本地可靠 Work/录音关系时保持待确认。在线候选确认时再 lookup Recording 及 Work/演唱署名，不能只按歌名写入目录。

名称匹配使用 OpenCC 简繁转换、Unicode 规范化、大小写、空格和标点处理。明确的括号版本词可用于基础歌名检索，但 Recording ID、原版本和来源指纹仍保留，不把现场版升级为录音室版。

`pypinyin` 只生成普通话无声调检索键。`Qing Tian` 可找到本地“晴天”的候选，但不是官方英文别名，可能存在同音不同作品；此类结果明确待确认，不自动选中、归并或写回官方标题。官方别名与用户选择历史分别标注。用户选择的查询别名仅用于后续检索，不能提升 Work 归并证据。

## 确认操作与旧模型

对已存在的 Recording，读取其**当前** Song 归属，追加目标选择审计，不重建分组、不调用审核重放、不更新原始 Recording 或旧 Song。返回单 Recording 的临时 CatalogResult；即使属于拥有多版本的 Song，来源查询仍只针对所选版本。选择现场版不会使其成为正式录音室主版本。

对新 Recording，核对官方 Recording MBID/允许的 canonical 重定向、目标歌手署名和版本；保留完整官方响应快照。已有原始数据/丰富 Work 内容以 INSERT OR IGNORE 保护。明确 Work 可接入同歌手的未人工审核自动分组；若目标组已人工审核，另建独立待确认项，不把新录音写入已审核组。不凭同标题合并。搜索确认审计与原有 merge/reject/independent/undo 历史相互独立。

取消发生在最终确认提交附近时，已提交的公开元数据或用户目标选择不会被删除；取消信号阻止后续自动启动音源任务。取消不是撤销已有人工审核。

## 缓存及数据库兼容

只追加 schema v6，v1–5 SQL/checksum 不变：

| 数据 | 用途 |
|---|---|
| `unified_artist_index` / `unified_recording_index` / `unified_title_keys` | 可重建的歌手、录音、官方名称及弱拼音检索索引 |
| `unified_index_meta` / `app_metadata.unified_revision` | 事务快照版本；目录/Work/人工分组变化后失效 |
| `unified_search_cache` | 带模式、歌手约束和来源范围的查询结果，成功 7 天、真实空结果 6 小时 |
| `unified_confirmations` | 只追加的目标选择审计，禁止 UPDATE/DELETE |
| `unified_user_aliases` | 用户选择过的查询名与精确歌手/Recording 关联，不作为官方别名 |

`unified-v3` 查询指纹保留输入词边界、版本文字、模式、歌手条件和已解析 MBID，避免 `AB C` 与 `A BC` 分词不同却串用缓存。有效查询结果保留解析后的歌手身份；未知前缀首次解析后同时保存原条件查找入口。目录 revision 变化即拒绝旧查询结果，索引在后台原子重建；并发补证改变 revision 时重试快照，仍不稳定则明确提示重试。错误不写成“无结果”负缓存。

原 MusicBrainz 页面和补证缓存继续使用；应用内全部 MusicBrainz 客户端共享 1.1 秒请求间隔，429/503/超时使用既有有界指数退避及 Retry-After。强制联网同时跳过统一结果和 HTTP 页面缓存。单进程限速不协调用户另行启动的其他应用实例。

来源结果沿用 Phase 2 指纹。所选 Recording 集合、版本或用户搜索别名变化时不会误用其他版本的来源缓存；重复同一单录音查询可复用。旧整首多版本指纹与新单版本指纹不同，首次选择可能需要重新搜索来源，这是保留版本身份的必要边界。

## UI 线程与任务生命周期

每次查询、模式切换和清空递增 generation，并请求取消旧任务。每个 worker 的 `RequestRelay(QObject)` 位于 UI 线程，通过排队 signal 更新控件，generation 不一致或关闭中的回调被丢弃。旧 QThread 保留引用直到 finished，不能提前销毁；旧 finished 不能恢复新任务的控件或清空新 worker。确认目标后若旧来源任务仍在运行，排队等待其结束；新查询会使旧的待启动目标失效。

取消是协作式的：退避/限速等待可中断，进行中的 HTTP 等待响应或 20 秒读取超时。保留已保存数据和本地候选，清空只影响当前展示。总量未知时显示不确定进度；API 次数、耗时及重试来自实际客户端计数。

## 边界与限制

官方 Recording 搜索每次最多 50 条，歌手发现最多 25 个身份；本地额外候选可以使展示数量超过 50。达到上限需要细化歌手/标题，不宣称穷尽全网歌曲。歌手完整目录仍由原分页目录任务获取。

真实验证数据及计时见 [PHASE3A_VALIDATION.md](../validation/PHASE3A_VALIDATION.md)。拼音、相关 API 命中、缺少 Work 和未知版本均不能被解释为已核实歌曲或合法音频。

官方依据：[MusicBrainz API 搜索](https://musicbrainz.org/doc/MusicBrainz_API/Search)、[API](https://musicbrainz.org/doc/MusicBrainz_API)、[速率限制](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)、[pypinyin 用法](https://pypinyin.readthedocs.io/zh-cn/master/usage.html)。
