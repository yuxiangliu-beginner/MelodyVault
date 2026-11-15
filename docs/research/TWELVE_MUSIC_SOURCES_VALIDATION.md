# Phase 3B.4：12 个来源真实验证

测试：2026-11-15 09:49–09:56 America/Los_Angeles（UTC−08:00）。起始 commit `fc969fbb0bd4f77f9ec2bd4f47cff32f9dbc5fee`；Windows 10 19045，Python 3.13.2，httpx 0.28.1，PySide6 6.12.0，pytest 9.2.0，mutagen 1.48.1。原始时间以各 JSON 的带时区时间为准。

**主要下载目标未达成：新增完整中文音频下载成功 0 首。** 本轮确实请求了 12 个指定网站，执行了三个中文查询，并跟随一个明确授权中文人声作品的正常下载流程；该流程要求登录。没有将首页、文章标题、许可声明、网盘页面或登录 HTML 计作音频下载成功。

## Phase A：现有项目检查

开始时 Git 工作区干净。读取现有 `PlatformSearchService`、`SourceFallbackManager`、`DownloadEligibilityService` 和下载测试，复用现有边界。正式 SQLite 使用只读连接，schema 10，2,055 Recording、3 download_jobs、68 discovered_sources；完整性 `ok`。完整表计数保存在 `phase-a.json`。复用上轮 musicdl 研究及现有 checkout，没有安装、克隆或执行其 `_search()`/音频解析分支。

现有下载器具有文件级许可核验、录音身份检查、版本冲突拒绝、原子发布及哈希校验；当前正式来源白名单不能由研究页面自动扩展。本轮正式程序代码、GUI 和 schema 均未修改。

## Phase B：12 站访问结果

隔离证据根目录：`.local/reports/twelve-sources-validation/`。`phase-b.json` 包含每站实际 URL、重定向链、HTTP 状态、耗时、抓取字节数及正文 SHA-256；`*.html` 保存有限长度正文。使用可识别的研究 UA，不带账号、Cookie 或会员凭据，TLS 校验开启，并发上限 3、单请求超时 12 秒、正文上限 1 MB。首次沙箱套接字拒绝单独记录为 `sandbox-network-blocked.json`，随后在正常网络权限下重试成功；不能把沙箱拒绝当作网站故障。

| 来源 | 实际访问证据 | 免登录搜索 | 完整音频 | 免登录下载 | 真实下载 | 接入结论 |
|---|---|---|---|---|---|---|
| MyFreeMP3 | 原 URL 302 到 `so.liumingye.cn`；该明确指向的同属域名页面 200，标题为“下歌吧 - 免费网盘资源搜索引擎” | 原音乐搜索 NOT_TESTED | 未核实 | 未核实 | NOT_TESTED | SITE_CHANGED：当前为通用网盘索引，不作为原音乐引擎接入 |
| 下歌吧 xiageba | 200，5.021 秒，音乐搜索表单及网友收集/删除侵权声明可见 | 表单存在；查询 NOT_TESTED | 未核实 | 未核实 | NOT_TESTED | PERMISSION_UNCONFIRMED：自动检索及作品保存权未确认 |
| 无损库 wusunk | 200，1.007 秒；实际站名“无损控” | 三次实际公开文章搜索均 200 | 只有合集/网盘文章声明 | 样本页要求注册、登录、回复 | NOT_TESTED | LOGIN_REQUIRED / PERMISSION_UNCONFIRMED，不接入 |
| 23ape | HTTP→HTTPS 后服务端断开，1.130 秒；HTTPS 有限重试同样断开 | NOT_TESTED | 未知 | 未知 | NOT_TESTED | NETWORK_ERROR，不能判断永久失效 |
| Free Music Archive | 200，0.568 秒；具体中文人声页及许可弹层均 200 | 批量/自动站内搜索 NOT_TESTED；定点作品资料读取成功 | 一个作品页标示 04:55、MP3、非器乐 | 此作品正常下载 302→登录 | DOWNLOAD_FAILED / LOGIN_REQUIRED | 作品授权明确，但该路径不符合免登录要求；暂不接入 |
| cctrax | 301→www，200，1.600 秒；标题为“Best Online Pokies Australia - Play for Real Money in 2026” | NOT_TESTED | 不适用 | 不适用 | NOT_TESTED | SITE_CHANGED，已是博彩内容，停止音乐测试 |
| CD包 | HTTP 521，0.289 秒；一次有限重试仍 521 | NOT_TESTED | 未知 | 未知 | NOT_TESTED | HTTP_ERROR；没有尝试挑战绕过或镜像 |
| Hifi15 | 302→`https://ww38.hifi15.com/`，0.464 秒 | NOT_TESTED | 未知 | 未知 | NOT_TESTED | 重定向未跟随；当前服务身份无法确认，不接入 |
| 网易云 | 首页 200，1.224 秒 | NOT_TESTED：客户端接口的第三方许可未确认 | 未验证 | 未验证 | NOT_TESTED | PERMISSION_UNCONFIRMED；不以首页证明搜索能力 |
| 酷我 | 首页 500，1.418 秒 | NOT_TESTED：接口许可未确认 | 未验证 | 未验证 | NOT_TESTED | 首页 HTTP_ERROR 不代表搜索接口失效；不接入 |
| 咪咕 | 301→`/v5/`，200，1.787 秒；另读官方开放合作页 | NOT_TESTED：缺适用文档/接入授权 | 未验证 | 未验证 | NOT_TESTED | 合作渠道待咨询，不满足当前免账号验证条件 |
| 铜钟 Tonzhon | 200，0.737 秒，页面显示“输入口令永久解锁” | NOT_TESTED：有解锁门槛 | 未验证 | 未验证 | NOT_TESTED | ACCESS_RESTRICTED；没有获取口令、代登录或调用内部接口 |

