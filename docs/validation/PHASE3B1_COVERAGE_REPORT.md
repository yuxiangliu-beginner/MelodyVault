# Phase 3B.1 中文歌曲真实覆盖率报告

2026-11-14，Windows / Python 3.13.2。固定 30 首、8 位歌手；基准数据位于 `tests/fixtures/phase3b1_chinese_songs.json`。

## 实际结论

**中文授权下载 0/30；商业及独立音乐的授权下载覆盖率没有改善。** 发现域名、候选文件、正确元数据、完整目标录音和下载许可分开计数。

| 指标 | 实际结果 |
|---|---:|
| 自动新发现调查域名（非预置） | 64 |
| 注册表总域名（含 4 个预置 API） | 68 |
| 可访问网站 | 13（新发现 10 + 正式 API 3） |
| 已做状态检查 | 33（29 新网站 + 3 API 联网 + 1 未配置检查） |
| 尚未做网站访问检查 | 35 |
| 编译适配器/官方接口已核验 | 3；新增 ccMixter 1 个 |
| 实测接受中文查询的正式音源 API | 3：Commons / Archive / ccMixter |
| 普通网页发现搜索表单 | 4；未证明能搜索中文音乐 |
| 返回任意音频候选的歌曲 | 5/30（16.67%） |
| 候选文件 | 7；包括不匹配的钢琴翻奏和另一混音 |
| 正确目标元数据 | 29/30：28 个 MB/本地目录身份 + 1 个官方原生录音 |
| 正确演唱者/版本的来源候选 | 1/30，2 个格式文件 |
| 有完整文件元数据线索的来源 | 2：Archive 与 ccMixter；不代表目标录音完整性已核验 |
| 与目标一致的完整录音候选来源 | 1：ccMixter 粤语无伴奏翻唱；作品权利未解决 |
| 明确通过全部下载权限的来源/歌曲 | 0 / 0 |
| 候选文件授权状态 | LICENSE_UNVERIFIED 7；LICENSE_VERIFIED 0 |
| 无结果 / 来源搜索失败 | 25 首 / 0 首 |
| MusicBrainz 发生 503 的查询 | 3；部分有本地候选可回退，不计作来源搜索失败 |
| 真实中文下载成功 | 0 首 / 0 文件 |

“新发现”包含新闻、百科外链、存档和与歌曲无关的站点，**不是 64 个已验证音乐网站**。例如 commonchemistry.cas.org 是歧义外链，保持待审核。没有通用全网搜索 API 密钥，实际渠道是公开 Wikipedia 搜索/外链 API。

## 逐首、逐来源结果

表中的数字是返回候选文件数；0 是真实查询无结果。“未配置”不计为成功或失败。

| # | 歌手 | 歌曲 | Commons | Archive | ccMixter | Jamendo | 目标元数据 | 资格结果 |
|---:|---|---|---:|---:|---:|---|---|---|
| 1 | 周杰伦 | 晴天 | 0 | 1 | 0 | 未配置 | MBID 已选定 | VERSION_MISMATCH ×1 |
| 2 | 周杰伦 | 七里香 | 0 | 1 | 0 | 未配置 | MBID 已选定 | VERSION_MISMATCH ×1 |
| 3 | 周杰伦 | 稻香 | 0 | 1 | 0 | 未配置 | MBID 已选定 | VERSION_MISMATCH ×1 |
| 4 | 周杰伦 | 青花瓷 | 0 | 1 | 0 | 未配置 | MBID 已选定 | VERSION_MISMATCH ×1 |
| 5 | 周杰伦 | 夜曲 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 6 | 林俊杰 | 江南 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 7 | 林俊杰 | 曹操 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 8 | 林俊杰 | 小酒窝 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 9 | 林俊杰 | 一千年以后 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 10 | 林俊杰 | 修炼爱情 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 11 | 周传雄 | 黄昏 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 12 | 周传雄 | 寂寞沙洲冷 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 13 | 周传雄 | 蓝色土耳其 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 14 | 周传雄 | 我的心太乱 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 15 | 周传雄 | 关不上的窗 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 16 | 张惠妹 | 听海 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 17 | 张惠妹 | 记得 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 18 | 张惠妹 | 真实 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 19 | 张惠妹 | 解脱 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 20 | 张惠妹 | 连名带姓 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 21 | 草东没有派对 | 大风吹 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 22 | 草东没有派对 | 山海 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 23 | 草东没有派对 | 烂泥 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 24 | 告五人 | 爱人错过 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 25 | 告五人 | 披星戴月的想你 | 0 | 0 | 0 | 未配置 | 未可靠匹配 | 无候选 |
| 26 | 告五人 | 在这座城市遗失了你 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 27 | 陈粒 | 奇妙能力歌 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 28 | 陈粒 | 小半 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 29 | 陈粒 | 易燃易爆炸 | 0 | 0 | 0 | 未配置 | MBID 已选定 | 无候选 |
| 30 | Li Yao Ming | The King 之王 | 0 | 0 | 3 | 未配置 | 官方原生文件 | LICENSE_UNVERIFIED ×3 |

