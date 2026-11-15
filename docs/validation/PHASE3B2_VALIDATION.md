# Phase 3B.2 验证记录（进行中）

2026-11-14。当前已实现歌曲选择后的来源搜索、文件级资格核验、限定任务队列和来源回退，但本阶段仍有未完成项，尚未整体验收。

## 真实 A → B → C 控制

输入 **Kevin MacLeod / Silent Night**；统一身份搜索从隔离 SQLite 得到 1 个候选，明确选择 MusicBrainz Recording `56c6eca2-5953-45d2-a7c2-54d6ab5833ef`。现有 Commons 来源查询得到 2 个候选，文件级资格验证通过后，DownloadManager 下载并验证原始 MP3，任务状态 COMPLETED，schema 9 保存会话、来源尝试和文件登记。实际新文件 **5,369,410 字节**，SHA-256 `4303f2a73ffd4e872503eb0898f62d7d0b9f1f15c783fcb3495e01c7383b6c00`；并发来源版 CLI 控制测试耗时 7.07 秒。此前测试副本中的已下载文件登记已清除，确保本次请求真实文件，不修改原 QA 库或正式库。

Windows 原生 Qt 一键界面也对该授权英文录音真实点击搜索并下载，最新运行状态 COMPLETED，截图与机器证据在 `.local/reports/phase3b2/native-final-network/`。记录 195 次 UI 心跳，最大间隔约 0.44 秒；该次界面对唯一可靠本地候选自动进入后续流程。此前一次在受限沙箱内补测因 WinError 10013 网络访问被拒而 FAILED，保留于 `.local/reports/phase3b2/native-final-delivery/`；随后在允许网络访问的环境中重跑成功。另一次中文原生演练人工选择周杰伦《晴天》现场版 Recording `4e7860ff-72d1-408b-8001-ca5558906942`，最终为 NO_SOURCE；该结果不代表录音室版的搜索结果。英文控制样本**不是中文下载成功**。另一原生中文 dry-run 查询周杰伦《晴天》结果 NO_SOURCE，没有创建音频。

另一次原生批量演练在周杰伦目录明确选择 `Ending`、`First Kiss` 两首，分别记录 FAILED 和 SKIPPED；共处理 2 首、实际下载完成 0，没有批量处理整个歌手目录。失败/未授权并未显示为成功。运行证据 `.local/reports/phase3b2/native-batch-layout/`。另一次原生 Qt 点击取消真实后台任务，持久会话为 CANCELLED。

## GD / 网易云接口复核

只读审计 SuiSound 的 GD 聚合实现后，本轮重新读取 [GD API 原始文档](https://music-api.gdstudio.xyz/api.php)：2026-09-16 更新的页面限定学习参考，明确禁止下载、传播及商用，并要求注明来源，限制 5 分钟内不超过 50 次请求。SuiSound 的旧搜索记录不能证明 MelodyVault 的自动化收藏用途符合该范围，也不能证明网易录音的下载许可。因此 GD 聚合搜索保持 RESTRICTED；本轮没有将它作为授权下载源，也没有请求 GD 音频。

## 中文真实测试

30 首、8 位歌手的真实音乐来源查询：5 首有候选、7 个文件全部 LICENSE_UNVERIFIED、25 首无结果、来源失败 0、下载资格通过 0、真实中文下载 0；真实耗时 812.19 秒。网易云、YouTube、Bilibili、抖音均未搜索，不能把未请求写成命中 0。逐首来源结果见 [覆盖报告](PHASE3B2_COVERAGE_REPORT.md)。本次 30 首回归通过既有 SourceSearchEngine 执行，不等于 30 次新版 GUI 一键流程。

## 保护与设计

- 正式库开发前：schema 8、2,055 条 Recording、3 个下载任务、68 个来源、0 条人工审核；已做 SQLite 备份和原始 payload 哈希清单。升级后 schema 9，2,055 条原始 payload 哈希逐条一致，3 个任务、68 个来源、审核、搜索确认及设置逐行不变，integrity_check=ok。
- 追加 schema 9：`pipeline_sessions` 和 `pipeline_source_attempts`；失败及跳过原因逐项写入。迁移保留旧版本 checksum 和原数据。
- `SearchOrchestrator` 为每个音乐来源分别包装现有 SourceSearchEngine，独立执行、复用缓存、限制并发，并逐个汇总结果；共同来源任务在全部返回后持久化。受限或未配置来源不阻塞可用来源。
- 一键默认只在用户点击“搜索并下载”时允许该次任务下载，独立“下载演练”复选框阻止保存；既有全局设置不被修改。只运行明确指定的任务 ID，不触发其他排队任务。
- 候选在创建下载任务前进行独立授权/录音/完整性核验，进入 DownloadManager 后再次核验。失败可切换下一个候选；错误、跳过、取消和完成分别记录。
- 搜索后不自动认定翻唱、钢琴版或同名录音；有歧义时由用户选择。网易云 GD 聚合链没有证明本应用的使用许可，保持 RESTRICTED；YouTube 没有密钥，NOT_CONFIGURED；官方元数据客户端已实现但尚无真实密钥测试，且品牌展示规范未完成核验，即使提供密钥也保持 RESTRICTED。YouTube 结果查看目前禁用；通过后续核验后仅临时分开展示，不进入下载队列、不记录在 SQLite；Bilibili 和抖音为 RESTRICTED。未发请求不计成功。
- 现有本地文件原格式校验沿用；yt-dlp 和 FFmpeg/FFprobe 后端尚未实现，当前环境也未检测到这三个命令或 yt-dlp Python 包，视频提取及相关真实格式测试未通过验收。

## 测试及限制

- 初始回归：192 passed、2 skipped；最新完整回归启用在线测试，**213 passed、0 skipped**，耗时 331.42 秒，JUnit 结果 `.local/reports/phase3b2-delivery-actual.xml`。YouTube 的缺少密钥、错误、取消、内存缓存和启用限制为模拟测试，并非真实 YouTube API 调用。`pip check` 通过。
- 选择性调度、同名/版本保留、未授权不创建下载、隔离用户其他排队任务、真实字节 SHA-256、mock 来源回退及 Qt 用户选择均有定向测试；模拟传输结果不计入真实下载。
- 未完成：四个平台中符合条件的真实搜索验证和 YouTube 品牌展示核验；统一会话自动断点续搜；yt-dlp / FFmpeg；明确授权完整中文音频的 A→B→C；全格式真实验证。
- 异常退出后，下次启动一键任务会在跨进程锁保护下把遗留 `running` 会话标为 `INTERRUPTED`，历史保留；下载队列具有独立恢复。不会自动从搜索断点继续，需要重新启动任务。Windows 原生窗口实际取消测试返回 CANCELLED，未记为下载成功。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts/validate_phase3b2_musicbrainz.py --execute-downloads --report-dir .local/reports/phase3b2/new-control
.\.venv\Scripts\python.exe scripts/verify_phase3b2_gui.py --authorized-english-control --report-dir .local/reports/phase3b2/new-native
.\.venv\Scripts\python.exe scripts/validate_phase3b1.py --live --execute-authorized-downloads --report-dir .local/reports/phase3b2/new-coverage
$env:MELODYVAULT_LIVE='1'
.\.venv\Scripts\python.exe -m pytest -q
```

以上真实测试需要网络和新的隔离输出目录。控制 MP3 来自已有公开授权 QA 样本，不使用用户私人音乐。历史基线、机器结果、数据库副本和音频位于 `.local`，不提交 Git。
