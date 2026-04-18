# 飞书智能周报工具

> 自动获取飞书日历事件和任务列表，调用 AI 生成正式周报，一键创建飞书文档并推送到群聊。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 目录

- [功能介绍](#功能介绍)
- [工作流程](#工作流程)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [快速开始](#快速开始)
- [命令行参数](#命令行参数)
- [配置文件](#配置文件)
- [使用示例](#使用示例)
- [输出说明](#输出说明)
- [定时任务](#定时任务)
- [常见问题](#常见问题)

---

## 功能介绍

| 功能 | 说明 |
|------|------|
| 📅 日历事件获取 | 自动获取本周（周一至周日）的飞书日历事件 |
| ✅ 任务列表获取 | 获取当前飞书待办任务列表 |
| 🤖 AI 周报生成 | 调用火山方舟（豆包大模型）生成正式周报 |
| 📝 飞书文档创建 | 将周报自动发布为飞书云文档 |
| 💬 群聊推送 | 将周报发送到指定飞书群聊或用户 |
| 🔍 数据过滤 | 按关键词/组织者过滤日历事件和任务 |
| 📋 预览模式 | dry-run 预览过滤后的数据，不调用 AI |
| 📝 自定义模板 | 支持自定义 Prompt 模板文件 |
| 📊 日志系统 | 支持 DEBUG 详细日志和日志文件输出 |

---

## 工作流程

```
获取本周日历事件 + 任务列表
        │
        ▼
   应用排除规则过滤
        │
        ▼
  提取关键信息 → 构建 Prompt → 调用 AI 生成周报
        │
        ├──▶ 创建飞书云文档
        ├──▶ 推送到群聊/用户
        └──▶ 保存本地文件（JSON + Markdown）
```

---

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.10 | 使用了 `tuple[str, str]` 等类型语法 |
| lark-cli | 最新版 | 飞书命令行工具 |
| 火山方舟 API Key | — | 用于 AI 周报生成（豆包大模型） |

> 脚本零外部依赖，仅使用 Python 标准库（`urllib`、`logging`、`subprocess` 等）。

---

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/peachgreenti/lark-cli-skill-weekly-report.git
cd lark-cli-skill-weekly-report
```

### 2. 安装 lark-cli

```bash
npm install -g @larksuite/cli
npx skills add larksuite/cli -y -g

# 配置并登录
lark-cli config init
lark-cli auth login --recommend
```

### 3. 配置火山方舟 API

1. 打开 [火山方舟控制台](https://console.volcengine.com/ark)
2. 创建 **推理接入点**（推荐模型：`Doubao-1.5-pro`），获取接入点 ID（`ep-xxxxxxxx`）
3. 在 [API Key 管理](https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey) 创建 API Key

### 4. 配置项目

```bash
# 复制示例配置文件
cp config.example.json config.json

# 编辑配置，填入你的 API Key 和接入点 ID
vim config.json
```

### 5. 验证

```bash
python3 feishu_weekly.py --help
python3 feishu_weekly.py --dry-run
```

---

## 快速开始

```bash
# 完整运行：获取数据 → AI 生成周报 → 创建飞书文档 → 推送群聊
python3 feishu_weekly.py

# 仅预览数据（不调用 AI）
python3 feishu_weekly.py --dry-run

# 预览 + 详细日志
python3 feishu_weekly.py --dry-run -v

# 生成周报但不创建文档、不推送
python3 feishu_weekly.py --no-doc --no-notify

# 指定推送目标
python3 feishu_weekly.py --send-to oc_xxxxxxxxxxxxxxxx

# 使用自定义 Prompt 模板
python3 feishu_weekly.py --template my_prompt.md
```

---

## 命令行参数

```
usage: feishu_weekly.py [-h] [--no-ai] [--no-doc] [--no-notify] [--dry-run]
                        [--send-to SEND_TO] [--template TEMPLATE]
                        [--config CONFIG] [--docs-mode {arg,file,stdin}]
                        [-v] [--log-file LOG_FILE]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--no-ai` | 仅获取数据，不调用 AI 生成周报 | 关闭 |
| `--no-doc` | 不自动创建飞书文档 | 关闭 |
| `--no-notify` | 不发送消息到群聊 | 关闭 |
| `--dry-run` | 预览模式：仅获取和过滤数据 | 关闭 |
| `--send-to` | 指定推送目标（`oc_xxx` 群聊 / `ou_xxx` 用户） | 配置文件 |
| `--template` | 自定义 Prompt 模板文件路径 | 内置模板 |
| `--config` | 指定配置文件路径 | `./config.json` |
| `--docs-mode` | 文档创建模式：`arg` / `file` / `stdin` | `file` |
| `-v, --verbose` | 详细日志输出（DEBUG 级别） | INFO |
| `--log-file` | 日志输出到文件 | 无 |

---

## 配置文件

配置文件 `config.json` 支持以下配置项（也可参考 [config.example.json](config.example.json)）：

### AI 配置

```json
{
  "ai": {
    "model": "ep-20260418212629-26ftq",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "ark-xxxxxxxx",
    "temperature": 0.3,
    "max_tokens": 4096
  }
}
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `model` | 火山方舟接入点 ID | `doubao-1-5-pro-256k` |
| `base_url` | API 基础 URL | `https://ark.cn-beijing.volces.com/api/v3` |
| `api_key` | API Key（也可用 `ARK_API_KEY` 环境变量） | — |
| `temperature` | 生成温度（0-1，越低越确定性） | `0.3` |
| `max_tokens` | 最大输出 Token 数 | `4096` |

### 周报配置

```json
{
  "report": {
    "title_pattern": "周报 ({start} ~ {end})",
    "custom_prompt": ""
  }
}
```

| 字段 | 说明 |
|------|------|
| `title_pattern` | 文档标题格式，支持 `{start}` `{end}` 占位符 |
| `custom_prompt` | 自定义 Prompt 模板（留空用内置模板），支持 `{start_date}` `{end_date}` `{calendar_events}` `{tasks}` 占位符 |

### 推送配置

```json
{
  "notify": {
    "chat_id": "",
    "user_id": "",
    "send_as": "user"
  }
}
```

| 字段 | 说明 |
|------|------|
| `chat_id` | 飞书群聊 ID（`oc_xxx`），与 `user_id` 二选一 |
| `user_id` | 飞书用户 ID（`ou_xxx`），与 `chat_id` 二选一 |
| `send_as` | 发送身份：`user`（以用户身份）或 `bot`（以机器人身份） |

### 排除规则

```json
{
  "exclude": {
    "calendar_keywords": ["午休", "站会"],
    "calendar_organizers": [],
    "task_keywords": ["打卡", "考勤"],
    "hide_completed_tasks": true
  }
}
```

| 字段 | 说明 |
|------|------|
| `calendar_keywords` | 排除包含这些关键词的日历事件（支持通配符 `*`） |
| `calendar_organizers` | 排除这些组织者的事件 |
| `task_keywords` | 排除包含这些关键词的任务 |
| `hide_completed_tasks` | 是否隐藏已完成的任务 |

### 文档创建配置

```json
{
  "docs": {
    "mode": "file"
  }
}
```

| 模式 | 说明 |
|------|------|
| `arg` | 通过命令行参数传入 `--markdown "内容"` |
| `file` | 通过文件传入 `--markdown @file.md`（默认，推荐） |
| `stdin` | 通过管道传入 `echo "内容" \| --markdown -` |

### 配置优先级

```
命令行参数 > 环境变量 > config.json > 内置默认值
```

---

## 使用示例

### 示例 1：基础使用

```bash
# 首次运行，预览数据
python3 feishu_weekly.py --dry-run -v

# 确认数据无误后，完整运行
python3 feishu_weekly.py
```

### 示例 2：过滤无关数据

在 `config.json` 中配置排除规则：

```json
{
  "exclude": {
    "calendar_keywords": ["午休", "1:1", "站会"],
    "task_keywords": ["打卡", "考勤", "日报"],
    "hide_completed_tasks": true
  }
}
```

### 示例 3：推送到群聊

```bash
# 命令行指定
python3 feishu_weekly.py --send-to oc_xxxxxxxxxxxxxxxx

# 或在 config.json 中配置
```

### 示例 4：自定义 Prompt 模板

创建 `my_prompt.md`：

```markdown
你是一位技术团队的周报助手。请根据以下数据生成简洁的技术周报。

## 时间范围
{start_date} ~ {end_date}

## 本周日历事件
{calendar_events}

## 待办任务
{tasks}

请输出：
1. 本周完成事项
2. 进行中的工作
3. 下周计划
```

```bash
python3 feishu_weekly.py --template my_prompt.md
```

### 示例 5：定时自动运行

```bash
# 每周五下午 6 点自动生成周报并推送
0 18 * * 5 cd /path/to/project && python3 feishu_weekly.py --log-file weekly.log
```

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
  "calendar_events": { "ok": true, "data": [...] },
  "tasks": { "ok": true, "data": { "items": [...] } },
  "weekly_report": "# 周报\n\n...",
  "feishu_doc": "https://xxx.feishu.cn/docx/xxx",
  "fetched_at": "2026-04-18T10:30:00"
}
```

---

## 日志系统

```bash
# 普通日志（INFO 级别）
python3 feishu_weekly.py

# 详细日志（DEBUG 级别，显示命令详情和过滤明细）
python3 feishu_weekly.py -v

# 日志同时输出到文件
python3 feishu_weekly.py --log-file weekly.log
```

日志输出示例：

```
22:16:51 INFO  已加载配置文件: ./config.json
22:16:51 INFO  本周范围: 2026-04-13 ~ 2026-04-19
22:16:51 INFO  正在获取日历事件 (2026-04-13 ~ 2026-04-19)...
22:16:55 INFO  正在获取任务列表...
22:17:00 INFO  任务列表: 原始 6 条 → 过滤后 2 条（排除 4 条）
22:17:00 INFO  正在调用 AI (ep-20260418212629-26ftq) 生成周报...
22:17:05 INFO  AI 周报生成成功（1234 字符）
22:17:06 INFO  正在创建飞书文档: 周报 (2026-04-13 ~ 2026-04-19) (模式: file)
22:17:08 INFO  飞书文档创建成功
22:17:08 INFO  结果已保存到: feishu_weekly_2026-04-13_2026-04-19.json
22:17:08 INFO  全部完成 ✓
```

---

## 所需权限

| 权限 | 说明 |
|------|------|
| `calendar:calendar:read` | 读取日历事件 |
| `task:task:read` | 读取任务列表 |
| `docx:document:create` | 创建飞书云文档 |
| `im:message.send_as_user` | 以用户身份发送消息（可选） |

登录时使用推荐权限即可覆盖：

```bash
lark-cli auth login --recommend
```

---

## 常见问题

### Q: 运行报错 `command not found: lark-cli`

```bash
which lark-cli
lark-cli --version
```

### Q: AI 报错 `HTTP 401`

API Key 无效或过期，请检查 `config.json` 中的 `ai.api_key` 或环境变量 `ARK_API_KEY`。

### Q: AI 报错 `HTTP 404` 模型不存在

需要使用火山方舟的 **接入点 ID**（`ep-xxxxxxxx` 格式），而非模型名称。请到[火山方舟控制台](https://console.volcengine.com/ark/region:ark+cn-beijing/model)创建接入点。

### Q: 文档创建失败

尝试切换文档创建模式：

```bash
python3 feishu_weekly.py --docs-mode stdin
```

### Q: 消息推送失败

确认已授权 `im:message.send_as_user` 权限：

```bash
lark-cli auth login --scope "im:message.send_as_user"
```

### Q: 如何只获取数据不生成周报？

```bash
python3 feishu_weekly.py --no-ai
```

---

## License

MIT
