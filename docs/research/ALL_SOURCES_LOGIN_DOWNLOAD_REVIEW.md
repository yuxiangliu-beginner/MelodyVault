# 全部历史来源：搜索、登录与下载复核

测试日期：2026-11-15，America/Los_Angeles（UTC−08:00）。本轮原始记录从约 21:44 起，各次时间以 JSON 及文件时间为准；Hi歌曲/夸克复用同日紧接本轮之前的 21:38 记录。工作目录 `E:\users\yliu\MelodyVault`，起始 Git `0d49299`，Windows 10、项目 Python 3.13 虚拟环境、Playwright 普通可见 Chrome。

范围：历史 12 站、新 MyFreeMP3、Hi歌曲，以及之前讨论过的开放音频、商业音乐、视频来源，共 28 个音乐/媒体来源；另列 MusicBrainz 与两种外部网盘。没有修改正式应用、GUI、适配器、SQLite、下载任务或音乐库。未修改 SuiSound，未进入 Phase 3C。

## 关键更正

1. **新 MyFreeMP3 本次确实能匿名触发 MP3 下载。** 搜索“周杰伦 晴天”后，经结果菜单 Download、新页面、最终 Download MP3 按钮，得到 HTTP 200、`audio/mpeg`、响应头 Content-Length **11,001,219**，浏览器触发下载事件，建议文件名“周杰伦 - 晴天 [myfreemp3.ink].mp3”。没有登录、验证码或访问控制绕过。此前旧下载路径的 502 **不能概括为整个网站不能下载**。
2. 浏览器下载事件已取消，没有保存未知授权的商业音频。因此 11,001,219 是**服务器声明的字节数**，不是本地已验收文件大小；没有 SHA-256、完整解码、音频身份或截断检查。页面标示 4:30/320kbps 仅是候选元数据。本轮不能宣称《晴天》已完整下载到电脑或许可核验通过。
3. 旧 MyFree 地址虽然改版，仍有音乐搜索：选择“搜索音乐”实际返回 39 条候选，样本 MP3/FLAC 下载转到夸克分享，不再将其笼统写为“已无音乐功能”。
4. 铜钟正常搜索界面本次无需口令即可返回结果，不能仅凭旧 HTML 中口令字段断言所有搜索都被锁定。
5. ccMixter 的直连 HTTP 403 也不等于浏览器不可用：正常作品页 Download → 文件链接实际返回 200/206 `audio/mpeg`，匿名浏览器可打开该 CC BY 3.0 英文/器乐对照样本。本轮未保存或解码，不算新增中文歌曲下载。

## 方法与证据等级

- 普通 Chrome 新建匿名会话、标准网页操作，保留浏览器默认身份；串行小规模操作，通常间隔 3 秒。不伪装爬虫、不复制登录 Cookie、不关闭 TLS、不绕过验证码或 Chrome 安全警告。
- 默认查询“周杰伦 晴天”；部分受限来源仅能检查入口或定点作品。没有重跑每站三首歌或 30 首覆盖率测试。
- 明确区分：实际歌曲搜索成功、登录门槛、服务/网络错误、只返回资料、未验证下载、已收到音频响应、已完成文件校验。网页 HTTP 200 不等于搜索成功。
- “无需登录”只适用于已经实际走到的步骤。“未知”表示未走到该步骤；“需要注册”指没有现有可用账号时需正常取得账号，未实测注册流程。
- 没有注册、购买会员或使用任何账号。出现账号、客户端或安全门槛即记录，不继续绕过。
- 本轮下载事件取消；页面内音频打开可能产生正常浏览器临时缓存，没有发布或登记为用户音乐文件。

## 逐来源结果（28 项）

