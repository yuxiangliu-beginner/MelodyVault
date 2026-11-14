# Phase 3A 验证记录

项目：`E:\users\yliu\MelodyVault`。运行环境：Windows 10 build 19045，CPython 3.13.2，PySide6 6.12.0，SQLite 3.45.3，httpx 0.28.1，OpenCC 0.1.7，pypinyin 0.55.0。报告时间使用本机 America/Los_Angeles，实测在 2026-11-13，SQLite UTC 时间可显示次日。

本轮只开发统一歌手/歌曲搜索、身份匹配和 Phase 2 来源连接。不开发歌词、播放、歌单、在线播放、下载或上传，不进入 Phase 3B。实现和测试结果待用户验收，不代表用户已接受。

## 验收口径

- 智能（默认）、歌手、歌曲；Enter、取消、清空和歌手条件修正；同名歧义保留候选，不默认选择歌曲。
- 复用 SQLite、原 Song/Recording/Work、版本及人工审核。保存歌手本地目录零网络；首次目录继续原分页 partial 路径；裸歌名有多歌手在线候选。
- 明确用户选择的 Recording 才接来源搜索，不把 MusicBrainz 匹配当作合法音源或下载成功。版本和缓存边界保留。
- 后台任务、主线程信号接收、generation 防旧结果覆盖，取消/断网/503、查询类型和歌手身份缓存，v1–5 向后兼容。
- 以下在线 API、SQLite、原生 GUI 与 mock/fault-injection 分开记录，不以模拟结果冒充实测。

## 真实 MusicBrainz API

运行 `scripts/validate_phase3a.py --online`，强制忽略统一结果和 HTTP 页面缓存。每个查询后正常重复查询验证零 HTTP；不是用计时器构造的数据。完整候选、MBID、演唱署名及依据保存在 `.local/reports/phase3a/online-release.json`。

| 查询 / 模式 | 歌手候选 | 录音候选（精确标题） | 演唱者数 | 待确认录音 | 在线秒 | GET / 重试 | 重复查询秒 / GET |
|---|---:|---:|---:|---:|---:|---:|---:|
| 周杰伦 / artist | 1 | 0（0） | 0 | 0 | 2.193 | 1 / 0 | 0.009 / 0 |
| 林俊杰 / artist | 1 | 0（0） | 0 | 0 | 7.786 | 3 / 2 | 0.012 / 0 |
| 周传雄 / artist | 1 | 0（0） | 0 | 0 | 1.959 | 1 / 0 | 0.011 / 0 |
| 晴天 / song | 0 | 52（26） | 42 | 50 | 2.355 | 1 / 0 | 0.017 / 0 |
| 江南 / song | 0 | 52（14） | 42 | 50 | 1.419 | 1 / 0 | 0.019 / 0 |
| 周杰伦 晴天 / smart | 1 | 8（7） | 1 | 6 | 8.999 | 2 / 0 | 0.017 / 0 |
| 林俊杰 江南 / smart | 1 | 6（4） | 1 | 4 | 1.490 | 2 / 0 | 0.016 / 0 |
| Jay Chou Qing Tian / smart | 1 | 7（0） | 1 | 7 | 4.051 | 3 / 1 | 0.014 / 0 |
| 不存在的歌手 / artist | 0 | 0（0） | 0 | 0 | 5.354 | 1 / 0 | 0.012 / 0 |
| 不存在的歌曲 / song | 0 | 0（0） | 0 | 0 | 0.955 | 1 / 0 | 0.017 / 0 |
| MelodyVaultNoSuchArtist82D57F20261113 / artist | 0 | 0（0） | 0 | 0 | 0.969 | 1 / 0 | 0.012 / 0 |
| MelodyVaultNoSuchSong82D57F20261113 / song | 0 | 0（0） | 0 | 0 | 0.782 | 1 / 0 | 0.013 / 0 |

三位歌手精确身份分别为：

- 周杰伦：`a223958d-5c56-4b2c-a30a-87e357bc121b`。
- 林俊杰：`e5d8c705-8ea4-4820-b11d-fbf580d85ce4`。
- 周传雄：`27c24ef3-a0c6-41d3-b704-21bbe769e744`。

本轮三个指定歌手均命中预期身份（3/3 测例），不是针对任意歌手的准确率估计。裸“晴天”“江南”各返回 52 个按歌手+录音区分的候选、42 个不同演唱者身份，保留不同作品与版本；52 包含本地补充项和单条 Recording 的多个署名，不是 52 首已确认独立歌曲。API Recording 上限 50，返回可能包括索引相关结果；“精确标题”仅指规范化名称匹配，不能证明原唱、同一作品或版权。

“周杰伦 晴天”“林俊杰 江南”的歌曲候选均约束到指定歌手 MBID，保留多个版本。`Jay Chou Qing Tian` 的官方英文标题检索本身未给出可靠命中；返回的是本地 7 条普通话拼音弱线索，**7 条全部待确认，0 条官方英文别名确认**。不能把此项写成官方英文别名完全匹配成功。最初未实现弱拼音时确实为 0（`online-real.json`），后续改为明确显示弱候选；原失败记录保留。

