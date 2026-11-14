# MelodyVault Phase 2 实测记录

日期：2026-11-13，Windows 10 x64 / Python 3.13.2。沿用现有项目、Song/Recording及人工审核，追加schema v5。本轮范围为目录性能、来源元数据搜索/匹配/授权说明、真实进度和独立Chrome；没有音频下载或Google Drive上传。用户确认Jamendo暂无client_id，明确跳过；未核验授权保留LICENSE_UNVERIFIED、原因和原始链接，不阻断其他来源。

## 目录性能与独立补证

以下使用**全新SQLite目录、强制在线、API缓存0**，最终代码遵守1.1秒MusicBrainz请求间隔，503/429/超时指数退避，Retry-After为0也不取消退避底限。

| 实测 | 周杰伦 | 林俊杰 | 周传雄 |
|---|---:|---:|---:|
| Artist MBID | a223958d-5c56-4b2c-a30a-87e357bc121b | e5d8c705-8ea4-4820-b11d-fbf580d85ce4 | 27c24ef3-a0c6-41d3-b704-21bbe769e744 |
| 原始音频Recording | 710 | 443 | 368 |
| 首次目录总耗时（秒） | 63.666 | 53.453 | 17.360 |
| 实际API请求（包含重试） | 26 | 19 | 10 |
| 自然发生的503重试次数 | 6 | 7 | 1 |
| 首批可显示时间（秒） | 8.611 | 5.055 | 2.001 |
| 首批Recording数 | 85 | 89 | 100 |
| 完成后快速目录Song/待确认条目 | 674 | 420 | 350 |
| 新目录后台服务再次SQLite读取（秒） | 0.384 | 0.320 | 0.097 |
| 再次读取API请求 | 0 | 0 | 0 |

普通目录没有请求深度Work关系。这些新目录有0个Work已核实作品，不把缺Work误称为重复或已核实；有明确录音/发行证据的上下文簇仍待确认，所有Recording完整保留。已有正式运行库继续使用之前已保存的Work和人工决定：周杰伦572个Song条目（192已核实+380待确认），林俊杰403（48+355），周传雄347（16+331），全部可立即进行来源查询。

“周传雄此前约530请求”是包含深度补证的旧路径，本轮10请求是分离后的快速目录路径，任务范围不同，不用两者宣称相同工作量下的百分比加速。第一次在线结果受真实503/服务器等待影响，首批时间不保证固定2秒。

现有目录纯后台服务本地读取分别为0.390/0.320/0.107秒；最终Windows真实输入—点击—表格显示分别为 **0.707/0.485/0.381秒**，API均为0。原生窗口全流程心跳最大间隔0.251/0.168/0.135秒，分别646/411/661次心跳，目录/来源按钮在补证期间仍可操作。目录刷新和深度补证为独立操作，明确刷新才联网更新保存目录。

独立补证实测（使用既有真实官方缓存，不是假API）：

| 补证任务 | 周杰伦 | 林俊杰 | 周传雄 |
|---|---:|---:|---:|
| 首轮独立任务耗时（秒） | 14.147 | 4.950 | 19.596 |
| 网络请求 / API缓存页 | 0 / 43 | 0 / 7 | 0 / 5 |
| no_work负缓存Recording数 | 411 | 377 | 349 |
| 再次整任务缓存读取（秒） | 0.003 | 0.004 | 0.003 |
| 再次网络请求 | 0 | 0 | 0 |

no_work表示该Recording上次读取的直接Work关系为空，不代表没有作品、不代表重复，也不抹掉其他身份辅助证据。实体检查时间和7天有效期持久化，Recordings集合变化会使整任务摘要失效；手动强制刷新忽略正/负及整任务缓存。

原生GUI中对周传雄启动LowPriority强制补证，在实际首批关系返回后点击取消：2次真实请求、0缓存，3.011秒退出；已有368个Recording及347个Song条目保留，界面保持响应。取消无需先完成全部补证，不会把取消记作目录成功。

## 三歌手音源搜索结果

最终使用修正后的Commons简/繁/英文短语查询（source-query-v2），Archive官方API，Jamendo明确未配置。每位先单首，再5个不同显示标题的Song任务，再重复同样5首验证缓存；单首已包含在5首内，**不重复相加**。

