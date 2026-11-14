# MelodyVault

独立 Windows 桌面应用，目标是建立歌手歌曲目录，并在有明确下载与私人保存授权时下载完整音频，上传用户自己的 Google Drive 私人文件夹。

**当前：Phase 3B 多来源下载与本地归档，等待验收。** 输入“歌手名称或歌曲名称”，默认智能识别，可切换歌手/歌曲模式；Enter 搜索，支持取消和清空。裸歌名展示多位歌手和录音版本，手动选择具体目标后连接现有多来源音源搜索。可填写歌手条件修正身份，或勾选“仅本地搜索”（零网络）。不开发歌词、播放器、歌单或在线播放。

已保存歌手直接从 SQLite 显示；首次歌手目录通过 MusicBrainz 按页显示，不等待深度 Work 补证。默认 Song 一行、Recording 可展开，待确认不会因为同名而强制归并。原人工审核和撤销保留。`Jay Chou Qing Tian` 等拼音线索明确待确认，不作为官方英文别名或自动合并证据。界面提供独立的刷新目录、补证和音源搜索；实际下载默认关闭；明确开启后只处理独立审核通过的完整音频。本阶段不上传。

新增“下载任务”“下载设置”页。使用方法：

1. 在目录右键建立单首审核任务，或选择来源后点“加入下载审核”；下载页也可为当前歌曲/整位歌手目录建立任务。歌手沿用已确认的Artist身份，未确认作品/版本会记录原因跳过。
2. 点击“开始任务”。默认 **dry-run**：搜索、核验、READY或SKIPPED，**不会创建音频文件**；READY、许可字段已核实、SKIPPED都不是下载完成。
3. 需要真实下载时，在“下载设置”选择目录、并发、质量偏好、队列总限速和临时文件策略，明确开启实际下载并保存；**重新建立实际任务**后点击开始。旧dry-run不会自动转成下载，开启开关或重启也不会自动执行。
4. 可暂停/继续/取消单首或全部，重试仅针对失败任务。暂停保留`.part`；退出/异常重启后等待手动继续，恢复前重新核验来源和HTTP对象。字节100%还需校验归档，只有COMPLETED代表通过。
5. “查看授权与失败原因”显示来源、录音/版本、许可条件、署名、失败原因、校验值和文件路径；可打开本地下载文件夹。没有播放、歌词、歌单或云端上传页面。

默认目录：`E:\users\yliu\MelodyVault\.local\downloads`。目录可修改；恢复旧任务沿用原目录，新任务使用新设置。保留原始音频、版本和署名旁证，不转码、不覆盖不同文件。存在已核实文件时重新检查后复用或复制到新目录，不用同名作为去重依据。

许可与身份审核独立于来源搜索分数。明确Recording文件URL关系或ISRC等可靠身份、文件完整性、自动下载来源和私人保存许可必须全部通过。Archive/Chrome候选无法核实具体录音权利链时继续保留LICENSE_UNVERIFIED；Jamendo未配置明确跳过。未知、翻奏、试听、错误版本或其他音频不会当作目标原唱下载。

歌曲右键可搜索单首，“音源搜索”页可批量、搜索前5首、仅搜索缺少已核实来源、重试失败/取消项。来源为Internet Archive和Wikimedia Commons官方API；Jamendo适配器需要自己的官方client_id，未配置会明确跳过。候选保存标题、演唱者、时长、版本、匹配依据、许可状态/原因和原始网页。授权无法核验一律 `LICENSE_UNVERIFIED`，仍继续其他来源；不把同名钢琴、翻唱、伴奏或现场录音认定为原曲。

可选Chrome补充公开网页搜索，以及读取所选候选的授权页面。Python Playwright自行启动独立Chrome会话，不连接Codex插件或用户Chrome资料。只访问已核实白名单及robots允许的公开页面，遇验证码/访问控制停止，阻止音频资源，不解析隐藏流。Chrome读取页面不会自动把未核验许可升级成可下载。统计来自实际歌曲队列与来源尝试，不使用计时器模拟进度。

