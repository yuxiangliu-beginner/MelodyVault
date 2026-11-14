# Phase 3B.1 验收记录

状态：开发与测试完成，等待用户验收；未进入 Phase 3C。日期：2026-11-14。

## 最终结果

| 检查 | 实际结果 |
|---|---|
| 开发前基线 | 169 passed in 307.60s |
| 开发中完整回归 | 187 passed / 2 未启用在线用例；随后 194 passed in 300.38s |
| 最终发布回归 | **194 passed in 309.93s；0 failed / 0 skipped** |
| 新增来源/安全/界面用例 | 25 项；包含故障注入，不冒充真实联网 |
| 正式 SQLite | schema 7 → 8；integrity_check=ok |
| 原始 Recording | 2,055 → 2,055；全部原始 payload SHA-256 一致 |
| 人工审核 / 统一搜索确认 | 原 0 / 0 行保持；未创建用户审核事件 |
| 下载任务 / 设置 | 原 2 个 dry-run SKIPPED 任务原样保留；设置仍未开启实际下载 |
| 真正联网中文基准 | 固定 30 首 / 8 歌手，逐首逐来源见覆盖报告 |
| 下载控制 | 原始 MP3 与 WAV 各 1 个真实成功；MP3 RANGE_ACCEPTED 续传及重复文件复用 |
| 本地启动 / 依赖 | `--init-db` 返回 schema 8；pip check 无依赖冲突；compileall 通过 |

两项 opt-in 目录集成测试在正式实库上保留运行；它们可能复用目录缓存，不能把该 pytest 标签当作每次均访问了官方服务器。真正强制联网的 30 首基准另有请求、错误和时间记录。

## 实现及验收边界

- 动态发现：公开 Wikipedia 官方搜索/外链 API；可选 Brave 官方 API，当前无密钥，未宣称通用全网已实测。发现域名默认待审核，不执行远程插件。
- 注册表：网站去重、能力三态、检查/发现历史、实际来源尝试指标、正负缓存、过期重检、连续三次失败停用、人工启停。人工启用不能批准新适配器或文件权利。
- 适配器：既有 Commons / Archive / Jamendo 保留，新增 ccMixter 官方 JSON；四个实现均满足统一 SourceProvider 协议。新适配器必须经过编译政策审核和有效官方检查。
- 授权：新网站和不明商业录音只作调查。翻唱、混音、传统作品、采样和无法证明完整歌曲范围的候选保留 LICENSE_UNVERIFIED，不请求音频。
- 下载：原生文件身份与格式分离，不转码；沿用严格资格、暂停/恢复、官方大小/校验、SHA-256、媒体解析和证据归档。补充 AAC 解析与 Ogg 容器的 Opus 校验；未宣称所有格式都完成真实下载验证。
- 网络：HTTPS、公共 DNS 固定、私网/保留地址拒绝、不可信重定向拒绝、媒体/可执行响应拒绝、体积限制、超时、取消、有界退避。robots 禁止或无法确认就停止普通页面调查；只对明确官方 API 政策做窄范围接口使用。
- 现有 Song/Recording/Work、人工审核和下载任务模型保留，不增加歌词、播放器、歌单、在线播放或上传功能。

## 中文真实数据

自动发现新调查域名 64，总注册域名 68；其中包含新闻、外链存档及无关结果，不能当作 64 个音乐来源。实际可访问 13，新域名 10 + API 3；正式 API 中文查询 3 个，另 4 个普通页面仅发现表单，未确认音乐搜索能力。

5/30 首返回 7 个任意候选文件；与明确目标版本一致的只有 1 首粤语无伴奏翻唱的 MP3/FLAC 两个文件。4 首 Archive 命中是钢琴翻奏，不是周杰伦原唱。ccMixter 的另一混音保留独立候选。

7 个文件全部授权未验证；通过全部下载资格 0，真实中文下载 **0/30**。无结果 25 首，来源请求失败 0 首。MusicBrainz 歌曲元数据有 3 次查询遭遇真实 503（按查询计，不是 HTTP 503 响应总次数），与“来源失败”分别记录。

首次 30 首实际耗时 2556.02 秒：MusicBrainz 57 请求，来源 169 请求，发现/网页检查 109 请求，初始化官方接口另 3 请求。最后的原生演唱者/版本补测单独记录，不覆盖首轮性能或失败。

上传账号不等于歌手。首轮原生测试曾把 solos_to_use 当作目标身份且未指定 cover，导致两个自身文件误标版本不符。修正依据为官方 featuring 的 Li Yao Ming，明确 cover，再真实请求；两个文件成为 METADATA_MATCH，但传统作品权利仍未解决，下载数仍为 0。原始测试数据全部保留。

同一晴天查询缓存回归：Archive / Commons / ccMixter 命中，HTTP 0，0.5743 秒；发现命中 2 查询，HTTP 0，1.1831 秒。

## 原生 Windows GUI

