# Phase 3B.1 来源调查依据

调查日期：2026-11-14。下列政策仅证明特定接口的使用方式，不为任意上传录音背书。

| 来源 | 官方依据 | 本程序采用的范围 |
|---|---|---|
| Wikipedia / MediaWiki | [API Search](https://www.mediawiki.org/wiki/API:Search)、[External links](https://www.mediawiki.org/wiki/API:Extlinks)、[Etiquette](https://www.mediawiki.org/wiki/API:Etiquette) | 公开百科搜索与页面外链；不等同全网结果 |
| Brave（可选） | [Search API](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started) | 用户自行配置正式 API 密钥；本轮未配置，不宣称实测 |
| Commons | [文件复用政策](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia) | 官方 API 原始文件和逐文件许可；作者署名不自动当作演唱者 |
| Internet Archive | [开发者接口](https://archive.org/developers/) | 搜索/文件元数据调查；上传者权利链不足不下载 |
| Jamendo | [Tracks API](https://developer.jamendo.com/v3.0/tracks) | 无 client_id，未请求；仍需 audiodownload_allowed 与文件许可 |
| ccMixter | [明确的第三方 Query API 权限](https://license.ccmixter.org/about)、[API 参数](https://ccmixter.org/query-api) | 有界 JSON API，不运行 JS；仅固定原始文件路径可能进入逐文件审核 |

ccMixter 的 robots.txt 包含对 /api/ 的索引排除；同时其专门 API 使用政策明确面向第三方程序公开 Query API。本程序只对这个正式接口采用具体许可，不将其解释为普通网页的抓取许可。
搜索用 `search` 与 `search_type=all`、按文件查询用 `ids`、输出 `f=json`。真实 JSON 是数组，与原来源 JSON 字典接口不同。

真实中文候选 [The King 之王](https://ccmixter.org/files/solos_to_use/49286) 提供 MP3/FLAC 元数据，页面将其描述为传统粤语歌的无伴奏翻唱。其 CC BY-NC 3.0 上传许可未独立解决底层作品权利，所以本程序保留 LICENSE_UNVERIFIED，未请求音频。
这个例子既不是周杰伦原唱，也不能仅因存在下载地址就计为中文下载成功。
其他发现的十秒诗歌朗读、二胡短采样、包含未解决旧流行歌采样的混音，也未计作完整中文歌曲成功。

真实候选 URL、每个查询和来源结果在本地隔离报告；可分享的逐歌曲/来源统计在 [覆盖报告](../validation/PHASE3B1_COVERAGE_REPORT.md)。不提交音频、私人数据库和完整运行缓存。
