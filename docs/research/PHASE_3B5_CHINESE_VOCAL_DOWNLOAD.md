# Phase 3B.5 — 中文人声下载、解码与自动入库

日期：2026-11-15，America/Los_Angeles。起始 commit `76a002a`；Windows 10 19045，Python 3.13.2，现有虚拟环境、httpx/PySide6/mutagen/imageio-ffmpeg；没有安装新依赖。具体起止时刻见隔离目录 `.local/reports/phase-3b5/phase-a.json`、`gui-final/validation.json` 和 `protection-final.json`。

**主要产品流程已通过：1 首新的中文原创作品《是你》从真实网络下载，原始 Ogg 文件通过完整解码并经正式下载、个人音乐库代码自动入库。** 桌面验收采用真实 Qt 窗口与点击、正式 provider、实际网络及独立数据库；没有替换网络传输或注入搜索歌曲。没有声称人工桌面点击或人工听审，也未把测试记录写入用户正式库。

## A：现有项目检查

起始工作区干净。审阅 Phase 3B.4 报告、Commons provider、PlatformSearchService、MusicTask、DownloadManager、文件核验、DownloadRepository 和 `library/imports.py`。已有 Commons 通用搜索和原生文件 ID 核验能够找到并下载开放文件；发现缺口是下载完成只登记 downloaded_files/任务，未登记 personal_music，且发布前仅检查哈希/媒体解析，没有运行完整 FFmpeg 解码。

正式库只读审计：schema 10，catalog_recordings 2,055，download_jobs 3，discovered_sources 68，personal_music 0，integrity_check `ok`。逐表计数与 Recording 内容摘要保存在 `phase-a.json`。新建隔离研究目录及独立 QA 数据库；没有清库、迁移或覆盖用户文件。

## B–C：从作品反向建立候选

使用 Commons 官方 API 做 9 个有界目录查询及少量定点文件查询。完整响应在 `commons-search-*.json`、`commons-extra-*.json`、`five-candidates.json`、`original-candidates.json`。最初临时脚本直接 JSON 解析报错，没有将它记成无结果；随后复用已有 SourceHTTP 正常获得官方 JSON。没有重做 12 站调查。

初查的商业翻唱《忽然之间》《心酸》虽上传者给出录音 CC 标识，但词曲权利缺少足够依据，未下载；《Pingtan Treasure》作者自己表示只是现场短段录音、表演者不明，未用作完整作品。历史公有领域录音需分别核对司法辖区及录音/作品权利，未为赶进度扩大下载白名单。钢琴作品全部排除。另调查作者发布的“开源人之歌”项目（完整录音为视频，未作为本次下载目标）；另一原创项目公开页面返回 404，未宣称可用。Commons 已发现合格作品，因此没有继续扩大到 Archive 的新平台接入。

