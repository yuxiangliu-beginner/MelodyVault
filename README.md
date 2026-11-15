# MelodyVault

MelodyVault 是 Windows 上的个人音乐搜索、下载和媒体整理工具。当前 Phase 3B.5 保留三个页面：**音乐搜索、我的音乐、媒体转换**。

- 搜索 Apple iTunes 歌曲目录和 Wikimedia Commons 具体音频。选择 Commons 文件后，程序核对文件身份及许可，再由现有下载管理器保存原始格式。
- 在“我的音乐”导入自己的 MP3、FLAC、M4A、WAV，可预览、修改歌名与歌手；文件复制到歌手目录，按 SHA-256 去重，原文件不修改。
- 媒体转换支持 MP3 / WAV 输出、本地音视频，以及官方核验为 CC0 的 Commons 远程视频；转换后可选择加入音乐库。MP3 转 WAV 不会恢复丢失的音质。

Phase 3B.5 已通过真实网络和 Qt 点击验证：搜索“是你”，选择 Commons 的“陈正瑆（创作）”原创记录，点击下载后保存原始 Ogg、执行 FFmpeg 完整解码并自动加入“我的音乐”。文件 820,742 字节、153.6697 秒，许可 CC BY-SA 3.0。重复下载复用文件及音乐库记录。搜索结果中的其他同名歌曲仍是独立录音；本次没有验证主流商业歌曲下载。详见 [Phase 3B.5 验收报告](docs/research/PHASE_3B5_CHINESE_VOCAL_DOWNLOAD.md)。

## 启动

```powershell
Set-Location E:\users\yliu\MelodyVault
.\.venv\Scripts\python.exe -m melodyvault --data-dir .local\runtime
```

新环境需 Python 3.11+；安装项目及媒体转换依赖：`pip install -e ".[media]"`。可在右上角设置音乐库目录。软件使用 SQLite 版本 10；旧下载记录不会被移动。当前项目已在迁移前备份，备份和真实测试证据保存在 `.local/reports/phase3b4/`，不提交 Git。

## 已知限制

- 网易云、QQ、酷我、酷狗、咪咕等来源尚未接入可核验允许本软件保存完整文件的授权接口；YouTube 搜索尚未配置密钥。
- 中文原创《是你》已验证，其他候选仍需逐文件核验；真实跨来源换源尚未验证。不绕过付费、DRM、认证或其他访问控制。
- 远程转换目前只支持官方核验为 CC0 的 Commons 文件页和原始文件，不支持任意视频网站。
- 本阶段不包含 Google Drive 上传。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_personal_library.py tests/test_music_platform_ui.py tests/test_app.py tests/test_downloads.py tests/test_database.py tests/test_remote_video.py tests/test_recording_bridge.py tests/test_pipeline_foundation.py
```

[开发日志](docs/development.md) · [架构记录](docs/ARCHITECTURE.md) · [历史 Phase 3B.3 验证](docs/validation/PHASE3B3_VALIDATION.md)

凭据、音频文件、SQLite 数据库和缓存均由 `.gitignore` 排除。
