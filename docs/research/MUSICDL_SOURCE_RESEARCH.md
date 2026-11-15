# musicdl 中文音乐来源研究

研究时间：2026-11-15 09:29（美国太平洋时间，UTC−08:00）；环境 Windows 10 19045、Python 3.13.2。MelodyVault 起始提交 `7167679a46414c7d8df7e74ce910daf4f1585396`，schema 10。本轮没有运行或安装 musicdl；只读克隆位于被忽略的 `.local/reports/musicdl-research/upstream/`。审阅版本为 [musicdl master `dca2f0967e46a8faf8d279737535471102d74ca3`](https://github.com/CharlesPikachu/musicdl/tree/dca2f0967e46a8faf8d279737535471102d74ca3)，该提交时间 2026-10-16，包版本 2.14.2；这说明仓库近期有更新，不代表每个接口现在有效。

## 对比结果

| 检查项目 | 网易云 | 酷我 | 咪咕 |
|---|---|---|---|
| 适配器源码存在 | 成功 | 成功 | 成功 |
| 源码已检查 | 成功 | 成功 | 成功 |
| 实际网络搜索 | **未测试**：未确认第三方自动搜索授权 | **未测试**：未确认授权；源码搜索使用 HTTP 客户端接口 | **未测试**：未确认自动搜索授权 |
| 中文歌曲匹配 | 未测试 | 未测试 | 未测试 |
| 完整音频候选 | 源码有解析分支；本轮未请求，实际情况无法确认 | 源码有解析分支；本轮未请求，实际情况无法确认 | 源码有解析分支；本轮未请求，实际情况无法确认 |
| 试听限制 | 无法确认具体曲目 | 无法确认具体曲目 | 无法确认具体曲目 |
| 需要登录 | 源码有默认 Cookie 与可选用户 Cookie；具体搜索/文件是否需要登录**未测试** | 搜索代码未要求显式 Cookie，音频路径可能使用 Cookie；实际**未测试** | 搜索代码未显式要求 Cookie；具体音频权限**未测试** |
| 需要会员 | 具体曲目与授权未测试，不能推断免费完整音频 | 平台会员协议明确有不同播放/下载权益；具体曲目未测试 | 具体曲目与授权未测试 |
| 官方授权方式 | 面向本应用的搜索/保存授权**无法确认** | 面向本应用的搜索/保存授权**无法确认** | 面向本应用的搜索/保存授权**无法确认** |
| 真实完整音频下载 | 未测试、0次实际下载 | 未测试、0次实际下载 | 未测试、0次实际下载 |
| 适合接入 MelodyVault | 暂不接入；先核实授权 | 暂不接入；先核实授权 | 暂不接入；先核实授权 |

“未测试”不是零命中，也不是认定接口已经失效。所谓“官方”下文仅描述请求域名或源码函数名，**不代表接口有第三方公开文档或已授权本应用使用**。

## 实际网络测试范围

仅以独立只读 HTTP 客户端请求各平台首页与 robots.txt；没有提交 Cookie、API key，没有关闭证书验证、访问聚合解析器或执行源代码。机器记录 `.local/reports/musicdl-research/network-probes.json`。

| 平台 | robots.txt | 首页 | 含义 |
|---|---|---|---|
| 网易云 | HTTP 200，1.192秒 | HTTP 200，0.529秒 | 首页可访问；robots 对不同爬虫有不同规则，不构成第三方 API 及音频下载许可 |
| 酷我 | HTTP 404，0.967秒 | HTTP 500，0.562秒 | 本次首页出错；不能据此断定搜索 API 永久失效 |
| 咪咕 | HTTP 404，1.498秒 | HTTP 301，0.266秒，指向同站 `/v5/` | 收到重定向；未追踪或将其计为搜索成功 |

每平台的《晴天》《江南》《黄昏》三项歌曲搜索均为**未测试**：适配器所用的客户端接口未找到明确适用于 MelodyVault 的第三方检索授权，按本任务约束不直接调用。因而返回数、匹配数、歌曲时长和专辑的**实际结果均未知**，也没有进行完整音频、试听、会员状态或下载测试。单项首页探测延迟不是歌曲搜索耗时。

## 源码发现

- [网易适配器](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/musicdl/modules/sources/netease.py#L48) 构造 `music.163.com/api/cloudsearch/pc` POST 搜索；[搜索逻辑](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/musicdl/modules/sources/netease.py#L680) 读取 `result.songs`，随后自动调用第三方解析与播放器接口，并只收集其判定为有有效音频地址的条目。源码提取名称、歌手、专辑和毫秒时长；字段存在不证明服务器当前会返回，版本及原唱也不能仅凭名称确认。其[第三方解析链](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/musicdl/modules/sources/netease.py#L627) 的部分注释涉及会员等级；部分分支显式 `verify=False`，部分使用客户端加密参数或第三方服务。本轮未执行这些路径，无法判断所有分支是否能播放或是否涉及规避限制。
- [酷我适配器](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/musicdl/modules/sources/kuwo.py#L44) 使用 `http://www.kuwo.cn/search/searchMusicBykeyWord`，读取 `abslist`，源码解析标题、歌手、专辑、秒级时长；这属于酷我域名的客户端接口，面向第三方的授权及当前可用性未核实。源码还列出 MP3、FLAC 及加密格式，使用第三方解析和加密查询；格式名称不证明所选歌曲有完整文件。仓库含独立解密相关脚本，本轮没有运行、移植或判断其对每个文件的作用。
- [咪咕适配器](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/musicdl/modules/sources/migu.py#L46) 请求 `c.musicapp.migu.cn` 的 `search_all.do`，搜索读取 `songResultData.result`，解析名称、歌手和专辑；播放地址分支另行获取时长，包含响应解码、格式选择及地址改写逻辑。源码跳过标识为加密的某类格式，但这不证明其他文件可以合法下载或保证完整。该接口是否面向本应用公开、实际返回内容及账号权益均未核实。
- 三者的 `_search` 不只是目录搜索：源码会在循环内尝试解析音频，再按地址状态筛选。直接运行它不能满足“只测试目录、不请求未获授权音频”的隔离要求。[通用下载器](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/musicdl/modules/sources/base.py#L191) 包含 HTTP/HLS、并发及错误记录；这些能力不是对任何具体录音的授权或完整性证明。

## 来源使用条件与许可

[musicdl LICENSE](https://github.com/CharlesPikachu/musicdl/blob/dca2f0967e46a8faf8d279737535471102d74ca3/LICENSE) 为 PolyForm Noncommercial 1.0.0；其个人非商业研究条款与通知、分发条件需要一并考虑。[项目 README](https://github.com/CharlesPikachu/musicdl/tree/dca2f0967e46a8faf8d279737535471102d74ca3) 还写有非商业及再分发限制声明。二者的具体关系和未来发布兼容性需权利人或专业人士确认；**软件源码许可不授予平台接口或歌曲版权许可**。本轮没有复制该项目源码到 MelodyVault。

[酷我用户服务协议](https://www.kuwo.cn/static/page/customer/customerservice.html) 对软件和内容权利分别规定，并不因软件使用许可自动授予内容权利；[酷我会员协议](https://vip1.kuwo.cn/vip/added/mobile/v9/agreementServiceAndroid.html) 表明不同内容的下载/缓存权益可受限制。[咪咕用户协议](https://g.10086.cn/h5/cloudgame/game/serviceAgreement.html) 覆盖其音乐产品和站外 API 引用，涉及收费服务时另有条件；该协议不单独证明 musicdl 所用接口面向第三方开放。[网易云服务条款的第三方历史快照](https://github.com/metowolf/Agreement/blob/master/netease/%E7%BD%91%E6%98%93%E4%BA%91%E9%9F%B3%E4%B9%90%E6%9C%8D%E5%8A%A1%E6%9D%A1%E6%AC%BE.txt) 对未经认可的第三方兼容软件有约束；此快照并非本轮已独立核实的官方现行版本。应向平台核对最新协议及具体 API 授权，而非根据域名、robots 或源码函数名推断许可。

## 接入结论与下一步

现阶段三个平台均无已验证的可用完整音频下载通道，**不应将任何一个标记为可下载或接入正式下载器**。如需确定下一步调查顺序，网易云可作为第一项**授权咨询**：其公开首页本机返回200且适配器搜索数据模型较清晰；这只是调研顺序，不是接口可用性排名，也不证明比另外两家更适合下载。酷我和咪咕并列待核实，现有证据不足以排序。

取得平台明确授权和测试凭据后，再分别在独立 provider 实现已授权的目录查询，验证限速、取消、超时及真实歌曲匹配；把搜索结果接入现有 `PlatformSearchService` / `SearchOrchestrator`，以具体文件的录音身份、完整性和保存授权作为 `DownloadEligibilityService` 前置条件，再通过 `SourceFallbackManager` 和现有 `DownloadManager` 执行。扩展固定来源白名单须以官方文件域名与许可为依据。凭据放本地配置或环境变量，不提交；是否需要新依赖取决于官方 SDK。现有 schema 10 记录能力可作为起点，是否需要追加迁移应依据官方授权证据字段而定。

本轮未更改正式下载流程、正式音乐库、下载任务或 SuiSound；未下载测试音频，未进入 Phase 3C。
