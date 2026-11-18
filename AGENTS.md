# AGENTS.md — 给 AI agent 和开发同事

这份文件是给**帮忙修改这个项目的 AI agent**（以及开发同事）读的。改任何代码之前先读完它。使用说明在 [README.md](README.md)，版本历史在 [CHANGELOG.md](CHANGELOG.md)。

## 这个项目是什么

- 一个本地运行的语音工作台：Flask 后端 + 单个 HTML 页面，把豆包和 MiniMax 两家的语音合成、声音复刻接口包成不懂代码的同事也能用的网页。
- 作者是 **yuki**。其他人和 agent 是协作者：改动要小、要可回退、要记录。
- 使用者是非技术同事。任何改动都要问一句：一个不懂代码的人第一次打开，会不会被吓到或点错？

## 目录结构

| 路径 | 作用 |
|---|---|
| `app.py` | 全部后端：配置读写、两家接口的合成、复刻、Excel 导入导出、音频存取 |
| `templates/index.html` | 全部前端：样式、页面、脚本都在这一个文件里 |
| `test_app.py` | 单元测试（unittest，使用 Flask 测试客户端，不联网） |
| `RUN_AI_VOICE_STUDIO.cmd` | 启动器：建 `.venv`、装依赖、选端口、启动 |
| `启动AI语音工作台.bat`、`备用启动AI语音工作台.cmd` | 只是调用上面的启动器 |
| `pick_port.py` | 在 8765～8775 里找一个空闲端口 |
| `AI语音批量生成模板.xlsx` | 批量模板的静态副本；页面上下载的模板由 `build_template_workbook()` 实时生成 |
| `config.example.json` | 配置示例 |
| `config.local.json` | 本机的真实配置和密钥，**不进 Git** |
| `data/audio/` | 生成的音频，**不进 Git** |

## 必须遵守的约定

这些是作者和协作者已经定下来的，不要在没有被明确要求的情况下打破。

1. **不改框架和整体交互。** 不引入前端框架、构建工具、数据库，不拆分 `index.html`。页面的两个标签页、卡片布局、手绘风格保持不变。
2. **新增的东西默认折叠。** 进阶功能放进 `<details class="adv">`，默认收起；主界面只保留最常用的几项。
3. **不填就等于没有。** 新增的参数全部可选。使用者不展开、不填写时，发给接口的请求必须和改动前完全一致。`test_minimax_payload_uses_advanced_options` 守着这一条，改合成逻辑后它必须通过。
4. **每个新参数都要有说明。** 标签后面放 `<span class="tip" tabindex="0" data-tip="…">?</span>`，用大白话写它是什么、建议怎么填、有什么副作用。会产生费用的，必须在说明里写明。
5. **两家接口的参数不要混传。** 豆包不认识的字段传过去会报 `invalid params`。MiniMax 专属的参数只在音色是 MiniMax 时发送；选中豆包音色时相关区域置灰并提示（见 `updateAdvState()`、`updateCloneAdv()`）。
6. **所有来自页面的值都在后端清洗。** 参考 `normalize_minimax_options()`：只接受白名单里的值，数字夹到合法范围，不合法的直接忽略，不要原样转发。
7. **默认是模拟模式。** 模拟模式下任何操作都不能调用真实接口。测试也必须在不联网的情况下通过。
8. **密钥只存在 `config.local.json`。** 不写进源码、文档、测试、日志、提交信息。日志不打印输入文案和完整请求头。
9. **服务只监听 `127.0.0.1`。**
10. **声音复刻必须保留授权确认。** 前端的勾选框和后端的 `consent` 检查都不能去掉或默认勾选。说明文字里要保留“只能复刻本人或已取得本人明确授权的声音”。
11. **高级参数目前只在“单条任务”生效。** 批量任务、Excel 模板的列不要动，除非被明确要求。

## 怎么运行和测试

**运行**（Windows）：双击 `RUN_AI_VOICE_STUDIO.cmd`。开发时不想弹浏览器，可以用：

```
.venv\Scripts\python.exe -m flask --app app.py run --port 8791
```

**测试**：

```
.venv\Scripts\python.exe -m unittest test_app
```

- 改完代码必须跑测试，全部通过才算完成。
- 新增功能要补测试。需要验证发给接口的内容时，像现有测试那样临时替换 `voice_app.requests.post`，不要真的联网。
- 测试会在当前文件夹生成 `config.local.json` 和 `data/audio/` 下的文件，它们已被 `.gitignore` 忽略。

