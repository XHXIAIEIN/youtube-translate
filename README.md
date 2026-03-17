# YouTube Live Translator

YouTube 直播/视频的实时同声传译。打开一个终端窗口，英文进去、中文出来。

## 它能干什么

- 实时听 YouTube 直播或视频的英语音频
- 用 Whisper 转成文字
- 用 AI 翻译成中文（支持 22 个翻译服务）
- 人名地名保留英文，旁边自动标注中文

效果大概长这样：

```
Welcome to the second hour of The World Today. I'm Stuart Norval.  17:00:17
欢迎收看《The World Today》第二时段，我是Stuart Norval。

In other news, lava pouring down a volcano on the French island of
Reunion. Spectacular images the island has not seen in 20 years.  17:01:02
其他消息，法属Reunion岛火山喷发，岩浆倾泻而下，
这是该岛近20年来最壮观的景象。

The Michelin Guide has handed out its famous stars to top restaurants
around the world.  17:01:13
米其林指南公布了今年的星级餐厅榜单。

Our correspondent Dave Keating joins us now from Brussels.  17:03:15
下面连线驻Brussels(布鲁塞尔)记者Dave Keating。
```

## 准备工作

需要装这些东西（只装一次）：

1. **Python 3.12+** — [python.org](https://www.python.org/downloads/) 下载安装，记得勾「Add to PATH」
2. **FFmpeg** — 打开终端，跑一行命令：
   ```
   winget install ffmpeg
   ```
3. **项目依赖** — 在项目目录里跑：
   ```
   pip install -r requirements.txt
   ```

如果有 NVIDIA 显卡，Whisper 会自动用 GPU 加速。没有也能跑，就是慢一点。

## 配置翻译服务

默认使用 Google 翻译，**不需要注册、不需要 API Key**，装好依赖直接能跑。

如果你想用其他翻译服务（比如 LLM 翻译效果更好），编辑 `run.cmd` 里的 `PROVIDER`，并在 `.keys/api_keys.env` 里填对应的 key。详见下方支持列表。

## 使用

编辑 `run.cmd` 里的 URL，换成你要看的 YouTube 链接，然后双击运行。

```
set URL=https://www.youtube.com/watch?v=你的视频ID
```

或者直接命令行：

```
python live_translate.py "https://www.youtube.com/watch?v=xxxxx"
```

## 支持的翻译服务

| 服务 | 需要 Key | 说明 |
|------|:--------:|------|
| | | **免费，无需注册** |
| google-free | 否 | Google 翻译（默认） |
| microsoft-free | 否 | 微软翻译 |
| ollama | 否 | 本地离线，需要显卡和下载模型（建议 14B 以上） |
| | | **翻译 API** |
| deepl | 是 | DeepL |
| baidu | 是 | 百度翻译 |
| caiyun | 是 | 彩云小译 |
| youdao | 是 | 有道翻译 |
| niutrans | 是 | 小牛翻译 |
| tencent | 是 | 腾讯翻译君 |
| google | 是 | Google Cloud Translation |
| microsoft | 是 | Azure Translator |
| volcano | 是 | 火山翻译（字节） |
| | | **大模型** |
| groq | 是（免费额度） | Llama 70B，速度快 |
| gemini | 是（免费额度） | Google Gemini |
| zhipu | 是（免费额度） | 智谱 GLM-4-Flash |
| qwen | 是（免费额度） | 通义千问 |
| kimi | 是（免费额度） | Moonshot |
| siliconflow | 是（免费额度） | 硅基流动 |
| deepseek | 是 | DeepSeek |
| openai | 是 | GPT-4o-mini |
| anthropic | 是 | Claude Haiku |
| doubao | 是 | 豆包（字节） |
| openrouter | 是 | LLM 聚合平台 |
| together | 是 | LLM 聚合平台 |

## 常见问题

**Q: 打开就报错 `yt-dlp: no audio stream found`**
A: 检查链接是不是有效的 YouTube 地址。如果是直播，确认直播正在进行中。

**Q: 翻译很慢**
A: 换个更快的 provider，比如 groq。

**Q: Whisper 加载很慢**
A: 第一次运行会下载模型（约 500MB），之后就快了。如果下载慢，脚本已配置了 HF 镜像。
