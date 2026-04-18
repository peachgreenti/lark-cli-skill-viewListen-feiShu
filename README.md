# 飞书消息监听 & AI 分类

基于飞书开放平台和飞书内置 AI 的群聊消息监听、智能分类与每日摘要报告工具。

## 功能特性

| 功能 | 说明 |
|------|------|
| 消息监听 | 通过 lark-cli 实时监听飞书群聊消息（im.message.receive_v1 事件） |
| AI 智能分类 | 使用飞书内置 AI（spark-lite）对消息进行 P0-P3 优先级分类 |
| FAQ 自动回复 | 支持关键词精确匹配和 Jaccard 模糊匹配两种模式 |
| 每日摘要报告 | 定时生成 Markdown 格式的摘要报告，自动创建飞书云文档 |
| 消息过滤 | 支持按 chat_id 白名单过滤，自动忽略机器人消息 |
| 线程安全存储 | 消息存储支持多线程并发，跨天自动清空 |
| 日志管理 | RotatingFileHandler 自动轮转，控制台+文件双输出 |

## 项目结构

```
.
├── listen_feishu.py    # 主脚本（消息监听、AI分类、FAQ匹配、报告生成）
├── config.yaml         # 配置文件
├── faq.yaml            # FAQ 知识库
├── create_doc.py       # 飞书云文档创建脚本
├── README.md           # 使用文档
├── .gitignore          # Git 忽略规则
└── listen_feishu.log   # 运行日志（自动生成）
```

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.10 | 使用了 `dict \| None`、`list[dict]` 等类型注解 |
| PyYAML | >= 6.0 | 配置文件解析 |
| lark-cli | 最新版 | 飞书命令行工具，需提前安装并登录 |

## 快速开始

### 第 1 步：安装 lark-cli

```bash
# 安装飞书命令行工具
npm install -g @larksuiteoapi/lark-cli

# 登录飞书账号
lark-cli login
```

### 第 2 步：安装 Python 依赖

```bash
pip install pyyaml
```

### 第 3 步：下载项目文件

```bash
git clone <your-repo-url>
cd listen_feishu
```

### 第 4 步：编辑配置文件

```bash
# 根据实际需求修改配置
vim config.yaml
```

### 第 5 步：（可选）配置 FAQ 知识库

```bash
# 编辑 FAQ 文件，添加常见问题和回复
vim faq.yaml

# 在 config.yaml 中启用 FAQ
# faq:
#   enabled: true
```

### 第 6 步：启动监听

```bash
# 使用默认配置文件
python listen_feishu.py

# 指定配置文件
python listen_feishu.py --config /path/to/config.yaml
```

## 配置文件详解

### listener - 监听器配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `event_name` | string | `im.message.receive_v1` | 飞书事件名称（固定值） |
| `output_format` | string | `ndjson` | 输出格式，目前仅支持 ndjson |
| `allowed_chat_ids` | list | `[]` | 允许处理的 chat_id 白名单，为空则处理所有 |
| `ignore_bot_messages` | bool | `true` | 是否忽略机器人自身发送的消息 |

### ai - AI 分类配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | `spark-lite` | 飞书内置 AI 模型名称 |
| `timeout` | int | `30` | AI 调用超时时间（秒） |
| `enabled` | bool | `true` | 是否启用 AI 分类 |
| `classification_prompt` | string | （见默认配置） | AI 分类 Prompt，需包含 `{message}` 占位符 |

### faq - FAQ 自动回复配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用 FAQ 自动回复 |
| `file_path` | string | `faq.yaml` | FAQ 知识库文件路径 |
| `match_mode` | string | `keyword` | 匹配模式：`keyword` 或 `fuzzy` |
| `fuzzy_threshold` | float | `0.6` | 模糊匹配阈值（0-1，越大越严格） |

### report - 每日摘要报告配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用每日摘要报告 |
| `hour` | int | `18` | 报告生成时间（小时，24小时制） |
| `minute` | int | `0` | 报告生成时间（分钟） |
| `title_prefix` | string | `飞书消息每日摘要` | 飞书云文档标题前缀 |
| `clear_after_report` | bool | `true` | 报告生成后是否清空当日消息 |
| `create_timeout` | int | `60` | 创建飞书文档超时时间（秒） |

### logging - 日志配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | string | `INFO` | 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `file_path` | string | `listen_feishu.log` | 日志文件路径 |
| `max_size_mb` | int | `10` | 单个日志文件最大大小（MB） |
| `backup_count` | int | `5` | 保留的日志备份文件数量 |
| `format` | string | （见默认配置） | 日志格式字符串 |

## FAQ 格式说明

FAQ 知识库使用 YAML 格式，每条 FAQ 包含以下字段：

```yaml
faqs:
  - keywords:          # 关键词列表（用于 keyword 模式匹配）
      - "关键词1"
      - "关键词2"
    question: "问题描述"  # 问题描述（用于 fuzzy 模式匹配及展示）
    answer: |            # 回复内容（支持多行）
      回复内容第一行
      回复内容第二行
```

### 匹配模式

- **keyword（关键词匹配）**：消息中包含任一 FAQ 的任一关键词即命中，速度快、精度高
- **fuzzy（模糊匹配）**：使用 Jaccard 相似度计算消息与 FAQ 的匹配度，需超过阈值才命中

## AI 优先级定义