字面“不存在的歌手/歌曲”和额外唯一测试字符串均真实返回空结果，不创建模拟歌手/歌曲。空结果仅限这次官方索引/条件，不宣称全网不存在。

本表真实 GET 合计 18 次，包含 3 次自然发生的 HTTP 503 重试，所有查询最终无错误；重复查询全部 0 GET。429/超时/断网由故障注入覆盖，本轮不宣称线上实际发生 429。原有两项真实目录集成最终使用有效官方页面缓存：周杰伦 710 录音/20 页面命中、林俊杰 443/12 页面命中，均 0 GET；与本表强制联网分开。

## 真实 SQLite 本地检索

`local-release.json` 通过 `SearchRequest.local_only=True` 实际读取现有数据库，12 个条件全部 0 GET。本地只存三位歌手，不把其覆盖范围伪装为在线全库。

| 查询 | 本地录音候选 | 本地秒 | GET |
|---|---:|---:|---:|
| 周杰伦 | 0 | 0.012 | 0 |
| 林俊杰 | 0 | 0.007 | 0 |
| 周传雄 | 0 | 0.008 | 0 |
| 晴天 | 7 | 0.011 | 0 |
| 江南 | 4 | 0.010 | 0 |
| 周杰伦 晴天 | 7 | 0.013 | 0 |
| 林俊杰 江南 | 4 | 0.011 | 0 |
| Jay Chou Qing Tian | 7 | 0.010 | 0 |
| 不存在的歌手 | 0 | 0.007 | 0 |
| 不存在的歌曲 | 0 | 0.010 | 0 |
| MelodyVaultNoSuchArtist82D57F20261113 | 0 | 0.006 | 0 |
| MelodyVaultNoSuchSong82D57F20261113 | 0 | 0.010 | 0 |

上述为后台服务耗时，不含进程启动及 UI 控件渲染。缓存目录原生显示耗时另列。

## Windows 原生 GUI

最终原生复验 **13 项记录通过**。使用 `QT_QPA_PLATFORM=windows`、实际 QApplication/Qt 事件循环、QInputMethodEvent 中文输入、Enter 与 QTest 原生控件点击；不是 offscreen 截图或 fixture provider。数据库通过 SQLite backup 复制到独立 QA 目录，QA 的目标选择不写入正式用户数据库。详细结果、单录音来源统计及截图记录在 `.local/reports/phase3a/native-accepted/`，初轮在 `native-release/`。

| 实际输入 / 模式 | 窗口点击至显示秒 | 观察 |
|---|---:|---|
| 周杰伦 / smart | 3.172 | 完整目录 710 录音，API 0 |
| 林俊杰 / smart | 0.879 | 完整目录 443 录音，API 0 |
| 周传雄 / smart | 0.728 | 完整目录 368 录音，API 0 |
| 晴天 / song | 0.771 | 52 个录音候选，API 0，42 位演唱者 |
| 江南 / song | 0.762 | 52 个录音候选，API 0，42 位演唱者 |
| 周杰伦 / artist | 0.914 | 完整目录 710 录音，API 0 |
| 晴天 / smart | 3.981 | 52 个录音候选，API 2，42 位演唱者 |
| 周杰伦 晴天 / smart | 0.256 | 7 个录音候选，API 0 |
| Jay Chou Qing Tian / smart | 0.470 | 7 个录音候选，API 0，待确认 7 |

首个歌手耗时包含失效索引重建、控件渲染和并行测试 IO 负载；不能用后台服务 0.01 秒替代 GUI 耗时。裸“晴天”智能模式真实显示 1 个相关歌手候选（“晴天ひ”，明确不是精确歌手名称）和 52 个歌曲录音候选，保留两类结果、无预选歌曲。默认 1040×720 截图已查看，中文、三个模式、候选/证据、确认/联网按钮可见，状态栏已清除上一位歌手统计。没有专辑列表或播放控件。

明确点击周杰伦“晴天”录音室候选 `729c6839-a400-41aa-aeb1-dfe657dc8be2` 后只向来源任务传递这条 Recording；真实 Archive/Commons 查询 6 GET / 6.113 秒。许可统计：**已验证 0、未验证 1、无结果歌曲 0、失败歌曲 0**，不是找到可下载原曲。候选来自 Archive 钢琴合集，`VERSION_MISMATCH` + `LICENSE_UNVERIFIED`，原因“未提供可识别的明确录音许可 URL；公开可播放不是授权”，原始页面 `https://archive.org/details/jay-chou-piano-40`；未请求音频。Jamendo 明确未配置。

重复点击同一录音复用 Archive/Commons 来源缓存，0 GET / 0.873 秒。查询别名/版本不同会产生不同来源指纹，不冒充这一缓存命中。网络搜索强制刷新后实际发出 1 次 GET，再点击取消，任务总耗时 1.049 秒后结束，取消状态可见；已有歌曲、原始 payload、Song 分组及审核事件逐行一致。清空后输入/结果均清空，保存数据仍在；QA 新增 2 条目标选择审计只在 QA 副本。

