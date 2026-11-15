# MelodyVault

独立 Windows / Python / PySide6 音乐目录与合法私人归档工具。当前 **Phase 3B.2 开发中，尚未完成验收**；不进入 Phase 3C。

## Phase 3B.2 开发进度

主页面新增“搜索并下载”：歌手或歌曲身份不明确时仍须选择 Recording；已明确目标后，后台调用现有音乐来源、逐文件核验身份和授权，只为核验通过的候选创建下载任务，失败后尝试下一候选。“下载演练”可阻止音频保存；未勾选时点击该按钮表示本次允许下载合格文件，不修改已保存的全局设置或运行其他排队任务。歌手目录可多选已确认歌曲，或展开选择具体录音后执行；不会自动下载整位歌手目录。“本地识别”只限制歌曲身份查询，音源搜索仍需联网。

网易云、Bilibili、抖音目前受限。YouTube 官方 API 元数据适配器已编写并通过模拟测试；当前未配置密钥，即使配置密钥，在官方品牌展示规范完成核验前仍保持受限。界面显示原因。现有 Commons / Archive / ccMixter 复用原引擎与缓存，由统一调度器按来源有界并发查询，结果逐个返回并显示。yt-dlp / FFmpeg / FFprobe 后端和中文授权音频端到端样本尚未完成。不要将平台搜索命中或 dry-run 当作下载成功。

真实控制：英文开放录音从 SQLite 身份搜索、Recording 选择、Commons 搜索、文件级许可核验到 MP3 下载归档成功。30 首中文来源复测：5 首有候选、7 文件均授权未验证、25 首无结果、中文下载 0；详情见 [本阶段覆盖报告](docs/validation/PHASE3B2_COVERAGE_REPORT.md)。

## 已实现并验证

- MusicBrainz 歌手/歌曲/智能搜索、别名与简繁体、Song / Recording / Work、人工审核与撤销、版本展开；同名不自动合并。
- SQLite 优先加载目录，目录与深度 Work 补证分开；HTTP 429/503/超时有界重试，可取消任务。
- Commons / Internet Archive 官方音源搜索；Jamendo 适配器保留，未配置时不请求。
- 动态来源注册表、公开百科外链发现、来源能力与历史、默认待审核、手动启停、失效停用、缓存过期重检。未知网站只作调查。
- 新增 ccMixter 官方 JSON 元数据适配器；在“音源发现”检查官方适配器后启用，逐文件许可和录音身份核验。上传者不当作演唱者。
- 独立下载资格审核、dry-run、暂停/恢复/续传、重试、SHA-256、完整性和格式检查、原始文件归档与旁证。普通下载队列的实际下载默认关闭，一键任务使用单次演练开关；不转码。
- Windows 原生 Qt 流程：保留歌曲目录、音源搜索、下载任务、下载设置，新增音源发现；后台运行、支持取消、关闭等待任务。

## 本轮真实覆盖率

固定 **30 首中文歌曲 / 8 位歌手**，含周杰伦、林俊杰、周传雄、张惠妹、独立音乐和有 CC 声明的粤语翻唱候选。

| 指标 | 实际结果 |
|---|---:|
| 自动新发现调查域名 | 64（包含新闻、存档和无关外链，不能称作 64 个音乐来源） |
| 动态注册表 | 68（另含 4 个预置 API） |
| 实际可访问 | 13（新域名 10 + 官方 API 3） |
| 官方适配器已核验 / 中文查询已测试 | 3：Commons、Archive、ccMixter |
| 有完整文件元数据线索的来源 | 2；与目标版本一致的候选来源为 1 |
| 返回任意音频候选 | 5/30，7 个文件 |
| 已验证下载许可 / 未验证候选 | 0 / 7 |
| 无结果 / 来源查询失败 | 25 / 0；另有 3 次歌曲查询遭遇 MusicBrainz 503 |
| 中文实际下载成功 | **0/30** |

商业及独立中文歌曲的合法下载覆盖率本轮仍为 0。翻奏、翻唱、混音、试听及未经证实的作品权利均不能冒充商业原唱成功。域名发现率和下载率分别计算，详见 [覆盖报告](docs/validation/PHASE3B1_COVERAGE_REPORT.md)。

真实下载控制样本另计：开放授权外语 MP3 / WAV 各一个下载并校验成功，MP3 暂停续传和重复文件复用成功。**不计入中文覆盖率**。中文 FLAC 仅验证真实候选元数据，未下载；M4A/AAC/Ogg/Opus 没有本轮合格中文实测样本。

## 开发中及已知限制