| 优先级 | 级别 | 说明 |
|--------|------|------|
| **P0** | 紧急 | 生产环境故障、线上事故、核心服务不可用、数据丢失、安全事件 |
| **P1** | 重要 | 客户反馈的严重问题、即将到期的关键任务、重要会议通知 |
| **P2** | 一般 | 日常开发讨论、代码审查请求、一般性技术问题、团队协作沟通 |
| **P3** | 低优 | 闲聊、表情包、非工作相关话题、已解决问题的后续讨论 |

AI 分类返回的 JSON 格式：

```json
{
  "priority": "P0",
  "reason": "分类理由（一句话）",
  "category": "消息类别"
}
```

## 每日摘要报告

每日在指定时间自动生成摘要报告，包含以下内容：

1. **统计概览**：消息总数、各优先级分布
2. **优先级详情**：按 P0-P3 分组展示每条消息的时间、发送者、内容和分类理由
3. **未分类消息**：AI 分类失败的消息列表
4. **自动创建飞书云文档**：报告以 Markdown 格式写入飞书云文档，方便团队查看

报告标题格式：`{title_prefix} (YYYY-MM-DD)`

## 所需权限

使用本工具需要以下飞书应用权限：

| 权限 | 说明 |
|------|------|
| `im:message` | 接收群聊消息 |
| `im:message:readonly` | 读取消息内容 |
| `ai:chat` | 调用飞书内置 AI |
| `docx:document:create` | 创建飞书云文档 |

请确保 lark-cli 登录的账号拥有以上权限。

## 日志示例

```
2026-04-18 09:00:01 [INFO] listen_feishu - 配置已加载: config.yaml
2026-04-18 09:00:01 [INFO] listen_feishu - 日志已初始化: level=INFO, file=listen_feishu.log
2026-04-18 09:00:01 [INFO] listen_feishu - 报告调度器已启动，每日 18:00 生成摘要
2026-04-18 09:00:01 [INFO] listen_feishu - 启动事件监听: lark-cli event subscribe --event im.message.receive_v1 --output ndjson
2026-04-18 09:00:05 [INFO] listen_feishu - 收到消息 [2026-04-18 09:00:05] ou_xxxx: 生产环境数据库连接超时
2026-04-18 09:00:06 [INFO] listen_feishu - AI 分类: P0 紧急 - 生产环境数据库连接超时属于线上事故
2026-04-18 09:00:10 [INFO] listen_feishu - 收到消息 [2026-04-18 09:00:10] ou_xxxx: 今天中午吃什么
2026-04-18 09:00:11 [INFO] listen_feishu - AI 分类: P3 低优 - 非工作相关的闲聊话题
```

## 常见问题

### Q1: 启动报错 "未找到 lark-cli 命令"

**A**: 请确保 lark-cli 已正确安装并添加到系统 PATH 中。可以通过以下命令验证：

```bash
lark-cli --version
```

如果未安装，请执行 `npm install -g @larksuiteoapi/lark-cli`。

### Q2: AI 分类返回 P3 或分类失败

**A**: 可能原因：
- AI 模型调用超时，可尝试增大 `ai.timeout` 值
- 检查 `classification_prompt` 是否包含 `{message}` 占位符
- 确认 lark-cli 登录的账号有 AI 接口调用权限

### Q3: 每日摘要报告未生成

**A**: 检查以下配置：
- `report.enabled` 是否为 `true`
- `report.hour` 和 `report.minute` 是否设置正确
- 确认 lark-cli 有创建云文档的权限
- 查看日志中是否有 "创建飞书文档失败" 的错误信息

### Q4: 如何只监听特定群聊？

**A**: 在 `config.yaml` 中配置 `listener.allowed_chat_ids`，填入目标群聊的 chat_id：

```yaml
listener:
  allowed_chat_ids:
    - "oc_xxxxxxxxxxxxxxxx"
    - "oc_yyyyyyyyyyyyyyyy"
```

### Q5: FAQ 匹配不准确怎么办？

**A**: 优化建议：
- 使用 `keyword` 模式时，添加更多同义词关键词
- 使用 `fuzzy` 模式时，调整 `fuzzy_threshold`（降低阈值可提高召回率）
- 在 `question` 字段中包含更详细的描述性文本

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    listen_feishu.py                      │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ lark-cli │───>│ 消息解析  │───>│   消息过滤器      │   │
│  │  event   │    │          │    │ (chat_id/机器人)  │   │
│  │ subscribe│    └──────────┘    └────────┬─────────┘   │
│  └──────────┘                              │             │
│                                     ┌──────▼──────┐     │
│                                     │ FAQ 匹配器   │     │
│                                     │(keyword/    │     │
│                                     │ fuzzy)      │     │
│                                     └──────┬──────┘     │
│                                            │             │
│                                     ┌──────▼──────┐     │
│                                     │ AI 分类器    │     │
│                                     │(spark-lite) │     │
│                                     └──────┬──────┘     │
│                                            │             │
│                                     ┌──────▼──────┐     │
│                                     │ 消息存储     │     │
│                                     │(线程安全)    │     │
│                                     └──────┬──────┘     │
│                                            │             │
│  ┌──────────────────┐             ┌──────▼──────┐     │
│  │ 报告调度器        │<────────────│ 定时触发     │     │
│  │ (daemon 线程)    │             └─────────────┘     │
│  │  └─> lark-cli   │                                  │
│  │     docs +create │                                  │
│  └──────────────────┘                                  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 日志系统 (RotatingFileHandler + Console)          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```
