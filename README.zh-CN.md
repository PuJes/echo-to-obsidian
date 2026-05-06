# Echo to Obsidian

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Local First](https://img.shields.io/badge/local--first-whisper-orange.svg)](https://github.com/SYSTRAN/faster-whisper)

[English](./README.md) | 简体中文

把视频和音频一键整理成 Obsidian 可直接使用的笔记：

- 自动嵌入音频
- 自动生成带时间戳的逐行转录
- 全流程本地优先

不依赖云端转录 API。

## 为什么值得自己做

1. **更注重隐私**  
   转录在本地通过 `faster-whisper` 运行，尽量避免把录音内容上传到线上大模型服务。
2. **更省钱**  
   现在开源语音识别已经很强了。如果你高频处理素材，本地方案可以明显减少按分钟计费的转录成本。

```mermaid
flowchart LR
    A["本地文件 / 视频链接"] --> B["yt-dlp + ffmpeg"]
    B --> C["faster-whisper（本地）"]
    C --> D["Markdown + JSON"]
    D --> E["Obsidian 笔记（含音频）"]
```

## 为什么做这个项目

常见转录流程一般要拆成 3 步：

1. 下载音频/视频
2. 转录成文字
3. 手工整理成 Obsidian 笔记

Echo to Obsidian 把这三步收成一个 CLI，尽量让你从素材到可用笔记只走一条命令。

## 这个项目有什么不一样

| 能力 | 常见方式 | Echo to Obsidian |
| --- | --- | --- |
| 音频附件 | 手动复制 | 自动保存到 `attachments/` |
| 时间戳链接 | 手动加 | 每段自动生成 |
| Obsidian 格式 | 还要二次整理 | 生成后即可用 |
| 隐私 | 常依赖云端 | 本地优先 |

## 适合谁

- 在 Obsidian 里做内容素材库的创作者
- 需要整理 B 站 / YouTube 资料的研究者
- 需要“可回听 + 可定位”的课程、访谈、会议记录场景

## 功能

- 基于 `faster-whisper` 的本地转录
- 支持本地文件和公开视频链接
- 自动保存音频附件到 `attachments/`
- 每行转录带可点击时间戳链接：
  `[[attachments/example.m4a#t=42|00:00:42]]`
- 支持批量处理（扫描目录或扫描 Markdown 链接）

## 安装

### 方式 1：源码安装（推荐）

```bash
git clone https://github.com/PuJes/echo-to-obsidian.git
cd echo-to-obsidian
uv sync
```

### 系统依赖

- `ffmpeg`
- `yt-dlp`（处理视频链接时需要）

## 快速开始

单条转录：

```bash
uv run echo2obs "/绝对路径/your-audio.mp3"
```

转录公开视频链接：

```bash
uv run echo2obs "https://www.bilibili.com/video/BVxxxxxxxxx"
```

从 Markdown 批量扫描链接：

```bash
uv run echo2obs-batch --from-md "./Cubox" --limit 20 --model-size tiny
```

从媒体目录批量处理：

```bash
uv run echo2obs-batch --from-dir "./recordings" --limit 10
```

## 输出结构

默认输出到 `./transcripts`：

```text
transcripts/
  ├── My Note Title.md
  ├── My Note Title.json
  └── attachments/
      └── My Note Title.m4a
```

## 命令帮助

单条命令：

```bash
uv run echo2obs --help
```

批量命令：

```bash
uv run echo2obs-batch --help
```

## 说明

- 首次运行可能会下载 whisper 模型权重。
- 如果网络环境对代理限制严格，建议首次模型拉取先在无代理环境下运行。
- 追求更高质量可以使用 `--model-size small` 或 `medium`。

## 路线图

- [ ] 一键重跑失败项
- [ ] 可选导出 `.srt` / `.vtt`
- [ ] 可选说话人分离模式

## License

MIT