事件循环实际心跳 1129 次、最大间隔 0.405 秒，计时只用于观测响应，不生成搜索进度。

## pytest 与故障注入

初次新增领域测试有 2 项失败：mock 使用带空格的未知字符串却断言只有一次请求，忽略了歌手前缀查证；修正该断言隔离方式，并新增“完整多词歌名优先”测试。原 `pytest-search.xml` 保留，未删除失败记录。后续领域 13 passed / 22.907 秒、界面 5 passed / 14.122 秒。全量第一轮 **113 passed / 208.32 秒**，包含原有 95 项回归及新增 18 项。缓存词边界保护和界面状态文案调整后的最终全量 **113 passed / 254.72 秒**，0 failures / errors / skipped，见 `pytest-accepted.xml`。

新增测试覆盖：简繁/标点/大小写、同名不同演唱者和作品、不同录音版本、合作署名、本地零网络、弱拼音、显式未知歌手 MBID 不泄漏其他歌手、裸标题先显示本地再补查、断网保留本地且不存空缓存、503 退避、取消响应、索引随人工重分组失效、已有审核和原始记录保护、新录音不改变人工审核组、错误演唱者拒绝、三个模式/Enter/清空、主线程回调、即使不遵守取消的旧 worker 也不能覆盖新查询、确认单版本后来源查询和缓存复用。429/超时/取消退避、数据库迁移、人工审核撤销、许可和来源错误隔离沿用原回归测试。

普通领域测试采用真实临时 SQLite + httpx.MockTransport；UI 边界使用真实 Qt 控件和假来源/旧 worker。全量中 `MELODYVAULT_LIVE=1` 的两项原目录集成使用真实 MusicBrainz 数据及有效 API 缓存，不能与上表强制联网混为一谈。

`pip check` 通过。更新 editable 安装元数据时，首次尝试 `--no-build-isolation` 因虚拟环境未安装 setuptools 失败；改回项目声明的隔离构建后安装成功，新增 pypinyin 已在项目元数据与锁文件中记录。没有为修复构建升级现有运行依赖。

## 数据与范围保护

开发前备份 `before-phase3a.sqlite3` 及 `baseline-hashes.json`。`preservation.json` 验证全部 **1520** 条原始 Recording SHA-256 完全相同；v1–5 迁移 checksum 未变，追加 schema v6；SQLite integrity_check=ok、foreign_key_check 无错误。正式人工审核事件原 0 / 现 0，正式目标选择事件 0，QA 确认只在隔离副本。人工审核存在时的保留/冲突由临时真实数据库测试覆盖，不伪造用户审核。

`downloads/__init__.py`、`cloud/__init__.py` 与迁移前文件哈希一致；SuiSound 未修改。来源模块只增加已确认用户查询别名向 SourceQuery 的传递，不更改许可、下载或云端规划。运行数据库、token、音频和虚拟环境路径经 git check-ignore 确认排除。

## 未解决问题与实际限制

- 英文音译不是官方别名；拼音可能多音/同音，不能自动确定歌曲。未知 Work/版本继续待确认，本轮没有放宽归并阈值。
- 不提供全标注数据集上的准确率；测试只证明上述指定身份、隔离和不强选行为。相关候选中仍可能包含翻唱/未知版本，必须用户核对。
- Recording 搜索每次最多 50 条、歌手发现最多 25；需细化条件，歌手完整目录仍走分页任务。简繁和本地别名可以匹配，但不保证所有 MusicBrainz 英文索引别名均完整。
- 真实 503 造成耗时波动；取消不能强行终止已发出的同步 HTTP，等待响应或读取超时。应用内共享限速，多个独立进程不共享限速器。
- Jamendo 仍未配置；开放库没有找到已核实目标原唱音源。授权待确认不会阻断任务，但也不允许下载。
- 只在上述 Windows 10/Python 3.13 环境验证；Windows 11、Python 3.11/3.12、独立 exe 未验收。

## 复现命令

```powershell
cd E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m pip install --no-deps -e . --cache-dir .local\cache\pip
.\.venv\Scripts\python.exe -m pip check
$env:MELODYVAULT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-3a-accepted --junitxml=.local\reports\phase3a\pytest-accepted.xml
.\.venv\Scripts\python.exe scripts\validate_phase3a.py --online --output .local\reports\phase3a\online-release.json
.\.venv\Scripts\python.exe scripts\validate_phase3a.py --output .local\reports\phase3a\local-release.json
# 每次原生测试指定新目录，拒绝覆盖已有 QA 数据库
.\.venv\Scripts\python.exe scripts\verify_phase3a_gui.py --report-dir .local\reports\phase3a\native-my-run
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
```

最终正常程序已启动：进程 23868，窗口 MelodyVault、Responding=True，使用正式 `.local/runtime`，启动记录 `app-launch.json`。普通沙箱读不到桌面标题，已在桌面权限下复查。没有自动网络任务。

当前停止等待用户验收；不自动进入 Phase 3B。