目录、低优先级Work补证、音源搜索和Chrome核验分别在线程中运行，可取消。保存目录默认直接本地读取，手动刷新才更新；MusicBrainz API页面及补证正/负缓存为7天。来源成功候选缓存24小时，无结果缓存6小时，错误可立即重试；查询包含歌手/歌曲身份、已知中英别名、录音集合及版本，元数据变化不会错用旧结果。可分别强制刷新目录、补证、音源缓存。HTTP超时20秒，503/429/超时有限指数退避并遵循较长Retry-After；取消等待当前请求结束，成功来源尝试保留。失败、取消、身份待选择都不假称成功。

采用 **Song → Recording** 两层模型。录音层以 Recording MBID 保存原始数据；歌曲层优先使用相同 Work ID，辅助使用 ISRC、兼容的歌手署名、相同发行组曲目位置和完整再版曲目序列证据。不同 Work ID 禁止合并，未知记录也不能作为跨作品的传递桥梁；多作品串烧独立待确认。标题经过简繁、空格、标点、英文大小写及官方别名规范化，但仅同名/同别名从不触发自动合并。

待确认项自动补查 Recording→Work、Work→Recording、ISRC、发行曲目和官方录音关联/合并重定向；只接受有来源且署名兼容的明确证据。共享 ISRC 若版本信息冲突则不推断；标题相似和时长接近只生成审核建议。补证请求完成点持久化，7天内可恢复复用，显式刷新可重取。

点击“待确认作品审核”查看候选、依据、置信度、Work、演唱者和录音版本。填写理由后可确认合并、拒绝此建议或保持独立；“审计历史与撤销”可撤销决定。人工确认明确区别于官方 Work 核实，绝不伪造 Work ID。撤销不删除原事件；刷新重放人工决定，遇新冲突或依赖被撤销时显示需重审。审核决定和派生分组在同一 SQLite 事务保存。

录音室主版本需要正式非现场发行或明确版本标注，现场/Remix/重新录制版保持各自 Recording；没有证据就不指定主版本。悬停父行可查看归并理由、Work ID 和主版本依据，悬停版本可查看原始名称及 Recording MBID。v3/v4 迁移保留原始 payload，刷新响应另存历史快照，重建歌曲映射不会删除录音。

统计显示原始录音、已核实/人工确认作品、Work核实、重复发行收录、全部版本、待确认和已人工审核数。Phase1补证未降低待确认数量的历史结果见 [PHASE1_VALIDATION.md](../validation/PHASE1_VALIDATION.md)，Phase2不把未知作品强行确认。明确标记视频的录音仅可作关联证据，不进入音频版本目录；正式发行/作品元数据不代表音频下载授权。

## 路径与环境

- 项目：`E:\users\yliu\MelodyVault`，与 SuiSound 完全独立；2026-11-13 按用户要求从 D 盘迁移到当前工作区。
- Python 3.11+；本次实际验证 Python 3.13.2 / Windows，Win10/Win11 双系统矩阵留到 Phase 8。
- 默认数据目录：D 盘存在时 `D:\MelodyVaultData`；否则 `%LOCALAPPDATA%\MelodyVault`。目录无权限时明确报错，不静默换位置。
- 测试和手工运行显式使用项目 `.local`，虚拟环境、pip 缓存、pytest 临时文件、日志和数据库均位于当前 E 盘项目内。产品的默认数据目录策略仍优先 D 盘；使用下列 `--data-dir` 参数可将运行数据保存在当前项目内。
- 当前环境的 `python` 是不可用的 WindowsApps 别名。请使用 `.venv\Scripts\python.exe`，或指定真实 Python 解释器创建虚拟环境。

## 安装与运行（PowerShell）

```powershell
Set-Location E:\users\yliu\MelodyVault
# 如果还没有虚拟环境，请将下面解释器路径换为本机 Python 3.11+ 的真实路径。
& 'C:\Users\yuxiang\AppData\Local\Programs\Python\Python313\python.exe' -m venv .venv
$env:PIP_CACHE_DIR = "$PWD\.local\cache\pip"
$env:TEMP = "$PWD\.local\tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --init-db
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
```