| 来源 / 实际入口 | 本轮搜索或访问结果 | 登录、注册或其他条件 | 下载实际验证到哪一步 | 当前结论 |
|---|---|---|---|---|
| 新 MyFreeMP3 — `myfreemp3.ink` | 实际搜到标注周杰伦《晴天》的候选 | 已测试完整按钮路径无需登录/注册 | 最终按钮触发下载事件；200 audio/mpeg，声明 11,001,219 字节；取消保存 | 技术下载入口可用；录音身份、完整性和文件保存授权未核验，不自动接入 |
| 旧 MyFree — `tool.liumingye.cn/music/` → `so.liumingye.cn` | 选择音乐模式，实际返回 39 条原唱/现场/翻唱等候选 | 网站搜索无需账号；后续为夸克分享，具体分享后续未测试 | 正常 MP3 按钮展示夸克链接，未取得音频 | 网页搜索可用；外部网盘流程及文件权限待验证 |
| Hi歌曲 — `higequ.com` | 同日真实搜索与《告白气球》作品页成功，页面标示 3:35 | 音乐文件按钮转夸克；进入分享文件夹实际出现登录框；无账号需注册/取得账号 | 到夸克分享与登录框，未下载 | 受夸克登录门槛阻止；不保证登录后文件有效或有保存权 |
| 下歌吧 — `xiageba.com` | 实际搜索与《晴天》作品页成功 | 网站公开显示百度分享与提取码，无需站内账号；本次网盘文件夹下载要求客户端；账号条件未完成验证 | 提取码正常打开分享，文件夹内列出 APE/FLAC/MP3；下载文件夹弹“请使用百度网盘客户端下载” | 搜索/分享可访问；本机匿名网页未取得文件，不把客户端门槛写成已证实登录门槛 |
| 无损控 — `wusunk.com` | 样本合集页可访问；先前三次搜索是文章结果，不是已核实歌曲 | 样本明确要求注册/登录站内账号、发表评论后查看百度链接/提取码 | 在站内账号/回复门槛停止 | 当前匿名流程不可用；正式适配器不接入 |
| 23ape — `www.23ape.net` | Chrome `ERR_HTTP2_PROTOCOL_ERROR`；此前有限重试也断开 | 未知，未到账号检查 | 未执行 | 当前环境网络/协议错误，不能断言永久失效 |
| Free Music Archive | 定点《风中的呢喃》作品及许可弹层可访问 | 点击同意许可后实际 `/download` → `/login`；需要账号，无账号需注册 | 停在 Sign in / Sign up | 作品许可明确；本次下载路径需要登录 |
| cctrax — `cctrax.com` | 重定向后页面为澳洲博彩内容 | 不适用 | 停止音乐流程 | 站点内容已变，当前不能作为音乐源 |
| CD包 — `www.cdbao.net` | HTTP 521 / Host Error | 未知 | 未执行 | 当前服务器不可用；不是已证实账号问题 |
| Hifi15 — `hifi15.com` | 经停放域名跳转到广告目录页 | 不适用 | 停止音乐流程 | 当前入口不提供已验证音乐功能 |
| 网易云 — `music.163.com` | 正常网页提交搜索后出现登录对话框；搜索 iframe 未获得可靠结果 | 当前匿名搜索路径要求登录，二维码/微信/其他正常登录方式 | 未解析、未下载 | 当前流程受账号限制；不将 iframe 提示计作真正无歌曲 |
| 酷我 — `www.kuwo.cn` | 首页 500；正常提交搜索后页面“暂无相关数据，重新刷新页面试试吧” | 未知，登录导航不等于必需登录 | 未解析、未下载 | 当前页面/数据服务异常；不计作可靠零结果 |
| 咪咕 — `music.migu.cn/v5/` | 匿名真实返回《晴天》周杰伦、叶惠美、04:30，另有 Live 等结果 | 搜索无需账号；原唱样本标 VIP；下载具体账号/会员权限未实测 | 仅目录与版本信息，未解析、未下载 | 可用的中文目录搜索；没有证明免费完整文件下载 |
| 铜钟 — `tonzhon.com` | 正常“歌曲搜索”界面实际返回翻唱等候选；未核实周杰伦原录音 | 本轮搜索未要求账号或口令；下载未知 | “下载说明”打开公开说明页；未取得具体歌曲音频 | 搜索可用、录音匹配及下载未核验；不改变弹窗/安全设置 |
| Wikimedia Commons | 复用本阶段已完成的真实搜索/下载证据，不重复下载 | 已验证作品无需登录/注册 | 陈正瑆《是你》Ogg 820,742 字节，SHA-256 与 FFmpeg 完整解码通过 | 已验证可用，但只适用于具体许可作品，不代表商业歌曲可下载 |
| Internet Archive | 官方高级搜索 API 200；`mediatype:audio AND title:晴天` 命中 104 项，抽样返回多为讲话/播客 | 元数据查询无需账号；具体文件权限和账号条件依条目 | 未找到已核实周杰伦录音，未下载 | 公共目录可用，不能将 104 项当作正确歌曲数 |
| ccMixter | 官方 API 200，“晴天”零条；对照作品 The Fade Out 可访问 | 对照作品页明确 Not logged in，正常文件链接可匿名打开 | 浏览器文件响应 200/206 audio/mpeg；未保存/解码；直接 HTTP 客户端曾 403 | 开放作品入口可用；本轮没有正确中文目标或新中文下载成果 |
| Jamendo | 网页正常搜索报错；官方文档公开测试 client_id 的 API 200 但业务 code 11 Suspended Application | 正式 API 需有效开发者 client_id，项目未配置；这不同于听众账号；不能用公开测试 ID 停用证明整个服务失效 | 未取得文件；必须检查每曲 `audiodownload_allowed` | 当前项目 API 配置不足，网页查询亦未成功 |
| Openverse | 官方音频 API 200，晴天返回 1 项《晴天雨》，不是目标周杰伦录音 | 本次公共元数据查询无需账号；文件条件取决于原站 | 只提供 Jamendo 等原站索引，未下载 | 索引可用；不是独立文件源，也不是正确目标歌曲命中 |
| Apple iTunes | 复用已有真实 API/GUI 搜索结果，中文目录可用 | 既有公共目录查询无需账号 | 预览/元数据不能计作完整歌曲文件 | 可用于身份与目录信息，不能据此自动下载完整商业歌曲 |
| 5sing — `5sing.kugou.com` | 首页 200；正常提交搜索的新页出现 Chrome“不安全的表单”警告 | 登录/注册入口存在，但搜索、下载必需条件未知 | 未点击“仍然发送”，未取得结果或文件 | 当前搜索流程遇到安全警告，停止；不是认定全站永久失效 |
| Audiomack | 匿名搜索返回标注晴天/周杰伦的用户上传作品 | 搜索/作品页无需账号；样本操作菜单无独立 MP3 下载 | 只检查作品及菜单，没有取得可保存文件 | 标注不证明官方原唱；App 离线功能不等于 Windows MP3 导出 |
| DTSHOT — `www.dtshot.com` | Chrome `ERR_NAME_NOT_RESOLVED` | 未知 | 未执行 | 当前检查域名 DNS 不可达，没有猜测镜像 |
| QQ音乐 — `y.qq.com` | 正常搜索路径弹 QQ/微信登录，并提示客户端下载更多内容 | 当前路径有登录与客户端提示；未登录验证后续 | 未解析、未下载 | 当前匿名流程受限；注册不保证下载资格 |
| 酷狗 — `www.kugou.com` | 匿名正常搜索返回周杰伦晴天、Live、伴奏等候选 | 搜索无需账号；查看更多内容提示客户端下载；具体下载账号/VIP条件未知 | 未解析、未下载 | 目录搜索可用；未证明完整音频保存能力 |
| YouTube | 匿名正常搜索出现周杰倫 Jay Chou 官方《晴天》MV（5:19）及翻唱 | 搜索无需账号/API Key；官方电脑离线观看帮助要求登录 Premium，非独立 MP3 导出 | 未提取视频音轨或下载 | 网页发现可用；视频时长不等于录音室音频时长 |
| Bilibili | 普通搜索新标签页真实返回大量中文歌曲视频；未因登录邀请停止搜索 | 本次搜索无需登录；保存能力/账号条件未测试 | 未提取或下载 | 视频发现可用；没有完整原唱音频或下载权限证明 |
| 抖音 — `douyin.com` | 正常搜索后显示“登录后即可搜索更多精彩视频” | 当前搜索流程需要正常账号登录 | 未解析、未下载 | 当前匿名流程受限，短视频也不自动当完整歌曲 |