项目内 Qt 集成脚本在实际 `windows` 平台运行：中文输入事件、Enter 搜索、明确选择歌手、目录显示、真实来源发现、禁用/启用、强制重检、证据历史、取消和退出均通过。新页与原四页共存，实际下载保持关闭。

最终本地周杰伦目录：572 行，MusicBrainz 请求 0，3.3594 秒。UI 心跳 273 次，最大间隔 **1.4099 秒**；说明网络任务未阻止 Qt 持续处理事件，但目录渲染/切页仍有可见的短暂停顿，不宣称完全无卡顿，留待后续性能阶段改善。

系统级 Computer Use 检查尝试过隐藏窗口和可见窗口：原生辅助工具截图持续超时，文本树可读但无法得到可点击几何，系统点击验证没有通过；没有把 Qt 集成测试冒充该项通过。最初 Qt 测试脚本漏选“歌手”模式的身份候选，等待条件不成立，修正为点击明确歌手后重测通过；失败目录保留。

最终截图 `.local/reports/phase3b1/native-release/discovery-native.png` 已查看：中文正常、五页保留、来源/状态/权限/格式及历史可见。测试源码分别为 `scripts/verify_phase3b1_gui.py` 和 `tests/test_discovery_ui.py`。

## 真实音频与格式

| 控制文件 | 实际字节数 | SHA-256 | 结果 |
|---|---:|---|---|
| Silent Night / Kevin MacLeod MP3 | 5,369,410 | 4303f2a73ffd4e872503eb0898f62d7d0b9f1f15c783fcb3495e01c7383b6c00 | 完成；暂停、重新构建管理器、RANGE_ACCEPTED 续传；重复复用 |
| Conillet de Vellut / José Galeote WAV | 24,968,780 | 7cf0414cced10263c76d78af1d094798da82b2ecdaca07e49107910c48ed368a | 完成；原始大小、SHA-1、解析时长与 SHA-256 通过 |

这两首是外语控制，不计中文成功。中文 MP3/FLAC 是真实候选元数据，未通过权限而未下载。其他格式无本轮符合全部条件的中文样本；模拟解析和错误注入只能计作软件测试。

## 数据、文档及隐私

开发前使用 SQLite backup 保存正式库，并记录所有 Recording 原始哈希。迁移与测试后再次对比哈希、审核、确认、下载任务和设置，全部保留。仅将真实公共来源注册表与其调查历史保存到正式库，不将 QA 的录音选择、下载设置、任务或音频导入正式库。

根目录 14 份历史 Markdown/锁定清单迁移到 docs 与 requirements；原 README 另存为 Phase 3B 历史使用说明，没有删除历史报告。检查代码、测试、脚本无旧文档路径依赖，所有本地 Markdown 链接验证存在。新 README 区分真实实现、开发中、未实现，并采用用户指定 Phase 3C–7 后续范围。

`.gitignore` 排除 `.local`、SQLite、token、密钥、音频、会话、缓存与临时文件。当前无 Jamendo、Brave、OAuth 配置；真实音频/数据库不提交。

## 复现实测命令

```powershell
$env:MELODYVAULT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local/pytest-3b1-release --junitxml=.local/reports/phase3b1/pytest-release.xml
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local/runtime --init-db
.\.venv\Scripts\python.exe scripts/validate_phase3b1.py --live --execute-authorized-downloads --report-dir .local/reports/phase3b1/new-coverage
.\.venv\Scripts\python.exe scripts/validate_phase3b_network.py --execute-downloads --report-dir .local/reports/phase3b1/new-control
.\.venv\Scripts\python.exe scripts/verify_phase3b1_gui.py --automated --report-dir .local/reports/phase3b1/new-native
```

使用全新的 QA 输出目录；已有目录拒绝覆盖。机器报告位于 `.local/reports/phase3b1/`，包括 pytest XML、coverage、native-credit-regression、cache-regression、preservation、authorized-control、native-release 及早期失败记录。

## Git 交付

开发前 main 无 HEAD，所有原项目文件均未跟踪；origin 原为空仓库。这是项目首次提交，包含保留的历史代码和本阶段更改；没有强制覆盖已有提交。
目标提交信息：`feat: phase 3b.1 dynamic chinese music source discovery`。
分支 `main`；远程 [yuxiangliu-beginner/MelodyVault](https://github.com/yuxiangliu-beginner/MelodyVault)。提交/推送后实际 SHA、远程核对结果写入本地 `git-result.json` 并在交付回复报告；若推送失败不得声称成功。

## 未解决与下一步

全网 API / Jamendo 未配置；35 个外链站点尚未逐站访问；新站点无编译审核前不运行抓取/下载适配器；中文合法完整录音下载仍为 0；全格式真实中文音频矩阵未完成；系统级窗口捕获失败；目录 UI 短暂停顿；Win11/其他 Python 与 EXE 未验收。
停止等待 Phase 3B.1 验收。上传、歌词、定时任务及 SuiSound 对接仍未开始。