不需要激活虚拟环境，不修改SuiSound；SQLite使用标准库。Phase2浏览器功能请安装 `pip install -e '.[test,browser]'`，并安装官方Google Chrome。运行时Python Playwright自带所需Node，应用不依赖系统Node或Codex浏览器。Google API/OAuth、mutagen、PyInstaller仍留在可选依赖，按后续授权阶段安装；当前不连接Google账户。

`requirements/requirements-phase2-lock.txt` 记录当前Python3.13/Windows的精确依赖（含Playwright）；可先 `pip install -r requirements/requirements-phase2-lock.txt`，再 `pip install --no-deps -e .`。旧Phase0/1清单保留作历史，不代表其他Python或Windows组合已验收。

## 配置

```powershell
Copy-Item config.example.toml config.toml
.\.venv\Scripts\python.exe -m melodyvault --config config.toml
```

优先级：`--data-dir` > `MELODYVAULT_DATA_DIR` > 配置文件 `storage.data_root` > 默认路径。配置文件仅在显式传入 `--config` 时读取，避免工作目录影响配置选择。配置内相对路径按配置所在目录解析。`--version` 无写入副作用。`--init-db` 不启动 Qt。

运行时目录：`database/`、`logs/`、`cache/`、`downloads/`、`credentials/`。旋转日志每份最多约 2 MB、3 份备份，格式化后对常见 token、密码和 Bearer 字段脱敏。脱敏不是记录敏感数据的许可，后续模块仍禁止记录凭据、音乐内容、OAuth 响应正文及授权 URL。Phase 0 尚无 token 存储或加密实现。

## 真实测试

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --init-db
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --smoke
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-tmp --junitxml=.local\reports\pytest.xml
```

pytest 的 GUI 子进程实际创建 PySide6 控件、执行 Qt 事件循环并自动退出，使用 offscreen 平台以便 CI 运行；单独运行 `--smoke` 使用本机桌面平台。数据库测试使用真实临时 SQLite 文件，覆盖幂等初始化、持久化、连接关闭、事务回滚和升级重试、拒绝未来版本与篡改历史。测试不访问外网、不下载音频、不上传文件。

普通测试中的 `tests/catalog_fixtures.py` 仅用于离线边界测试，应用代码不会导入或使用它。真实 API 测试需要显式开启，允许复用已经由官方 API 获取的有效页面缓存：

```powershell
$env:MELODYVAULT_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local\pytest-live-tmp --junitxml=.local\reports\pytest-live.xml
# 与桌面共用服务的真实获取入口（Ctrl+C 可取消）
.\.venv\Scripts\python.exe -m melodyvault.catalog --artist '周杰伦' --data-dir .local\runtime --report .local\reports\jay-chou.json
# 单独补证，不重新获取歌手目录；--refresh可强制忽略证据缓存
.\.venv\Scripts\python.exe -m melodyvault.catalog --artist '周杰伦' --data-dir .local\runtime --evidence-only
```

Windows 原生 Qt 端到端验收工具（使用从未运行过的新 `--data-dir`，保证真实网络请求）：

```powershell
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --data-dir .local\gui-check-new --report .local\reports\gui-check-new.json
# 在线刷新已单独验收后，可仅验证现有真实数据的分层 UI，不重复请求服务端
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --data-dir .local\runtime --report .local\reports\gui-cached.json --allow-cached
# 另一歌手的原生主界面回归
.\.venv\Scripts\python.exe scripts\verify_catalog_gui.py --artist '林俊杰' --data-dir .local\runtime --report .local\reports\jj-gui.json --allow-cached
# 使用新的输出目录；自动复制数据库，审核测试不写正式用户审计
.\.venv\Scripts\python.exe scripts\verify_review_gui.py --database .local\runtime\database\melodyvault.sqlite3 --output .local\reports\review-new
```

该工具启动真正的 Windows 窗口，向自己拥有的 Qt 输入框提交中文、点击搜索，验证 UI 心跳、按钮恢复、歌曲表格、SQLite 和原生截图；不操控其他应用。实际验收数量、错误重试和工具限制见 `docs/development.md`。

Phase2三位歌手真实测试与原生界面工具（会查询官方元数据，不下载音频）：

```powershell
.\.venv\Scripts\python.exe scripts\validate_phase2.py --stage catalog
.\.venv\Scripts\python.exe scripts\validate_phase2.py --stage evidence
.\.venv\Scripts\python.exe scripts\validate_phase2.py --stage sources
.\.venv\Scripts\python.exe scripts\verify_phase2_gui.py --report-dir .local\reports\phase2\native-new
```

真实耗时、请求数、授权已核验/未核验、无结果、失败数量及限制见 [PHASE2_VALIDATION.md](../validation/PHASE2_VALIDATION.md)。现有[Phase1报告](../validation/PHASE1_VALIDATION.md)作为模型与归并历史保留；没有因为进入Phase2就把未核实作品自动确认。

实现依据：[MusicBrainz API 与分页](https://musicbrainz.org/doc/MusicBrainz_API)、[限流和 User-Agent](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)、[OpenCC Python 实现](https://github.com/yichen0831/opencc-python)。

## 合法来源与隐私约束

官方 API 优先，网页自动化只用于明确允许自动访问的页面。公开结果、播放能力和下载按钮均不是授权证据。授权不明、禁止私人保存、非完整音频或来源缺失时必须拒绝下载，找不到合法来源应显示未找到。不得绕过 DRM、付费墙、验证码、地区限制或访问控制，不得从未经授权的聚合站提取隐藏流。

后续 OAuth 只请求 `https://www.googleapis.com/auth/drive.file`，使用应用创建或用户明确选择并授权给应用的文件夹，不申请全盘权限，不创建公开共享。所有网络任务必须可取消、重试、恢复，通过 SQLite 去重并持久化。以上是后续阶段的强制要求，Phase 0 不声称已经实现。