对所有未执行的步骤，表中“未知/未核实”不表示没有该功能，也不表示失败。`SITE_CHANGED` 只基于本次实际正文作出；Hifi15 的跳转不足以断言域名已转售。

补充检查：

- 下歌吧实际 HTML 有 `/s` 公开表单；robots 对 GPTBot、ClaudeBot 等列出禁止规则，对其他 UA 使用不同规则。这不是 API 授权，也不能概括为全站一律禁止。为避免在命名代理规则不清时自动提交，当前未发歌曲查询；仍需站方明确自动检索及具体文件保存条件。页面网友收集/侵权删除声明不构成权利链。
- 无损控实际公开表单为 `GET /?s=关键词`。只查询三次，没有解析网盘或提取码；具体样本 `/49216.html` 明示需注册、登录并回复才能看网盘链接。首页同时称资源来自互联网、仅供注册用户交流、“24 小时内删除”，这些不能授予歌曲保存权。
- FMA [条款](https://freemusicarchive.org/terms_of_use)允许按文件许可下载，但约束数据挖掘及外站音频直链。此次是已定点确认作品的一次正常下载验证与修正后资格复核，没有批量站内抓取、公开文件直链或绕过登录。持续自动搜索/第三方适配器的允许范围仍需单独确认。
- [咪咕官方开放平台](https://open.migu.cn/portal/)及[新手引导](https://open.migu.cn/order/miguBlack/nguide/)展示企业资料、审核、开发、测试流程。个人项目是否可申请、具体 API Key、曲库和文件下载授权范围仍未确认。不能把 musicdl 的客户端端点当作开放能力。
- 是否试听、时长、外部网盘和提取码：除 FMA 页面的 04:55 及非器乐标记、无损控的百度网盘和登录提取码条件外，其他来源本轮均未取得文件级证据，不能保证试听或完整文件能力。所有站点均未使用账号登录；这不证明其搜索或下载永远无需账号。

## Phase C：真实中文查询

仅对经过检查的无损控正常公开表单提交以下查询。请求时间、URL、HTTP、耗时及实际文章标题记录于 `wusunk-qingtian.json`、`wusunk-jiangnan.json`、`wusunk-huanghun.json` 和 `phase-c.json`。

| 查询 | HTTP | 时间（秒） | 文章条数 | 已核实正确录音数 | 结果判断 |
|---|---|---|---|---|---|
| 周杰伦 晴天 | 200 | 1.210 | 5 | 0 | 合集文章，不能证明目标曲目/录音存在 |
| 林俊杰 江南 | 200 | 1.636 | 2 | 0 | 实际返回 Tate McRae、The Kid LAROI 文章，与目标无关 |
| 周传雄 黄昏 | 200 | 0.737 | 2 | 0 | 同上，无正确录音匹配证据 |

文章搜索请求均为 `SEARCH_SUCCESS`，不等于歌曲搜索命中。曲目时长、专辑、歌曲唯一 ID、原唱/翻唱/现场版本均未知，没有把文章标题变成歌曲元数据。其他来源三首样本为 `NOT_TESTED`，具体原因见 Phase B；不是 `NO_RESULTS`。

补充定点读取 FMA 中文作品[《风中的呢喃》](https://freemusicarchive.org/music/adeline-yeo-hp/single/fengzhongdenenan/)，HTTP 200。这是借助公开索引找到的单个作品资料，不计作 FMA 站内关键词查询成功。

## Phase D：完整音频候选

唯一取得具体文件级许可和作品说明的候选：Adeline Yeo (HP) —《风中的呢喃 (FengZhongDeNeNan)》，FMA 原生 track ID `255896`。页面给出中文歌词、04:55、Instrumental No、MP3 元数据，许可为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0)，正常下载弹层明确允许私人/商业用途并要求保留歌名、作者、FMA 来源和许可署名。页面还披露作品或部分内容由 AI 生成；不能宣称为真人演唱或三首商业测试歌曲的原唱。

这只是**完整音频候选 1 项**：尚未取得音频字节，无法证实实际格式、时长、人声及完整性。后续正常下载要求登录，故**满足本轮全部资格的免登录候选为 0 项**。没有将页面嵌入的存储 URL 当作绕过登录的备用入口。

## Phase E：真实下载尝试

首次使用作品下载弹层明确给出的正常下载操作，实际 HTTP 302 重定向至 `/login`，再返回 HTTP 200 HTML。初版隔离研究脚本将登录 HTML 暂存成 `.mp3` 后被 mutagen 拒绝（`HeaderNotFoundError`），没有发布到正式库，亦未记作成功。已将该研究文件改名为 `.login-response.html` 保留失败证据，并修正研究脚本：登录重定向立即 `LOGIN_REQUIRED` 停止，非音频 MIME 在落盘前拒绝。

修正后再次请求正常下载入口：仍 HTTP 302→`/login`，立即停止，没有发出存储文件请求。`phase-e-initial.json` 保存原失败，`phase-e.json` 保存修正后复核；两个请求属于**同一候选的两次尝试**。真实音频获取尝试 2 次、成功 0 次；其中 HTTP 下载操作确实执行，但没有获得音频。不得把登录 HTML 的字节数或哈希报告为音乐文件大小或 SHA-256。

| 验收项 | 实际结果 |
|---|---|
| 合格音乐文件落盘 | 无 |
| 格式/大小/实测时长 | 不适用：仅获得过登录 HTML |
| 音频 SHA-256 | 无 |
| FFmpeg 完整解码 | NOT_TESTED：无音频文件 |
| 排除试听/截断 | 无法验证；页面时长不能替代文件验证 |
| 作品许可 | 已确认页面 CC BY 4.0；无法消除登录条件 |
| 最终状态 | DOWNLOAD_FAILED，原因 LOGIN_REQUIRED |

文件仅位于 `.local/reports/twelve-sources-validation/downloads/`，该目录含失败 HTML 与署名说明，不含新验证成功的歌曲。没有复用《卿雲歌》或生成测试音频冒充结果。

## Phase F：自动换源

真实跨来源换源 `NOT_TESTED`：没有两个均允许免登录保存、且可证明同一录音的来源；甚至尚无一个全部合格的来源。未将不同歌曲、不同演唱或 FMA 的存储子域当作独立音源。现有 `SourceFallbackManager` 的失败换源、版本拒绝及资格保护通过独立本地回归验证；测试使用明确模拟传输，不是网络换源成功。

## Phase G：接入及回归

**正式新增适配器 0 个。** 原因是没有来源通过免登录搜索方式、录音身份、具体下载许可和真实音频完整性全部检查。按任务条件不强制接入未经验证来源，现有 Apple/Commons 等保持原有能力。新增文件仅为独立研究脚本和本文档，不新增 schema 或正式下载流程。

定向回归命令：`.venv\Scripts\python.exe -m pytest tests/test_downloads.py tests/test_pipeline_foundation.py tests/test_music_platform_ui.py -q --basetemp=.local/pytest-twelve-sources`。实际 **67 passed in 91.02s**，包括模拟故障换源与版本拒绝测试；其中 Qt 测试使用测试事件循环，**不是本轮真人桌面点击或真实下载 GUI 验收**。没有重跑 30 首网络覆盖或所有历史测试。

阶段末只读复核：正式 schema 仍为 10，`integrity_check=ok`，全部业务表计数与 Phase A 完全相同，2,055 Recording、3 个旧下载任务、68 条来源记录均保留；证据 `phase-g-database.json`。没有新增可用适配器，因此正式新来源的 GUI 搜索→下载→入库验收为 `NOT_TESTED`。

## 下一步与验收状态

12 站访问调查和 A–G 各阶段决策均已执行并记录；主要产品验收**未通过**，下载目标不能标记完成。

最值得继续核实的三个渠道（不是已接入/可下载排名）：FMA（具体作品许可最清楚，但当前样本登录门槛及自动查询范围待解决）；咪咕官方合作（有明确洽谈渠道，但与本轮免账号约束冲突）；无损控（公共文章搜索已实测，但结果质量、登录及作品权利链不符合接入要求）。cctrax、通用网盘索引和口令解锁站不值得继续投入下载适配。

若保持免登录硬条件，下一步应获得原创作者直接公开、明确允许自动保存的中文录音或请 FMA 明确其无需账号的正常下载路径；不能承诺周杰伦、林俊杰商业录音可下载。任何放宽条件均需由用户决定。本轮停在 Phase 3B.4，未进入 Phase 3C。
