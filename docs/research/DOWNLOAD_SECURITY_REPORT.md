# Phase 3B 下载安全与范围报告

本报告对应实际代码、故障注入、真实公共音频及Windows原生测试，不把通过测试解释为任意来源或版权的保证。正式数据库默认实际下载关闭，启动不自动处理未完成队列。

## 允许下载的边界

| 来源 | 搜索 | 下载资格 |
|---|---|---|
| Wikimedia Commons | 官方API及已有公开页检查 | 文件级许可、署名、限制检查 + 可靠Recording关联 + 完整文件证据 + 原始文件URL |
| Internet Archive | 官方搜索、metadata、已有Chrome公开检查 | 当前无法核实上传者对具体录音的权利链；保持LICENSE_UNVERIFIED，不能自动下载 |
| Jamendo | 配置自己的官方client_id才启用 | 最新允许下载标志、CC条件、目标身份及受限下载域名必须同时通过；本轮未配置/未实网验收 |
| Chrome页面候选 | 仅沿用允许页面/robots边界 | 页面、播放控件或Free Download按钮均不能批准下载；不提取隐藏流 |

下载许可与用户目标选择分别存储。用户点击“确认歌曲”、同名、高元数据分数、时长接近、免费收听或能公开访问都不批准保存。已知翻奏/Live/Remix/伴奏差异拒绝；缺少Work不直接判重复，但批量自动下载要求明确目标与可用主版本，未知项记录TARGET_UNCONFIRMED。来源原生控制录音使用独立namespace，不冒充MusicBrainz录音或商业原唱。

许可检查保存文件级URL、声明、作者/署名、核验时间及适用条件。[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)和[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)的署名与再分发条件随原始文件保留；本阶段不转码、不公开分享或上传。对私人保存的批准限于本次明确许可的文件和用途。

## 网络防护

- 音频只允许HTTPS/443，拒绝userinfo、非标准端口、控制字符、路径穿越及任意主机。默认不继承环境代理，不共享浏览器cookie/登录资料。
- Commons只接受`upload.wikimedia.org/wikipedia/commons/<hash>/<hash>/<original filename>`原始文件路径，不使用任意缩略图/第三方URL。Archive/Jamendo限定各自下载主机和路径，不能跨provider重定向。
- 每次重定向重新检查，最多3跳；401及验证码/访问限制不能触发登录或浏览器绕过。过期地址只能重新核对官方元数据。
- DNS在实际TCP连接时解析；全部结果必须为全球公共IP，拒绝本地/私有/保留/多播及映射后的私有IPv4。选定IP后直接连接该IP，TLS仍使用原主机名证书/SNI，避免检查和连接之间再次DNS解析。
- 网络适配使用当前httpx0.28.1/httpcore1.0.9的受保护连接池接口；启动时检查接口，缺失即UNSAFE_TRANSPORT失败，不静默退回不固定DNS的实现。后续升级需要回归此边界。
- 传输限并发、限大小、限速、限超时和重试；拒绝未知/过大的HTTP总长度、错误Content-Range、变化验证器、非预期压缩编码或非音频内容类型。明显MZ/ELF/ZIP/HTML响应在发布前拒绝，不执行任何下载文件。

DNS固定、私网/用户信息/错误协议/端口/重定向、大小及类型拒绝均有MockTransport/真实本地文件测试。真实网络使用相同安全客户端访问Commons，不为测试加入localhost下载例外。

## 续传与文件完整性

标准带引号的强ETag才可直接用于If-Range。弱或裸ETag不使用；Last-Modified需满足Date至少晚60秒等条件。服务端206必须与已有前缀起点及对象相符；200重新从零写入自己任务的`.part`。实际文件长度优先于可能滞后的UI持久计数，避免进程崩溃时丢失进度或错误拼接。

完整接收后验证官方大小/校验值，计算SHA-256并解析实际音频格式和时长，WAV验证声明数据长度。失败、取消、许可不明和字节已收完但未验证，都不能统计为COMPLETED。文件扩展名不作唯一格式证据。

Windows路径组件过滤设备名和非法字符，归档解析必须留在所选根目录。文件名包含版本/录音摘要/内容摘要；发布不覆盖不同文件。只允许按任务UUID和已记录路径识别的`.part`清理，不删除既有音乐、目录、原始Recording或审核数据。整个目录不做递归删除。

下载文件与数据库不是一个跨资源事务：若在发布之后、SQLite完成之前崩溃，可能留下已验证但尚未登记的文件；不会伪造完成或删除它。重试仍通过校验和冲突检查处理，不承诺跨文件系统与SQLite的绝对原子事务。

## 凭据与私人数据

不新增OAuth、Drive、阿里云盘或浏览器登录流程。Jamendo client_id仅从现有环境配置读取；正式环境未配置。新增持久证据过滤常见凭据字段、Bearer内容、URL用户信息和签名参数；实际传输URL重新从官方API获得，不能拿过滤后的URL当有效下载链接。恢复保存含有效文件标识/格式参数的规范资源路径及验证器，只过滤签名/跟踪参数，不把不同查询身份强行当成同一文件。

正式旧缓存不删改；新增来源候选和下载证据采用共享`privacy.py`，避免来源仓储反向依赖下载引擎。媒体、SQLite、凭据、临时文件、QA报告和音频旁证均被Git排除。修正原`downloads/`忽略规则为根目录`/downloads/`，使`src/melodyvault/downloads/*.py`源码可提交，同时`.local`和`*.evidence.json`保持私有。

## 实际检查结果

- 正式库本轮基线为**2055**条Recording，全部SHA-256一致；旧报告1520条作为子集额外核验。
- v1–6迁移checksum一致；追加v7；integrity_check=ok、foreign_key_check无错误。
- Song身份字段、Song-Recording归属和原审核事件一致；47个source_runs、155个source_jobs、228个source_attempts、3个浏览器检查、37个统一搜索缓存及既有确认记录逐行一致。
- 正式download_jobs=0、automatic_download=false，所有真实下载均在明确开启的独立QA库；云端、Archive/Jamendo适配器及Chrome浏览器实现原文件哈希不变。
- 两种真实原始媒体保存成功；最终GUI和真正新进程恢复均取得206，详情见验收报告。未把钢琴版、百科朗读或商业原唱未知授权算成成功。

记录位于`.local/reports/phase3b/preservation.json`、`native-release/`、`process-restart/`及测试XML。没有修改SuiSound，也没有进入Phase3C。

## 尚未验收的范围

Jamendo真实账号/服务、Archive具体权利链审批、未知CDN、全部媒体编码逐帧解码、声纹识别、Windows11/独立exe及网络盘异常不在本轮已通过项目中。来源与许可证信息仍可能不完整；当前策略拒绝未知项，不通过降低证据标准补足数量。