`.gitignore` 排除本地配置、凭据/token、浏览器会话、音乐、缓存、日志与数据库；新凭据格式仍须在提交前检查，不能仅依赖文件名规则。不要把真实音频和凭据用于测试样例。

阶段计划、验收与测试实录见 [development.md](../development.md)，模块边界见 [ARCHITECTURE.md](../ARCHITECTURE.md)。每个阶段完成后停止，等待用户确认再进入下一阶段。


Phase 3A 设计与验收：[UNIFIED_SEARCH_DESIGN.md](UNIFIED_SEARCH_DESIGN.md)、[PHASE3A_VALIDATION.md](../validation/PHASE3A_VALIDATION.md)。可复现实测：

```powershell
.\.venv\Scripts\python.exe scripts\validate_phase3a.py --online --output .local\reports\phase3a\my-online.json
.\.venv\Scripts\python.exe scripts\validate_phase3a.py --output .local\reports\phase3a\my-local.json
# 原生 Windows GUI：使用真实数据库的隔离副本，每次指定未使用过的目录
.\.venv\Scripts\python.exe scripts\verify_phase3a_gui.py --report-dir .local\reports\phase3a\my-native
```


Phase 3B 报告：[PHASE3B_VALIDATION.md](../validation/PHASE3B_VALIDATION.md)、[DOWNLOAD_ENGINE_REPORT.md](DOWNLOAD_ENGINE_REPORT.md)、[DOWNLOAD_SECURITY_REPORT.md](../research/DOWNLOAD_SECURITY_REPORT.md)。真实开放MP3与WAV已从来源查询/核验到归档；三位商业歌手的15首样本可下载目标为0，没有伪造成功。测试音频及QA数据库仅在`.local/reports/phase3b/`，正式设置仍关闭。

真实下载测试脚本必须显式传`--execute-downloads`，并使用新的隔离报告目录；具体命令、测试与模拟区别见验收报告。本轮停在Phase3B，不进入Phase3C。