## 账号与注册汇总

**已经实际遇到账号门槛：**

- FMA：样本正常下载跳登录；没有账号需注册。
- 无损控：站内注册/登录并回复后才展示链接，后续网盘还需另行验证。
- Hi歌曲 → 夸克：公开分享外层可查看，进入文件夹出现登录；没有夸克账号需取得账号。此结论仅针对实际样本。
- 网易云、QQ音乐、抖音：当前匿名正常搜索路径出现登录门槛；没有实测登录后的内容或下载。

**另外的依赖：**

| 项目 | 实际证据 | 不能据此推断什么 |
|---|---|---|
| 夸克网盘 | Hi歌曲样本分享共 3 个文件、82.6M，外层显示名为 `168` 的文件夹及“2项”；进入文件夹出现二维码/手机号登录框 | 不是“1682 项歌曲”；不是全部歌曲已验证，也不保证注册后目标录音存在、可下载或有保存权 |
| 百度网盘 | 下歌吧样本凭公开提取码匿名进入，可看到周杰伦 - 晴天.ape / .flac / .mp3；文件夹整体下载提示需要客户端 | 没有完成客户端登录或真正文件下载，不能仅凭页面登录入口断言这次下载已被账号阻止；后续批量文件操作短时间停在“正在获取下载链接” |
| Jamendo 开发者 | 官方 API 要有效 client_id；当前未配置项目自己的凭据，文档公开示例应用已暂停 | 不是会员破解问题；也不是证明所有 Jamendo 作品要求付费或个人账号 |
| YouTube Data API | 项目没有 API Key；普通浏览器搜索仍实际成功 | “未配置 API”不等于网页不可搜索；离线观看会员也不授予任意第三方 MP3 提取能力 |
| MusicBrainz | 已有官方目录/身份匹配服务；不重复测试 | 不是音频源，Recording/Work 匹配成功不等于文件可以下载 |

