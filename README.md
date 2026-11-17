# MelodyVault

MelodyVault 是 Windows 上的个人音乐搜索、下载和媒体整理工具。当前 Phase 3B.5 保留三个页面：**音乐搜索、我的音乐、媒体转换**。

> **项目状态：因版权问题，不再进行下一步开发。**
> 主流华语歌曲的版权由各音乐平台授权，只能在其 App 内播放或以加密格式下载；经调查，没有合法、免登录的完整文件下载来源。能补齐主流歌曲的只有盗版资源站或绕过平台限制的第三方解析接口，接入它们会构成侵权，因此本项目停在现有功能：Commons / Internet Archive 搜索与下载、本地音乐导入整理、媒体转换。现有功能保持可用，不再新增音乐来源。

- **搜索**（Wikimedia Commons + Internet Archive，只列出能下载的具体文件；已移除只有目录、无法下载的 iTunes）：简繁体同查；Archive 先匹配标题/歌手字段、再以全文补足，每个词须出现在曲目自身信息或条目署名中；修复 GBK 乱码标签；同一首歌优先原始文件，其次 FLAC、MP3；Commons 过滤维基百科朗读录音和与关键词无关的文件。
- **完整下载**：只保存官方原始完整文件，核对大小、官方校验值并用 FFmpeg 完整解码；试听片段被拒绝。没有时长元数据的旧 Archive 上传，以下载后实测时长入库。无需登录。
- **自动换源**（设置中“自动换源”，默认开）：所选文件下载失败时，在 Archive/Commons 中查找同一首歌的其他上传；仅当歌名、歌手、版本一致且时长相差不超过 2 秒才替换。
- **我的音乐**：按歌手分目录，保存歌名、歌手、专辑（Archive 条目名）、时长、格式；SHA-256 去重；同名不同内容的文件另存为“歌名 (2)”，从不覆盖。也可导入自己的 MP3、FLAC、M4A、WAV，修改歌名与歌手。
- **媒体转换**：本地音视频，或粘贴 Commons 视频页/原始文件、archive.org/details/… 或 /download/… 视频网址，提取为 MP3 / WAV 并可加入音乐库。远程视频核对官方大小与校验值；MP3 转 WAV 不会恢复丢失的音质。
- **许可检查默认关闭**：“设置 → 只下载许可已核验的文件”勾选后恢复逐文件许可核验（此时 Archive 音频与视频一律不下载，Commons 视频只接受 CC0）。关闭时证据文件记录“许可未核验”；地址安全、完整性、解码检查及来源自身的访问限制始终生效。

Phase 3B.5 已通过真实网络和 Qt 点击验证：搜索“是你”，选择 Commons 的“陈正瑆（创作）”原创记录，点击下载后保存原始 Ogg、执行 FFmpeg 完整解码并自动加入“我的音乐”。文件 820,742 字节、153.6697 秒，许可 CC BY-SA 3.0。重复下载复用文件及音乐库记录。搜索结果中的其他同名歌曲仍是独立录音；本次没有验证主流商业歌曲下载。详见 [Phase 3B.5 验收报告](docs/research/PHASE_3B5_CHINESE_VOCAL_DOWNLOAD.md)。

## 启动

```powershell
Set-Location E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
```

新环境需 Python 3.11+；安装项目及媒体转换依赖：`pip install -e ".[media]"`。可在右上角设置音乐库目录。软件使用 SQLite 版本 10；旧下载记录不会被移动。当前项目已在迁移前备份，备份和真实测试证据保存在 `.local/reports/phase3b4/`，不提交 Git。

## 已知限制

- 网易云、QQ、酷我、酷狗、咪咕等来源尚未接入可核验允许本软件保存完整文件的授权接口；YouTube 搜索尚未配置密钥。
- 不绕过付费、DRM、认证或其他访问控制。自动换源已用模拟故障（所选文件被删除）在完整下载流程中验证；真实网络中尚未遇到自然失败的来源，未做真实换源演示。换源依据是歌名/歌手/版本/时长，不是 ISRC，仍可能把同名同长的不同录音视为同一首。
- Archive 上主流中文歌曲有限且多为网友上传、授权未知（2026-11-16 实测：“周杰伦”31 条、“邓丽君”41 条、“周杰伦 七里香”只有钢琴版）。Archive 标记为受限、私有或禁止下载的条目不会下载。已真实下载并入库梅兰芳 1931 年《霸王别姬》（公有领域标记，4,018,340 字节，MD5 一致，完整解码通过，专辑名入库），并真实下载一段公有领域 Archive 视频、提取 165 秒 MP3。
- 一次搜索约 12–16 秒：Archive 需逐个读取最多 10 个条目的文件列表，且每个请求间隔 1.1 秒。
- 来源审核记录 7 天后过期；下载前会自动对快过期的 Commons/Archive 重新做一次官方 API 检查（用户手动禁用的来源不会被重新启用）。
- 远程视频只支持 Commons 和 Internet Archive，不支持其他视频网站。
- 本阶段不包含 Google Drive 上传。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_personal_library.py tests/test_music_platform_ui.py tests/test_app.py tests/test_downloads.py tests/test_database.py tests/test_remote_video.py tests/test_recording_bridge.py tests/test_pipeline_foundation.py
```

[开发日志](docs/development.md) · [架构记录](docs/ARCHITECTURE.md) · [历史 Phase 3B.3 验证](docs/validation/PHASE3B3_VALIDATION.md)

凭据、音频文件、SQLite 数据库和缓存均由 `.gitignore` 排除。