**在浏览器里验证页面**：

- 模拟模式下就能验证绝大多数页面逻辑。
- **改了 `templates/index.html` 之后要重启服务**，否则看到的还是旧页面（Flask 非调试模式会缓存模板）。
- 页面脚本直接用元素的 `id` 当全局变量（例如 `singleVoice.value`），新增元素时注意 `id` 不要重复，也不要和已有的函数、变量同名。

## 接口要点

### MiniMax

- 合成：`POST https://api.minimaxi.com/v1/t2a_v2`。音频以十六进制字符串返回。
- 复刻：先 `POST https://api.minimax.cn/v1/files/upload`（`purpose=voice_clone`，示例音频用 `purpose=prompt_audio`），再 `POST https://api.minimax.cn/v1/voice_clone`。
- 两个域名目前都可用，代码里是混用的，属于历史原因，不影响功能。
- 官方文档索引：`https://platform.minimax.cn/docs/llms.txt`，每个页面地址后加 `.md` 可以拿到原文。**改参数前先查文档，不要凭记忆写参数名。**
- 情绪枚举：`happy`、`sad`、`angry`、`fearful`、`disgusted`、`surprised`、`calm`，以及仍被接受的 `neutral`。
- 复刻音频要求：mp3/m4a/wav，10 秒～5 分钟，不超过 20 MB；示例音频短于 8 秒。
- 自定义 voice_id：8～256 位，字母开头，只含字母、数字、`-`、`_`，不能以 `-` 或 `_` 结尾（`VOICE_ID_RULE`）。
- 费用：复刻音色首次用于合成时扣 9.9 元；复刻后 7 天未正式合成会被删除。
- 文本里的特殊标记：`<#0.5#>` 是停顿（只能夹在两段可读文字之间）；`(laughs)` 这类语气词只有 speech-2.8 模型支持，偶尔会让后面的读音异常。

### 豆包

- 合成：`https://openspeech.bytedance.com/api/v3/tts/unidirectional`，按行返回 JSON，音频是 base64。
- 复刻 2.0：`/api/v3/tts/voice_clone`，使用控制台里预付费的 `S_` 音色 ID；状态查询 `/api/v3/tts/get_voice`。
- 当前接入的 `seed-tts-1.0` 不传情绪和音量。

## 已知的坑

- `templates/index.html` 的单行非常长（一个区块一行）。修改时用精确的字符串替换，改完检查脚本语法和 `id` 是否重复。
- 在 Windows 的 Git Bash 里用 heredoc 往文件里写带转义字符的内容，可能混进空字节导致文件损坏。写文件请用编辑器或工具的写文件功能。
- 复刻素材在浏览器里统一转成 24 kHz 单声道 16 位 WAV 再上传，后端用 `wave` 模块校验；直接往 `/api/clone` 传 mp3 会被拒绝。
- `validate_audio_bytes()` 会按 MIME 检查文件头。新增输出格式时要同时更新它和 `MINIMAX_FORMATS`。
- `load_config()` 会把保存的音色和默认音色合并：默认音色的 `id` 不能随便改，否则使用者保存过的覆盖会失效。
- 素材预检（`analyzeClone()`）是粗略估计，只做提示，不要用它拦截提交。

## 改完之后

每次改动都要做这四件事：

1. 跑测试，全部通过。
2. 在 [CHANGELOG.md](CHANGELOG.md) 最上面加一条：版本号、日期、改了什么、动了哪些文件、哪些没有用真实接口验证过。
3. 功能或用法变了，就同步更新 [README.md](README.md)；约定或坑变了，就更新本文件。
4. 版本号要改三处并保持一致：`app.py` 的 `APP_VERSION`、README 顶部、CHANGELOG 的标题。

提交信息用中文，写清楚“做了什么、为什么”。不要提交 `config.local.json`、`data/audio/` 里的音频、`.venv/`。

## 如果不确定

涉及下面这些，先问作者或提出需求的人，不要自己决定：

- 改动主界面的布局或默认值。
- 改动批量任务或 Excel 模板的列。
- 新增会产生费用的自动调用。
- 改默认音色列表，或把仓库从私有改为公开（默认音色里有团队成员的复刻音色）。