## 本轮下载统计与限制

- 新增**已保存、通过 SHA-256/完整解码的完整中文歌曲：0 首**。没有把浏览器下载事件、响应头、网页时长或网盘文件名当成完整下载验收。
- 新 MyFreeMP3：**1 个中文商业歌曲候选的匿名下载事件已触发**，文件保存许可 `LICENSE_UNVERIFIED`，取消保存。不能报告网络不可用，也不能报告完整文件已验收。
- ccMixter：1 个非中文目标对照样本匿名音频响应成功，未保存/解码，不计中文成果。
- 历史可复现的真实成功：Commons 原创中文人声《是你》1 首，来自已完成的 Phase 3B.5 验证；本轮不重复累计。[下载、哈希与 GUI 证据说明](PHASE_3B5_CHINESE_VOCAL_DOWNLOAD.md)。
- 所有未确认许可候选保留为“许可未核验”，不据此删除搜索结果，也不自动进入正式下载器。
- 站点/API 浏览器搜索是否允许持续自动访问、适配器接入条款和每首录音保存权仍须分别核实；匿名技术可用不是上述全部许可的证明。本轮没有新开正式适配器。

## 原始证据与复现

本轮忽略目录：`.local/reports/all-sources-review/`。JSON 存储实际 URL、时间、HTTP/浏览器事件、可访问性快照和异常；PNG 为实际截图。没有将原始网页、分享链接提取码、音频、Cookie 或数据库提交 Git。

