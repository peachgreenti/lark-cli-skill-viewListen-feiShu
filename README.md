# 飞书智能周报工具

> 自动获取飞书日历事件和任务列表，调用 AI 生成正式周报，并一键创建飞书文档。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 目录

- [功能介绍](#功能介绍)
- [效果截图](#效果截图)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [使用方法](#使用方法)
- [配置说明](#配置说明)
- [输出说明](#输出说明)
- [常见问题](#常见问题)

---

## 功能介绍

本工具通过调用 `lark-cli` 命令行工具，实现以下自动化流程：

```
获取本周日历事件 + 任务列表 → AI 生成周报 → 自动创建飞书文档 → 保存本地文件
```

### 核心功能

| 功能 | 说明 |
|------|------|
| 日历事件获取 | 自动获取本周（周一至周日）的飞书日历事件 |
| 任务列表获取 | 获取当前飞书任务列表 |
| AI 周报生成 | 将日历和任务数据组装为 Prompt，调用飞书 AI 生成正式周报 |
| 自动创建文档 | 将生成的周报自动发布为飞书云文档 |
| 多格式输出 | 同时输出 JSON 数据文件和 Markdown 周报文件 |

### 周报结构

AI 生成的周报包含以下板块：

1. **本周工作总结** — 主要工作方向和进展概述
2. **重点工作与成果** — 按项目分类的会议、里程碑、交付成果
3. **进行中的工作** — 正在推进的事项及当前进展
4. **待办与计划** — 未完成任务和下周跟进事项
5. **风险与需要协调的事项** — 需要关注的风险（如有）

---

## 效果截图

### 运行效果

<!-- 截图占位：终端运行效果 -->
![终端运行效果](docs/screenshots/terminal-output.png)

> 终端输出展示：日历获取进度、AI 生成状态、文档创建结果

### AI 生成的周报

<!-- 截图占位：飞书文档中的周报效果 -->
![周报效果](docs/screenshots/weekly-report.png)

> 飞书云文档中的周报展示效果

### JSON 数据文件

<!-- 截图占位：JSON 输出示例 -->
![JSON 输出](docs/screenshots/json-output.png)

> 完整的 JSON 数据文件，包含日历事件、任务列表和周报内容

---

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.10 | 脚本使用了 `tuple[str, str]` 等类型语法 |
| lark-cli | 最新版 | 飞书命令行工具，需提前安装并登录 |

### 检查环境

```bash
# 检查 Python 版本
python3 --version

# 检查 lark-cli 是否可用
lark-cli --version
```

---

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/peachgreenti/lark-cli-skill-weekly-report.git
cd lark-cli-skill-weekly-report
```

### 2. 安装 lark-cli

请参照飞书官方文档安装 `lark-cli`，并完成登录授权：

```bash
# 安装后登录
lark-cli login
```

### 3. 验证安装

```bash
# 确认脚本可执行
python3 feishu_weekly.py --help
```

预期输出：

```
usage: feishu_weekly.py [-h] [--no-ai] [--no-doc] [--ai-cmd [AI_CMD ...]] [--docs-cmd [DOCS_CMD ...]] [--docs-mode {arg,file,stdin}]

飞书本周数据获取 + AI 周报生成 + 自动创建飞书文档

options:
  -h, --help            show this help message and exit
  --no-ai               仅获取数据，不调用 AI 生成周报
  --no-doc              不自动创建飞书文档
  --ai-cmd [AI_CMD ...] 自定义 AI 命令（默认: lark-cli ai）
  --docs-cmd [DOCS_CMD ...] 自定义文档创建命令（默认: lark-cli docs +create）
  --docs-mode {arg,file,stdin} 文档内容传入模式（默认: file）
```

---

## 使用方法

### 基础用法

```bash
# 完整运行：获取数据 → AI 生成周报 → 创建飞书文档
python3 feishu_weekly.py
```

### 仅获取数据

```bash
# 不调用 AI，仅获取日历事件和任务列表
python3 feishu_weekly.py --no-ai
```

### 不创建飞书文档

```bash
# 生成周报但不上传到飞书
python3 feishu_weekly.py --no-doc
```

### 自定义命令

```bash
# 自定义 AI 调用命令
python3 feishu_weekly.py --ai-cmd lark-cli +ai

# 自定义文档创建命令
python3 feishu_weekly.py --docs-cmd lark-cli docs +create --folder "folder_token"

# 切换文档内容传入模式为管道
python3 feishu_weekly.py --docs-mode stdin
```

### 命令行参数一览

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--no-ai` | 跳过 AI 周报生成，仅获取数据 | 关闭 |
| `--no-doc` | 跳过飞书文档创建 | 关闭 |
| `--ai-cmd` | 自定义 AI 调用命令 | `lark-cli ai` |
| `--docs-cmd` | 自定义文档创建命令 | `lark-cli docs +create` |
| `--docs-mode` | 文档内容传入模式 | `file` |

---

## 配置说明

所有配置项位于脚本顶部的 **配置区域**（第 16-29 行），可直接修改源码，也可通过命令行参数覆盖。

### AI 命令配置

```python
# 默认 AI 调用命令
AI_COMMAND = ["lark-cli", "ai"]
```

如果你的 `lark-cli` AI 命令格式不同，修改此处即可。例如：

```python
AI_COMMAND = ["lark-cli", "+ai"]
# 或
AI_COMMAND = ["lark-cli", "ai", "--model", "gpt-4"]
```

### 文档创建配置

```python
# 文档创建命令
DOCS_CREATE_COMMAND = ["lark-cli", "docs", "+create"]

# 内容传入模式
DOCS_CREATE_MODE = "file"  # 可选: "arg" | "file" | "stdin"
```

#### 三种文档传入模式

| 模式 | 说明 | 实际命令示例 |
|------|------|-------------|
| `arg` | 通过命令行参数传入 | `lark-cli docs +create --title "标题" --markdown "内容"` |
| `file` | 通过文件传入（默认） | `lark-cli docs +create --title "标题" --markdown @file.md` |
| `stdin` | 通过管道传入 | `echo "内容" \| lark-cli docs +create --title "标题" --markdown -` |

> 如果内容较长导致命令行参数超限，建议使用 `file` 或 `stdin` 模式。

### 周报 Prompt 自定义

如需调整周报的风格、结构或语言，修改 `WEEKLY_REPORT_PROMPT_TEMPLATE` 常量（第 112-145 行）即可。

---

## 输出说明

运行完成后，会在当前目录生成以下文件：

| 文件 | 格式 | 内容 |
|------|------|------|
| `feishu_weekly_YYYY-MM-DD_YYYY-MM-DD.json` | JSON | 完整数据（日历事件 + 任务 + 周报 + 文档链接） |
| `weekly_report_YYYY-MM-DD_YYYY-MM-DD.md` | Markdown | AI 生成的周报（独立文件） |

### JSON 输出结构

```json
{
  "week_range": {
    "start": "2026-04-13",
    "end": "2026-04-19"
  },
  "calendar_events": { ... },
  "tasks": { ... },
  "weekly_report": "# 周报\n\n...",
  "feishu_doc": "https://xxx.feishu.cn/docx/xxx",
  "fetched_at": "2026-04-18T10:30:00"
}
```

---

## 常见问题

### Q: 运行报错 `command not found: lark-cli`

**A:** 请确认 `lark-cli` 已正确安装并添加到系统 PATH 中：

```bash
which lark-cli
```

### Q: AI 生成的周报内容不准确

**A:** 可以修改脚本中的 `WEEKLY_REPORT_PROMPT_TEMPLATE` 来优化 Prompt，添加更多上下文信息或调整输出要求。

### Q: 文档创建失败

**A:** 请尝试切换文档传入模式：

```bash
# 尝试 file 模式
python3 feishu_weekly.py --docs-mode file

# 或 stdin 模式
python3 feishu_weekly.py --docs-mode stdin
```

### Q: 如何定时自动运行？

**A:** 可以使用 cron（Linux/macOS）或任务计划程序（Windows）设置定时任务：

```bash
# 每周五下午 6 点自动生成周报
0 18 * * 5 cd /path/to/project && python3 feishu_weekly.py
```

---

## License

MIT
