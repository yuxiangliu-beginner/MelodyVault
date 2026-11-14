# Phase 3B.1 来源发现设计

## 边界

`DiscoveryPage → DiscoveryWorker → SourceDiscoveryService → DiscoveryHTTP → DiscoveryRepository`。
`SourceSearchEngine → SourceProvider → Candidate → DownloadEligibilityService → DownloadManager` 是另一条链。
网站、歌曲、录音、文件和文件格式分别计数。网站审核从不批准整个网站的下载行为。
所有远端内容作为数据处理，不执行脚本、远程插件或网页中的开发指令。保留原 Song/Recording/Work 和人工审计模型。

公开发现默认使用中文 Wikipedia 官方搜索 API 的百科页面外链，不局限于预置域名。没有密钥时，这只是有限的公开目录发现，不能声称已经实现全网搜索引擎覆盖。
可选 `BRAVE_SEARCH_API_KEY` 连接官方搜索 API，不抓取受限搜索结果页。密钥只读取环境变量，不进入 SQLite 查询或日志。
查询计划包含歌手、歌名、简繁体、已有英文别名、拼音、格式及免费/完整/官方/CC 意图。百科只执行前两个身份查询，避免用下载意图污染百科检索；配置通用搜索 API 后执行完整计划。
拼音、标题、相近时长、专辑背景都只是检索或显示依据，不构成录音身份或权利证明。

## SQLite v8

v1–7 迁移及 checksum 不变。v8 新增 `discovered_sources`、`source_capabilities`、`source_discovery_history`、`source_verification_history`、`source_discovery_cache`。
新域名默认为 `PENDING_REVIEW`；域名 IDNA、小写、去尾点、www 归一，不错误合并其他子域名。
历史保存原始公开 URL、查询、渠道、时间、检查依据和操作。显示最近 100 条历史；数据库保存全部历史。

能力字段使用三态：`null` 未核实、`false` 已检查不支持、`true` 有证据。出现 MP3 字样不是完整音频证据；robots 许可不是文件使用许可。
网站状态包括 DISCOVERED、ACCESSIBLE、SEARCH_SUPPORTED、METADATA_ONLY、FULL_AUDIO_CANDIDATE、DOWNLOAD_PERMISSION_VERIFIED、LICENSE_UNVERIFIED、RESTRICTED、UNSAFE、UNAVAILABLE。
网站当前状态和文件授权状态分别保存；本版普通新网站不会因为 HTML 线索进入 DOWNLOAD_PERMISSION_VERIFIED。

查询正/负缓存 6 小时，普通站点检查 24 小时复用；显式重新检查绕过检查缓存。已批准 API 适配器核验有效期 7 天，过期暂停使用，等待重新检查。
连续三次请求失败自动停用；手动禁用优先于检查成功；手动启用不会将 PENDING_REVIEW 提升为 APPROVED，也不能绕过 UNSAFE/过期状态。
缓存命中不计为新的 API 请求或成功请求。`attempts/hits` 是真实请求尝试和返回候选的请求次数，不是授权成功率。

## 网络与来源适配器

调查请求仅 HTTPS 公共网络；复用下载层 `PublicBackend` 在 TCP 建连前检查所有 DNS 地址，再连接字面 IP，保留原 Host/TLS SNI。
不使用环境代理，不跟随重定向，不访问媒体/可执行响应，限制响应解压后的体积，连接/读取超时，有界 429/503/502/504 指数退避及取消。
普通网站先读取 robots；禁止或无法确认时不抓取歌曲页。API 例外必须有编译到程序的明确官方政策，不能从未知网页自动生成例外。
预置 API 检查通过后才将其编译适配器写入注册表批准。旧三个适配器在没有注册行时保留兼容行为；一旦注册，就服从启停、健康和过期规则。新增 ccMixter 在没有有效批准行时不运行。

`SourceProvider` 明确搜索、按文件 ID 取新元数据的接口；四个实现均提供 `search/get_metadata`，候选包含格式、大小、时长、许可 URL、页面、直接文件 URL、失败/匹配原因和来源证据。
来源失败隔离；原录音版本、ISRC、Work 关系和手动确认逻辑保留。Archive 上传者声明仍不能自动批准下载；Jamendo 未配置就跳过，不发请求。

ccMixter 的 robots 排除 API 爬虫索引，但它发布了专门的第三方 Query API 使用许可；仅 `/api/query` 使用此明确接口权限，不扩展到禁止抓取的网页。
每个上传下的不同文件使用 `upload_id:file_id`，原生录音身份使用 `ccmixter:upload_id`；不会伪造 MusicBrainz UUID。
Base32 SHA-1 转为十六进制后与真实文件比对。文件只能来自编译允许的 `/content/account/original.ext` HTTPS 路径。
翻唱、传统作品、采样、stem、loop、spoken-word 等未解决作品权利/完整歌曲范围时保持 LICENSE_UNVERIFIED，不因 CC 标签降低标准。

## 下载及 GUI

原下载引擎逐文件刷新官方元数据，严格确认身份、版本、完整性、许可、私人保存范围后才下载。新网站手动启用和元数据匹配分数都不能越过资格审核。
保持来源原始 MP3/FLAC/WAV/M4A/AAC/Ogg/Opus 字节，不转码。AAC 解析和 Ogg 容器中的 Opus 检查已补充；原有续传、SHA-256、旁证、同卷发布和去重保留。
同一录音不同格式使用不同文件身份/指纹，允许分别排队；同一来源文件重复下载沿用 SHA 和官方身份复用。尚未实现跨来源的预下载内容去重或云端按格式去重。

五个页面保留原四页并增加音源发现。调查/检查运行于 QThread，Qt 信号更新界面；任务未完成时禁用冲突操作，支持取消，关闭窗口等待 worker。
无明确许可的来源候选不提供可执行下载按钮；它们的链接、调查信息和拒绝原因仍可查看。页面状态和进度来自实际任务；不确定总量时使用不确定进度条。

真实覆盖率、模拟错误注入和平台限制分别报告在 [验收报告](../validation/PHASE3B1_VALIDATION.md) 与 [中文覆盖报告](../validation/PHASE3B1_COVERAGE_REPORT.md)。