- 来源发现默认仅公开 Wikipedia 官方搜索/外链发现，范围有限；可选 Brave 官方 API 适配器已实现，未配置密钥，未做真实通用全网测试。
- 没有 Jamendo client_id，Jamendo 实测未开展。新的域名均 PENDING_REVIEW；启用网站不会赋予抓取和下载权限。
- 新闻外链、网页提及格式、搜索表单、可播放和下载按钮都不是音乐文件或授权证明。禁止/无法确认自动访问、受限页面、重定向或不安全响应不继续抓取。
- ccMixter 中文样本涉及传统作品翻唱，底层作品权利未核实，保留 LICENSE_UNVERIFIED 和来源链接，不请求音频。
- Windows 原生 Qt 测试通过；系统级 Computer Use 窗口捕获超时，未把系统点击检查标为通过。只有当前 Windows / Python 3.13.2 环境实测，未完成 Win10/11 与 Python 版本矩阵。
- 原始 MP3/FLAC/WAV/M4A/AAC/Ogg/Opus 解析和保存不转码；本轮没有将所有格式都宣称为真实下载测试通过。跨来源预下载内容去重尚未实现。

## 启动（PowerShell）

```powershell
Set-Location E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime --init-db
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
```

新环境使用 Python 3.11+ 创建 `.venv` 后运行 `pip install -e '.[test,browser]'`。精确 Windows 依赖在 [当前依赖快照](requirements/requirements-phase3b1-lock.txt)；先 `pip install -r requirements/requirements-phase3b1-lock.txt`，再 `pip install --no-deps -e .`。SQLite 是标准库。浏览器可选功能需已安装 Chrome，独立 Playwright 会话不依赖 Codex 插件。当前不用 Google 账户。

1. 歌曲目录输入歌手或歌名，选定身份及版本；支持 Enter、取消、清空和本地搜索。
2. 音源发现页输入歌手/歌曲，点击“自动发现新网站”。查看详情、原始链接、能力和历史，按需启停或重新检查；“检查官方适配器”会核验编译的 API 来源。
3. 歌曲可单首/批量搜索音源。未验证授权的候选保留原因，不能直接下载。
4. 下载任务默认 dry-run，仅搜索和审核；READY 不代表文件已下载。确需实际下载时在下载设置明确开启并保存，然后重新建立实际任务、点击开始。旧 dry-run 不自动转为真实下载，重启不自动执行。
5. 只有 COMPLETED 才代表媒体、完整性、校验及本地旁证全部通过；暂停保留临时文件，恢复前再次核验来源与 HTTP 对象。

运行数据默认优先 D 盘；上面的命令显式使用当前项目 `.local/runtime`。下载目录默认项目 `.local/downloads`，可在设置中更改。不修改 SuiSound。

非敏感配置模板为 [config.example.toml](config.example.toml)。可选 API 从环境变量 `JAMENDO_CLIENT_ID` / `BRAVE_SEARCH_API_KEY` 读取；不要将密钥写入代码或提交 Git。数据库、音频、token、浏览器会话、缓存和本地配置均由 `.gitignore` 排除。

## 测试与文档

Phase 3B.2 完整回归 **209 passed，0 skipped**；最后两项小幅修正分别通过定向测试。最新原生响应数据及未完成项见 [本阶段验证报告](docs/validation/PHASE3B2_VALIDATION.md)。所有真实联网结果与模拟错误注入分开记录。

```powershell
$env:MELODYVAULT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest -q
# 真实 30 首测试，必须使用新的隔离目录；通过资格后才可请求音频
.\.venv\Scripts\python.exe scripts/validate_phase3b1.py --live --execute-authorized-downloads --report-dir .local/reports/phase3b1/my-coverage
# 原生 Qt 集成测试；操作本项目的独立 QA 窗口
.\.venv\Scripts\python.exe scripts/verify_phase3b1_gui.py --automated --report-dir .local/reports/phase3b1/my-native
```

- [开发状态与测试日志](docs/development.md)
- [架构](docs/ARCHITECTURE.md) · [来源发现设计](docs/design/SOURCE_DISCOVERY_DESIGN.md)
- [官方来源调查依据](docs/research/PHASE3B1_SOURCE_RESEARCH.md)
- [本阶段验收](docs/validation/PHASE3B1_VALIDATION.md) · [30 首逐来源结果](docs/validation/PHASE3B1_COVERAGE_REPORT.md)
- [Phase 3B 历史使用说明](docs/design/PHASE3B_USER_GUIDE.md) · [历史验证报告](docs/validation/PHASE3B_VALIDATION.md)

根目录历史 Markdown 和依赖清单已迁至 `docs/` 与 `requirements/`，全部保留。

## 尚未实现

| 阶段 | 范围 |
|---|---|
| Phase 3C | Google Drive / 阿里云盘上传、按格式去重 |
| Phase 4 | 歌词片段搜索 |
| Phase 5 | 自动化与定时任务 |
| Phase 6 | 性能优化与 SuiSound 数据对接 |
| Phase 7 | Windows EXE 打包发布 |

每阶段完成后停止等待确认；当前没有播放器、歌单、在线播放或云端上传功能。