《The King 之王》首轮使用上传账号 solos_to_use 和未指定版本，误把自身翻唱标为版本不符；补测依据官方 featuring 改为 Li Yao Ming、明确 cover 版本。两种格式成为 METADATA_MATCH，仍因传统作品权利链不足而拒绝下载。初次结果完整保留，未用修改样本伪造提升。
其余 4 首的 Archive 命中属于钢琴翻奏，VERSION_MISMATCH；不能计为周杰伦原唱。《The King (之王)》另一混音署名/版本不同，保留独立候选，不自动合并。

## 候选链接和拒绝原因

| 目标 | 来源文件身份 | 原始网页 | 原因 |
|---|---|---|---|
| 晴天 | archive:jay-chou-piano-40/08.mp3 / mp3 | [来源](https://archive.org/details/jay-chou-piano-40) | VERSION_MISMATCH；未提供可识别的明确录音许可URL；公开可播放不是授权 |
| 七里香 | archive:jay-chou-piano-40/11.mp3 / mp3 | [来源](https://archive.org/details/jay-chou-piano-40) | VERSION_MISMATCH；未提供可识别的明确录音许可URL；公开可播放不是授权 |
| 稻香 | archive:jay-chou-piano-40/37.mp3 / mp3 | [来源](https://archive.org/details/jay-chou-piano-40) | VERSION_MISMATCH；未提供可识别的明确录音许可URL；公开可播放不是授权 |
| 青花瓷 | archive:jay-chou-piano-40/33.mp3 / mp3 | [来源](https://archive.org/details/jay-chou-piano-40) | VERSION_MISMATCH；未提供可识别的明确录音许可URL；公开可播放不是授权 |
| The King 之王 | ccmixter:49286:74812 / mp3 | [来源](https://ccmixter.org/files/solos_to_use/49286) | METADATA_MATCH；改编/翻唱/采样权利链或完整歌曲范围未核实 |
| The King 之王 | ccmixter:49286:74813 / flac | [来源](https://ccmixter.org/files/solos_to_use/49286) | METADATA_MATCH；改编/翻唱/采样权利链或完整歌曲范围未核实 |
| The King 之王 | ccmixter:49285:74811 / mp3 | [来源](https://ccmixter.org/files/pharmacopia/49285) | REVIEW_REQUIRED；改编/翻唱/采样权利链或完整歌曲范围未核实 |

## 请求、耗时与缓存

初次 30 首完整测试实际墙钟时间 2556.02 秒；MusicBrainz 57 请求，来源元数据 169 请求（重试 0），发现渠道/网页检查 109 请求。初始化正式 API 另 3 请求。包含服务器延迟/退避，不用固定计时模拟进度。

原生身份补测另 3 来源请求、4 发现请求，正式 API 检查另 3 请求；不覆盖首轮性能统计。

缓存回归：同一晴天查询复用 Archive / Commons / ccMixter，真实新增 HTTP 请求 0，耗时 0.5743 秒；发现查询命中 2 个缓存，新增请求 0，耗时 1.1831 秒。

## 来源状态清单

下列为首轮实际保存状态。UNSAFE 的三个站点是未跟随的重定向，不能据此认定网站恶意；UNAVAILABLE 包含 HTTP 403、404、体积限制或响应解压失败。最终程序已将 401/403/429 归类为 RESTRICTED，旧历史保留原判断。

| 域名 | 状态 | 审核 | 格式/权限 |
|---|---|---|---|
| 163.com | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| 8world.com | UNSAFE | PENDING_REVIEW | 逐文件授权未验证 |
| allmovie.com | UNSAFE | PENDING_REVIEW | 逐文件授权未验证 |
| api.jamendo.com | METADATA_ONLY | PENDING_REVIEW | 逐文件授权未验证 |
| archive.org | SEARCH_SUPPORTED | APPROVED | 逐文件授权未验证 |
| bamid.gov.tw | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| bilibili.com | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| blow.streetvoice.com | UNSAFE | PENDING_REVIEW | 逐文件授权未验证 |
| businessweekly.com.tw | DISCOVERED | PENDING_REVIEW | 未检查 |
| ccmixter.org | SEARCH_SUPPORTED | APPROVED | 逐文件授权未验证 |
| chinatimes.com | ACCESSIBLE | PENDING_REVIEW | 逐文件授权未验证 |
| cna.com.tw | SEARCH_SUPPORTED | PENDING_REVIEW | 逐文件授权未验证 |
| commonchemistry.cas.org | ACCESSIBLE | PENDING_REVIEW | 逐文件授权未验证 |
| commons.wikimedia.org | SEARCH_SUPPORTED | APPROVED | 逐文件授权未验证 |
| dashi.streetvoice.cn | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| douban.com | SEARCH_SUPPORTED | PENDING_REVIEW | 逐文件授权未验证 |
| dwnews.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| elle.com | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| ent.ltn.com.tw | SEARCH_SUPPORTED | PENDING_REVIEW | 逐文件授权未验证 |
| ent.sina.com.cn | DISCOVERED | PENDING_REVIEW | 未检查 |
| epochtimes.com | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| facebook.com | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| gq.com.tw | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| hb.sina.com.cn | DISCOVERED | PENDING_REVIEW | 未检查 |
| inewsdb.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| instagram.com | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| jianshu.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| jvrmusic.com | ACCESSIBLE | PENDING_REVIEW | 逐文件授权未验证 |
| k.sina.cn | DISCOVERED | PENDING_REVIEW | 未检查 |
| k.sina.com.cn | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| kkbox.com | ACCESSIBLE | PENDING_REVIEW | 逐文件授权未验证 |
| linkinghub.elsevier.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| medium.com | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |
| merit-times.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| mirrormedia.mg | DISCOVERED | PENDING_REVIEW | 未检查 |
| mojinggeci.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| movie.douban.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| movies.yahoo.com.tw | DISCOVERED | PENDING_REVIEW | 未检查 |
| music.163.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| music.migu.cn | DISCOVERED | PENDING_REVIEW | 未检查 |
| musicbrainz.org | ACCESSIBLE | PENDING_REVIEW | 逐文件授权未验证 |
| must.org.tw | DISCOVERED | PENDING_REVIEW | 未检查 |
| mymusic.net.tw | DISCOVERED | PENDING_REVIEW | 未检查 |
| natalie.mu | DISCOVERED | PENDING_REVIEW | 未检查 |
| new.qq.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| news.mingpao.com | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| news.tvbs.com.tw | SEARCH_SUPPORTED | PENDING_REVIEW | 逐文件授权未验证 |
| nla.gov.au | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| pmdb.taipei | DISCOVERED | PENDING_REVIEW | 未检查 |
| pttsuperstar.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| pubchem.ncbi.nlm.nih.gov | DISCOVERED | PENDING_REVIEW | 未检查 |
| pubmed.ncbi.nlm.nih.gov | DISCOVERED | PENDING_REVIEW | 未检查 |
| rottentomatoes.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| site.douban.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| solomo.xinmedia.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| star.ettoday.net | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| stars.udn.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| streetvoice.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| tw.appledaily.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| tw.news.yahoo.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| udn.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| viaf.org | DISCOVERED | PENDING_REVIEW | 未检查 |
| web.archive.org | ACCESSIBLE | PENDING_REVIEW | 逐文件授权未验证 |
| weibo.com | RESTRICTED | PENDING_REVIEW | 逐文件授权未验证 |
| worldjournal.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| y.qq.com | DISCOVERED | PENDING_REVIEW | 未检查 |
| yourart.asia | DISCOVERED | PENDING_REVIEW | 未检查 |
| youtube.com | UNAVAILABLE | PENDING_REVIEW | 逐文件授权未验证 |

## 格式与真实下载控制

中文候选发现了 MP3 与 FLAC 的真实文件元数据，但没有通过完整权利核验，两个格式均未下载。WAV/M4A/AAC/Ogg/Opus 没有本轮合格中文样本，不声称已完成这些格式的中文真实下载验证。

独立的外语控制测试：Commons 原始 MP3 5,369,410 字节、WAV 24,968,780 字节真实下载成功，均验证媒体时长、官方 SHA-1 和 SHA-256。MP3 暂停后新管理器续传 RANGE_ACCEPTED，重复文件复用。它们只证明下载引擎正常，绝不计入中文覆盖率。

完整机器结果、错误、查询参数、候选与实际音频保存在被 Git 忽略的 `.local/reports/phase3b1/`；本报告只提交公共来源统计与链接。