| 检查 | 主要证据文件 |
|---|---|
| 新 MyFree 全流程 | `myfree-ink.json`、`myfree-final.json`；后者包含 200 audio/mpeg、Content-Length、download 事件与取消标记 |
| 旧 MyFree 音乐模式/夸克按钮 | `myfree-old-search.json`、`old-myfree-song.json` |
| 下歌吧及百度客户端门槛 | `xiageba-search.json`、`xiageba-song.json`、`baidu-final.json`、`baidu-single-file.json`（脚本名虽为 single，实际快照显示选中三个文件，不是单文件测试） |
| Hi歌曲与夸克登录 | 同日 `.local/reports/higequ/result.json`、`music-button.json`、`quark-share.json`、`quark-folder.json` |
| FMA 登录 | `fma.json`、`fma-download.json`、`fma-final.json` |
| 网易云/酷我/咪咕/铜钟 | `netease-search.json`、`kuwo-search.json`、`migu-search.json`、`tonzhon-search.json`、`tonzhon-help.json` |
| 视频来源 | `youtube-search.json`、`bilibili-final.json`（搜索在第二标签页）、`douyin-search.json` |
| 其他商业/创作者站点 | `qqmusic-search.json`、`kugou-search.json`、`audiomack-search.json`、`audiomack-song.json`、`5sing-final.json` |
| 不可达/改版 | `23ape.json`、`cdbao.json`、`hifi15.json`、`cctrax.json`、`dtshot.json` |
| 公共 API | `archive-api.json`、`ccmixter-api.json`、`ccmixter-control.json`、`openverse-api.json`、`jamendo-api.json` |
| ccMixter 浏览器与直接 HTTP 差异 | `ccmixter-file-headers.json`（403）、`ccmixter-browser.json`（正常按钮）、`ccmixter-file-click.json`（Chrome 200/206） |
| 已有 Commons/Apple GUI 实证 | `.local/reports/phase-3b5/gui-final/validation.json`，本轮未重新下载 |

使用项目现有 Playwright/Python，未安装 musicdl 或下载破解工具。主要脚本为 `browser_batch.py`、`search_batch.py`、`search_extras.py`、`drill.py`、`download_checks.py`、`last_checks.py`、`final_followup.py`，均在隔离忽略目录；这些脚本依赖当时真实页面结构，不能当作稳定正式接口。

检查中有一次终端 GBK 输出 `©` 抛 UnicodeEncodeError：发生在 `final_followup.py` 已写入 UTF-8 JSON 和截图之后。已通过 `python -X utf8` 重新读取证据核验；未把脚本退出码 1 当作平台失败，没有重复发请求来掩盖异常。

未运行历史 pytest 或全部历史网络测试：正式程序代码没有修改，本轮验证对象为实时网站流程。文档检查使用 `git diff --check`；该检查不证明网站或文件下载成功。

## 条件说明的官方参考

- [YouTube：在电脑上离线观看视频](https://support.google.com/youtube/answer/11977233?co=GENIE.Platform%3DDesktop&hl=zh-Hans)：账号/Premium 与平台内离线观看条件；这不是第三方音频导出 API。
- [Jamendo API authentication](https://developer.jamendo.com/v3.0/authentication)、[tracks API](https://developer.jamendo.com/v3.0/tracks)：client_id 与逐曲下载允许字段；本轮 code 11 是实际业务响应，不是 HTTP 错误。
- [ccMixter Query API](https://license.ccmixter.org/query-api)、[对照作品页](https://ccmixter.org/files/Coruscate/70473)：公共元数据及具体作品许可。
- [FMA 使用条款](https://freemusicarchive.org/terms_of_use)：具体文件许可、站点使用和自动化接入需要分别核对；本轮登录要求另有浏览器实证。

本轮到此停止，等待用户决定账号登录或下一来源的授权核实；没有修改正式下载流程。