沿[作者公开作品目录](https://zh.wikipedia.org/wiki/User:Czxttkl#作品)定点核实 6 个真实文件。该页面列出作品演唱者；Commons 文件页注明原创来源与 CC BY-SA 3.0。下表时长为**官方文件元数据**，只有《是你》另经实际下载测量。

| 作品 | Commons page ID | 官方时长（秒） | 录音许可 | 作者/演唱证据 | 实际下载验证 |
|---|---|---|---|---|---|
| [是你](https://commons.wikimedia.org/wiki/File:是你.ogg) | 15326761 | 153.669660 | CC BY-SA 3.0，自有作品 | 创作陈正瑆；作者作品表列陈正瑆演唱 | **通过** |
| [曾相信](https://commons.wikimedia.org/wiki/File:曾相信.ogg) | 15326719 | 245.458141 | 同上 | 创作陈正瑆；作者作品表列陈正瑆演唱 | 未下载，待逐文件验收 |
| [南边](https://commons.wikimedia.org/wiki/File:南边.ogg) | 15326750 | 166.185215 | 同上 | 创作陈正瑆；作者作品表列陈正瑆、王少杰演唱 | 未下载，待逐文件验收 |
| [黑色rap](https://commons.wikimedia.org/wiki/File:黑色rap.ogg) | 15326793 | 296.309841 | 同上 | 创作陈正瑆；作者作品表列陈正瑆演唱 | 未下载，待逐文件验收 |
| [爱情在怀念中继续](https://commons.wikimedia.org/wiki/File:爱情在怀念中继续.ogg) | 15326815 | 100.054785 | 同上 | 创作陈正瑆；作者作品表列陈正瑆演唱 | 未下载，待逐文件验收 |
| [一个人止血](https://commons.wikimedia.org/wiki/File:一个人止血.ogg) | 20846888 | 135.000816 | 同上 | 自有作品；作者作品表列陈正瑆演唱 | 未下载，待逐文件验收 |

逐项结构化资料见 `candidate-list.json`：页面、ID、格式、标示时长、文件许可、署名、商业与再分发条件、核验限制均有记录。6 项是候选数，**不是 6 首下载成功**。元数据请求无需登录；仅《是你》的音频免登录路径已实际验证，其余未逐文件发起音频请求。

| 来源 | 中文人声证据 | 免登录 | 下载许可 | 真实下载 | 正式接入 |
|---|---|---|---|---|---|
| Wikimedia Commons | 原创文件说明＋作者作品演唱表及华语作品说明 | API/选中音频均未携带账号、Cookie 或密钥 | 具体录音 CC BY-SA 3.0 | 《是你》成功 | 复用既有 provider，扩展后续验证/入库链路 |
| 作者公开作品页 | 提供演唱者及作品关联 | 公开可读 | 本轮以 Commons 文件页许可为准 | 未另下载 | 不作为新的下载 provider |
| 作者“开源人之歌”仓库 | 中文原创演唱项目说明 | 公开资料可读 | 项目提供 CC BY-SA 4.0 | 未下载视频 | 不新增 provider |

中文人声判定依据是文件原作者的作品表明确列出演唱者，以及其作品说明中的华语曲风和原创录音声明，不是仅依据文件名或“非器乐”标签。本轮没有人工听审；从实际下载文件导出 35–47 秒片段尝试 Windows 中文离线识别，仅得置信度约 0.004 的单词结果，**不把该结果当作可靠语种/歌词证据**。作者来源声明满足本轮“作者明确标示人声演唱”的条件；如要求独立人工听审，仍需补做。来源没有 AI 生成标记，未作技术性 AI 排除判断。

## D：真实文件下载与许可

| 歌曲 | 作者／来源声明演唱者 | 来源 | 实际格式 | 字节数 | 实测时长 | 校验 |
|---|---|---|---|---|---|---|
| 是你 | 陈正瑆（Czxttkl） | Commons，page 15326761 | Ogg Vorbis | 820,742 | 153.669659864 秒 | 官方 SHA-1/字节数一致，SHA-256 已计算，FFmpeg 全解码通过 |

SHA-256：`e5f0040a89437667cb8c74428a8a6a9ae26814ebd17b215c59a2f167fc999d3c`。

下载地址由官方 `imageinfo.url` 获取，保存官方完整原始文件，没有从播放器提取隐藏流、转码、剪辑或重复拼接。下载器执行公开 HTTPS、TLS 证书核验、公共地址检查、连接/读取超时、有限重试、体积上限、临时文件、官方哈希/字节/时长检查；最终 GUI 验收文件在 FFmpeg 成功后才原子发布。没有使用旧《卿雲歌》器乐文件或生成测试音频替代。

许可记录：[具体录音文件页](https://commons.wikimedia.org/wiki/File:是你.ogg)、[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)、原作者页面自有作品声明。允许私人保存、商业使用和再分发，但需署名、附许可并说明修改；改编作品的再分发须遵守相同方式共享要求。下载不等于无条件再分发。录音与词曲原创依据来自该文件“创作”说明及作者自有作品声明，并非只依据转载下载按钮。

文件旁附 `.evidence.json` 保存作者、许可 URL、原始 API 元数据、录音身份、校验和及原始字节未修改的记录，数据库同时保留来源证据。没有把文档许可自动套给音频。

## E–F：正式程序改动

- `downloads/files.py` 增加有时限、可取消的 FFmpeg 全解码；找不到解码器或解码失败则拒绝发布。沿用已有 FFmpeg／imageio-ffmpeg，不新装框架。
- `downloads/manager.py` 在新下载及复用文件发布前执行完整解码。原有 SHA-256、官方哈希、格式、时长、冲突与原子发布逻辑保留。
- `library/imports.py` 增加已核验下载的原地登记服务，支持下载器已有原始格式（包括 Ogg），不再复制一次文件。`DownloadRepository.register_file()` 在同一 SQLite 事务内登记 downloaded_files、personal_music 和完成状态；失败不显示入库成功。
- 重复 SHA-256 复用音乐库 ID，保留用户改过的标题/歌手，不覆盖已有文件。来源/许可留在下载证据及旁附文件，schema 10 不变。
- Commons 搜索在有明确“创作：姓名”资料而缺 Performer 时显示“姓名（创作）”。不把上传者默认当歌手；本例虽有研究确认的演唱者，通用程序仍谨慎保留创作角色。未写死任何测试歌名或 ID 到正式应用。
- GUI 保持三个页面和四列；成功提示自动入库，新歌手组展开显示歌曲，已折叠的旧组继续折叠。已经入库的下载不再显示重复历史行；解码/校验/许可错误提供中文提示。

## G：真实 Qt GUI 验收

执行命令：

```powershell
.\.venv\Scripts\python.exe scripts/validate_phase3b5_gui.py --run-live --directory .local/reports/phase-3b5/gui-final
```

实际显示 `MusicWindow`，输入“是你”、点击搜索，返回 34 条真实结果（Apple 与 Commons）；选择 Commons page ID 15326761，点击下载，再切换“我的音乐”确认歌曲及文件路径。不同歌手的同名 Apple 条目保持独立，不当作该开放录音。

最终运行：搜索 1.146 秒；下载、文件核验、完整解码及入库 5.355 秒；重复点击核验/复用 3.121 秒。时长来自实际计时，非模拟进度。

最终文件（项目内相对路径）：

`.local/reports/phase-3b5/gui-final/music/陈正瑆(创作)/陈正瑆(创作) - 是你.ogg`

音乐库 ID：`1088dbdd-915a-488a-af62-efdeb71c893b`。原始研究下载位于 `.local/reports/phase-3b5/downloads/未知歌手/未知歌手 - 是你.ogg`，用于确认来源后再开发，未自动冒称已入库；最终 GUI 是独立真实下载，SHA-256 与原始研究文件相同。两个目录的重复文件属于隔离验收运行，不能累计为不同成功歌曲。

`gui-final/validation.json` 证明：两次下载操作完成、只有 1 个实际音频文件、1 条 downloaded_files、1 条 personal_music、相同 library_id，第二次 `reused=true`。旁附许可文件存在；“我的音乐”歌曲行展开可见。`search.png` 和 `library.png` 是 Qt 实际窗口截图，已视觉检查。

这是**真实网络＋Qt 自动化**；不是 mock 传输，不是人工桌面点击。测试使用正式代码路径和独立数据库；用户正式库没有新增测试歌曲。用户正常启动后可使用同样搜索/下载流程，正式库 Commons 来源审批状态已只读确认允许使用。

## H–I：换源、错误处理与回归

没有两个不同且合格的同录音来源，因此真实跨站换源 `NOT_TESTED`。不把 Commons 存储域或同名其他歌手当作备用源。既有换源模拟故障回归通过。

开发回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_download_library.py tests/test_downloads.py tests/test_pipeline_foundation.py tests/test_music_platform_ui.py tests/test_personal_library.py -q --basetemp=.local/pytest-phase3b5
```

实际 **75 passed in 107.15s**。包括下载/取消/失败、无效许可、身份冲突、非音频/截断/校验拒绝、实际 FFmpeg 进程检查、自动入库、重复下载保留人工编辑、Apple/Commons 服务和个人音乐库基础回归。单元测试用合成 WAV 与明确 mock HTTP，和真实 GUI 下载分开统计。

最终修正新歌手组展开后，只重跑受影响 UI 测试：**6 passed in 3.36s**，并再次完成上述真实网络 Qt 验收。不是 81 个不同测试；同一 UI 测试重复执行不能累加。没有运行全历史网络覆盖或完整项目 pytest。

## 数据保护与验收结论

`protection-final.json`：正式 schema 10；所有业务表计数与起始一致；2,055 Recording 的内容摘要一致；3 个旧下载任务、68 条来源、0 条正式 personal_music 均未改变；integrity_check `ok`。未修改 SuiSound、用户音乐文件或云端功能。测试音频、旁附证据、个人数据库、原始 API 响应及截图均在忽略目录，不能提交 Git。

修改文件：README、development.md、本文、downloads/files.py、downloads/manager.py、database/downloads.py、library/imports.py、search/platforms.py、ui/music_window.py、test_download_library.py、test_music_platform_ui.py 及独立真实 Qt 验证脚本。结束代码以本报告对应 Git 提交为准。

主要验收通过：1 首按作者来源确认为中文演唱的开放原创录音，真实免登录下载、精确原始字节、FFmpeg 全解码、SHA-256、正式下载/个人音乐库流程、真实 Qt 展示及去重均验证。限制：未人工听审，其他 5 首尚未独立下载验收，主流商业歌曲能力未新增，真实跨站换源未验证。保留这些限制，不进入 Phase 3C。