| 五首批量 | 已处理 | 有候选歌曲 | 已验证文件许可 | 授权未验证候选 | 无结果歌曲 | 失败歌曲 | 元数据HTTP请求 | 耗时秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 周杰伦 | 5 | 1 | 0 | 1 | 4 | 0 | 16 | 18.327 |
| 林俊杰 | 5 | 0 | 0 | 0 | 5 | 0 | 12 | 52.873 |
| 周传雄 | 5 | 0 | 0 | 0 | 5 | 0 | 16 | 18.062 |
| 合计 | **15** | **1** | **0** | **1** | **14** | **0** | 44 | 不作并行性能指标 |

单首：周杰伦“晴天”6次元数据请求、6.531秒，候选1；林俊杰“江南”3次、3.323秒、无候选；周传雄“黄昏”4次、4.543秒、无候选。批量会复用单首及其他仍有效的既有尝试，所以请求数不等于歌曲数乘固定来源数。上述耗时为实际队列建立后到结束，不是模拟计时。

重复5首均为0次HTTP请求，分别3.634/3.534/3.965秒。成功候选缓存24小时，空结果6小时，缓存命中不会把原检查时间延长；失败可立即重试。匹配快照包括歌手、Song、Recording集合、已知别名/版本/时长，不能仅凭同名复用其他作品的结果。

