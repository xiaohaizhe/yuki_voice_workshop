# 更新记录

每次改动都在这里记一条，最新的在最上面。写法见 [AGENTS.md](AGENTS.md) 的“改完之后”。

项目作者：yuki。

---

## v0.1.14（2026-11-18）

**来源**：协作贡献，基于 yuki 的 v0.1.13（文件夹 `AI_Voice_Studio_v0.1.13_dual_clone`）修改。

**一句话**：在合成和复刻两处增加了默认折叠的高级参数、悬浮说明、音色试听和复刻素材预检。框架、页面布局、原有操作都没有变。

**兼容性保证**：不展开、不填写新增内容时，发给 MiniMax 的请求体与 v0.1.13 逐字段一致（见 `test_app.py` 的 `test_minimax_payload_uses_advanced_options`）；豆包的请求没有任何变化；批量任务没有任何变化。

### 新增

- **情绪**：新增“惊讶”“平静”“厌恶”，分别对应 MiniMax 的 `surprised`、`calm`、`disgusted`。单条的情绪按钮、批量的下拉、Excel 模板的下拉都同步增加。
- **音色试听**（单条任务）：音色下拉旁的“试听”按钮，用固定短句走一次正常的生成接口。
- **单条任务 · 高级参数**（仅 MiniMax 音色，默认折叠）：
  - 语调与精细调节：自定义语速、自定义音量（填了就覆盖上方档位）、语调 `pitch`。
  - 语言与文本处理：`language_boost`、`text_normalization_mode`、发音词典 `pronunciation_dict.tone`。
  - 停顿与语气词：把 `<#0.5#>` 这类停顿标记、`(laughs)` 这类语气词插入到文字光标处。
  - 音频输出与效果器：格式（mp3/wav/flac）、采样率、比特率、`voice_modify` 的三个滑杆和特殊音效。
  - “高级参数恢复默认”按钮。
  - 选中豆包音色时整区置灰并提示，参数不会发给豆包。
- **声音复刻 · 素材预检**：选择录音后在浏览器本地解码、合并，显示时长、可试听，并提示时长不足、底噪偏高、停顿过少、爆音。不调用任何接口。
- **声音复刻 · 高级选项**（仅 MiniMax，默认折叠）：
  - 降噪、音量归一化开关（默认开启，与旧版写死的行为一致）。
  - 自定义 voice_id（留空仍自动生成 `Clone` + 随机串）。
  - 复刻后立即试听：传入 `text` + `model`，返回的 `demo_audio` 直接在页面播放。
  - 示例音频：额外上传一段短于 8 秒的音频和对应文字，走 `clone_prompt`。
- **说明文字**：每个新参数旁有“?”悬浮说明；合成和复刻各有一段折叠的“使用说明”。
- **作者标识**：页面底部和 README 标注作者 yuki。
- **文档**：重写 README；新增本文件和 AGENTS.md。

### 改动的文件

| 文件 | 改了什么 |
|---|---|
| `app.py` | 版本号；情绪映射；新增 `normalize_minimax_options()`；`synthesize_minimax()` 增加可选的 `options` 参数；`validate_audio_bytes()` 支持 FLAC；`/api/generate` 接收可选的 `advanced` 字段；`/api/clone` 的 MiniMax 分支接收可选的高级选项并返回 `voice_id`、`demo_audio`；新增 `APP_AUTHOR` |
| `templates/index.html` | 新增样式（`details.adv`、`.tip`、`.precheck` 等）；单条任务的试听按钮和高级参数区；复刻区的预检、高级选项、使用说明；`cloneVoice()` 拆成 `prepareClone()`、`encodeWav()`、`decodeMono()`、`analyzeClone()`；页面底部作者标识 |
| `test_app.py` | 原有 1 个测试保留不变，新增 6 个 |
| `AI语音批量生成模板.xlsx` | 重新生成，情绪下拉包含新增的三项 |
| `README.md` | 重写 |
| `.gitignore` | 增加启动器产生的临时文件 |

### 没有改的

- 豆包合成与豆包复刻的逻辑。
- 批量任务的流程、表格列、Excel 模板的列。
- 接口配置、声音 ID 管理、打包下载。
- 启动脚本。
- MiniMax 的接口域名（合成用 `api.minimaxi.com`，复刻用 `api.minimax.cn`，实测两个都可用）和“温柔”“严肃”映射到的 `neutral`（实测接口仍接受）。

### 尚未验证

以下内容只在模拟模式和假响应下测过，**没有用真实接口跑过**，第一次使用时请留意：

- 高级参数里的 `voice_modify`、`flac`/`wav` 输出、`text_normalization_mode`。
- 复刻的四个高级选项（自定义 voice_id、试听、示例音频、关闭降噪）。
- 素材预检的阈值是经验值，只做提示，不拦截提交。

---

## v0.1.13 及更早

由 yuki 开发。此前没有逐版本的记录，以下是从原 README 和代码里能确认的要点：

- v0.1.13（`dual_clone`）：声音复刻同时支持 MiniMax 与豆包复刻 2.0。
- v0.1.11：界面改为手绘游戏任务板风格，页面顶部显示版本标识；启动器自动避开被占用的端口。
- v0.1.10：保存前检查 MP3/WAV 头部，无法播放的结果直接标为失败。
- 更早：单条与批量生成、Excel 模板导入、打包下载、接口配置与声音 ID 管理、模拟模式。