“晴天”的唯一候选来自 [周杰倫 Jay Chou Piano](https://archive.org/details/jay-chou-piano-40)：文件标签声称歌手周杰伦、时长268秒，但页面是钢琴合集，且没有明确许可。结果为 **instrumental / VERSION_MISMATCH / LICENSE_UNVERIFIED**，匹配分0；原因和网页链接持久化。没有因同名、相近时长、“Free Download”页名或下载按钮就当作原唱或合法完整音源。

计数定义：已搜索包括成功/无结果/失败的已结束歌曲；已完成、失败、待处理互斥合计为本次总数；失败包含至少一个已配置来源错误的歌曲，其他来源继续。无结果指本次已配置来源/关键词与上限内无候选，不能解释成整网没有合法音源。授权计数按候选文件；“已核实匹配来源”另要求METADATA_MATCH，本轮为0，不表示已核实原唱。UI候选列表含该歌手历史结果，明确区别于本次队列统计。

## Chrome与真实开放许可对照

真实Google Chrome **156.0.8078.80**，Python Playwright **1.65.1**。产品自行启动空白隔离会话；没有使用Codex Chrome插件或用户浏览资料。真实公开搜索等待搜索结果标题和结果feed，读取“晴天”对应真实Archive条目；独立元数据引擎的可选Chrome来源及再次缓存也实测。读取候选页面和Commons真实文件说明页均成功，监听到的音频响应为0；下载/音频请求被阻止。

真实Commons独立对照为Chopin/Nocturne，返回5个用户录制音频的文件级开放许可（如 [D-flat Op.27 No.2 文件说明](https://commons.wikimedia.org/wiki/File:Chopin_-_Nocturne_in_D-flat_Op-27_No-2_(Piano_Performance_by_eld%C3%BCendes%C3%BCarez).wav)）。真实Chrome能读取其Creative Commons说明，音频响应0。**这些对照不属于三位测试歌手，不混入上表授权数量**；作者或作曲家不能填充为演唱者，许可证字段也不能证明目标录音身份。

API优先、Chrome仅补充已核实允许访问页面。先检查robots、固定域名/路径白名单，无登录/验证码处理/代理/隐藏流提取。API访问失败时不会自动改用Chrome绕过。HTTP请求指标仅指元数据/robots客户端，不包含浏览器页面的所有静态子资源；Chrome版本、导航页面与可见内容另存证据。页面读取本身不升级LICENSE_UNVERIFIED。

官方依据：[Archive自动访问说明](https://archive.org/developers/bots.html)、[Archive metadata API](https://archive.org/developers/md-read.html)、[Commons API](https://commons.wikimedia.org/wiki/Commons:API)、[MediaWiki imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo)、[Jamendo下载允许标志](https://developer.jamendo.com/v3.0/tracks)、[MusicBrainz限速](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)。

## 自动与原生测试

最终完整pytest：**95 passed in217.22s，0 failed / 0 errors / 0 skipped**，包括“已完成+失败+待处理=本次总数”的失败隔离断言。JUnit：`pytest-accepted.xml`。前一轮95 passed in187.82s也保留，最终结果以accepted报告为准。`pip check`：No broken requirements found。

测试包含：SQLite迁移/事务和原始保留、旧Song/Work归并与人工审核/撤销、保存目录零网络、按页partial、独立正/负补证缓存和强制刷新、同名不同作品/歌手/版本、钢琴合集误导标签、未知权利原因与链接、许可域名/下载标志、逐来源失败隔离、无结果缓存/指纹变化、取消后复用成功来源、失败项重试、实际Qt控件/线程/关闭，以及两位歌手真实MusicBrainz完整服务回归。三位歌手的首次在线、来源、补证和Windows原生完整流程另由上述脚本实测。

503为自然发生的真实在线结果；429和读取超时通过明确的HTTP故障注入验证重试/退避，没有对官方服务制造限流，也不谎称在线发生429。固定Qt计时器只用于测试事件循环心跳/截止，不用来生成业务进度。

原生GUI三位均通过：中文输入、从SQLite显示、歌曲树与状态、歌曲右键单首搜索、5首批量、未核验原因与原始链接、Chrome页面检查、强制补证后取消、低优先级和UI心跳；版本展开另有实际Qt控件回归覆盖。最终原生截图及默认1040×720窗口已实际查看，没有专辑列表，全部操作可见。

## 数据保留与范围

全库原始 **1520** 条Recording payload SHA-256逐条一致（歌手内710+443+368存在1条共享Recording），旧v1–4迁移name/checksum一致，原人工审核事件0条完整保留，integrity_check=ok、foreign_key_check无错误。实际pytest人工审核只写临时数据库，未伪造正式用户决定。downloads/cloud原文件hash不变，未修改SuiSound。运行数据/查询/截图/浏览器缓存/数据库和凭据全部被Git忽略。

失败和修复记录保留：首轮70 passed/1 failed/2 deselected，是旧UI断言仍假定后台自动Work补证；修正后通过。CLI初次因系统Node16不满足版本退出，改用Python Playwright自带Node26进行CLI验证。最初原生15.567/7.680/3.712秒受QTest等待循环持有GIL干扰；保留初测后改用Qt正常事件循环，最终为上表0.707/0.485/0.381秒。Commons曾错误使用Solr分组导致漏报，对照检索发现后修正、缓存指纹更新并重新实测，旧结果不作为最终有效来源结果。所有这些都不曾标记为下载成功。

## 本地证据与复现

证据根目录 `.local/reports/phase2/`（均不提交Git）：`before-phase2.sqlite3` / `baseline-hashes.json`、`preservation.json`、`catalog-final/catalog-online.json`、`evidence.json`、`source-search.json`、`chrome-final.json`、`engine-chrome.json`、`commons-control-final.json`、`commons-chrome-page.json`、`native-release/native-gui.json`及六张原生截图、`default-window-sources.png`、pytest XML。`output/playwright/phase2-chrome-search.png`为独立CLI Chrome公开搜索截图。

```powershell
Set-Location E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
# 已保存歌手直接显示；目录刷新、低优先级补证、音源搜索分别操作
.\.venv\Scripts\python.exe scripts\validate_phase2.py --stage catalog --report-root .local\reports\phase2\catalog-new
.\.venv\Scripts\python.exe scripts\validate_phase2.py --stage evidence
.\.venv\Scripts\python.exe scripts\validate_phase2.py --stage sources
.\.venv\Scripts\python.exe scripts\verify_phase2_gui.py --report-dir .local\reports\phase2\native-new
$env:MELODYVAULT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-new --junitxml=.local\reports\phase2\pytest-new.xml
```

## 未解决问题和验收边界

三位歌手本轮没有找到已核实可保存的目标录音，不能承诺开放库收录商业歌手完整音乐。Jamendo真实查询因未提供client_id而未执行，未把适配器契约检查当作真实测试。API或HTML结构、访问条款可能变化；候选数有界，授权字段不是完整权利链核验，仍需后续阶段审批。已保存目录默认不会自动联网更新，用户可明确刷新；缓存有效期并非来源永远存在的保证。HTTP取消需等待当前请求结束，浏览器还可能等待当前渲染条件的超时，期间UI可响应。

本轮仅Windows10 / Python3.13.2 / 本机Chrome实测，Windows11、其他Python、无Python独立exe尚未验收。用户将下载/上传/断点恢复安排在后续Phase5，本轮不提前实施。**本轮实现与自动/真实测试完成，Phase2等待用户验收；停止，不进入下一阶段。**
