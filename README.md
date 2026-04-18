# lark-cli-skill-viewListen-feiShu

> 飞书消息监听 + AI 智能分类 + 每日摘要报告

基于 [lark-cli](https://github.com/larksuite/node-cli) 的飞书群聊消息实时监听工具，集成火山引擎 ARK（豆包大模型）进行 AI 智能分类，支持 FAQ 自动匹配与每日摘要报告自动生成。

## 项目信息

- **项目名**：lark-cli-skill-viewListen-feiShu
- **GitHub 仓库**：https://github.com/peachgreenti/lark-cli-skill-viewListen-feiShu
- **作者**：peachgreenti
- **License**：MIT

## 项目文件结构

```
├── listen_feishu.py    # 主程序：实时监听 + AI 分类 + 每日摘要
├── msg_assistant.py    # 环境检查脚本（dry-run）
├── demo.py             # 端到端演示脚本（手动生成摘要报告）
├── config.yaml         # 配置文件
├── faq.yaml            # FAQ 知识库
├── .gitignore          # Git 忽略规则
└── README.md           # 使用文档
```

## 核心功能

1. **实时消息监听**：通过 lark-cli WebSocket 监听飞书群聊消息
2. **AI 智能分类**：使用火山引擎 ARK（豆包大模型）对消息进行 P0-P3 优先级分类
3. **FAQ 自动匹配**：基于关键词/模糊匹配的 FAQ 知识库自动回复
4. **每日摘要报告**：定时生成 Markdown 摘要并自动创建飞书云文档
5. **环境自检**：一键检查所有依赖和配置是否正常

## AI 优先级定义

| 优先级 | 级别 | 说明 |
|--------|------|------|
| **P0** | 紧急 | 生产环境故障、线上事故、安全事件 |
| **P1** | 重要 | 客户严重问题、关键任务、紧急需求 |
| **P2** | 一般 | 日常开发讨论、项目沟通 |
| **P3** | 低优 | 闲聊、非工作话题 |

## 环境要求

- Python 3.10+
- lark-cli v1.0.13+
- PyYAML
- 火山引擎 ARK API Key + Endpoint ID
- 飞书开放平台机器人（已配置 `im.message.receive_v1` 事件订阅）

## 快速开始（6 步）

### 第 1 步：安装 lark-cli

```bash
npm install -g @larksuite/cli
lark-cli auth login --recommend
```

### 第 2 步：配置环境变量

```bash
echo "export ARK_API_KEY='your-ark-api-key'" > ~/.feishu_weekly_env
source ~/.feishu_weekly_env
```

### 第 3 步：克隆项目

```bash
git clone https://github.com/peachgreenti/lark-cli-skill-viewListen-feiShu.git
cd lark-cli-skill-viewListen-feiShu
```

### 第 4 步：安装 Python 依赖

```bash
pip install pyyaml
```

### 第 5 步：配置 config.yaml

编辑 `config.yaml`，填写以下必要配置：

- `listener.allowed_chat_ids`：要监听的群聊 ID
- `ai.ark_endpoint_id`：火山引擎 ARK 推理接入点 ID

### 第 6 步：环境检查

```bash
source ~/.feishu_weekly_env && python3 msg_assistant.py --dry-run
```

## 使用方式

### 启动实时监听

```bash
source ~/.feishu_weekly_env && python3 listen_feishu.py
```

### 手动生成摘要报告

```bash
source ~/.feishu_weekly_env && python3 demo.py
```

### 环境检查

```bash
source ~/.feishu_weekly_env && python3 msg_assistant.py --dry-run
```

### 后台常驻运行

```bash
source ~/.feishu_weekly_env && nohup python3 listen_feishu.py > /dev/null 2>&1 &
```

## 配置文件详解

### listener 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `event_name` | string | `im.message.receive_v1` | 监听的飞书事件 |
| `output_format` | string | `ndjson` | 输出格式 |
| `allowed_chat_ids` | list | `[]` | 要监听的群聊 ID 列表（空=所有群） |
| `ignore_bot_messages` | bool | `true` | 是否忽略机器人消息 |

### ai 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | string | `ark` | AI 提供商：`ark` / `lark` |
| `model` | string | `spark-lite` | 飞书内置 AI 模型（`provider=lark` 时） |
| `timeout` | int | `30` | API 调用超时（秒） |
| `enabled` | bool | `true` | 是否启用 AI 分类 |
| `ark_api_key` | string | `""` | ARK API Key（也可用环境变量 `ARK_API_KEY`） |
| `ark_endpoint_id` | string | `""` | ARK 推理接入点 ID |
| `ark_base_url` | string | `https://ark.cn-beijing.volces.com/api/v3` | ARK API 地址 |
| `classification_prompt` | string | （见默认） | AI 分类提示词 |

### faq 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用 FAQ |
| `file_path` | string | `faq.yaml` | FAQ 文件路径 |
| `match_mode` | string | `keyword` | 匹配模式：`keyword` / `fuzzy` |
| `fuzzy_threshold` | float | `0.6` | 模糊匹配阈值 |

### report 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用每日报告 |
| `hour` | int | `18` | 生成时间（小时） |
| `minute` | int | `0` | 生成时间（分钟） |
| `title_prefix` | string | `飞书消息每日摘要` | 报告标题前缀 |
| `clear_after_report` | bool | `true` | 生成后是否清空消息记录 |
| `create_timeout` | int | `60` | 文档创建超时（秒） |

### logging 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | string | `INFO` | 日志级别 |
| `file_path` | string | `listen_feishu.log` | 日志文件路径 |
| `max_size_mb` | int | `10` | 单个日志文件最大大小 |
| `backup_count` | int | `5` | 保留的日志备份数量 |
| `format` | string | （见默认） | 日志格式 |

## FAQ 知识库格式

在 `faq.yaml` 中按以下格式配置 FAQ 条目：

```yaml
faqs:
  - question: "如何部署上线？"
    keywords: ["部署", "上线", "发布", "deploy"]
    answer: "部署上线流程：1. 提交代码并合并到 main 分支..."
```

- `question`：FAQ 问题描述
- `keywords`：用于关键词匹配的关键词列表
- `answer`：对应的回答内容

## 飞书开放平台配置

1. 打开飞书开放平台应用管理页面：`https://open.feishu.cn/app/{app_id}/event`
2. 添加事件订阅：`im.message.receive_v1`
3. 开通权限：`im:message`、`im:message.group_at_msg`
4. 发布新版本

## 技术架构

```
飞书群聊消息
    ↓ (WebSocket)
lark-cli event +subscribe
    ↓ (NDJSON)
listen_feishu.py
    ├── 消息过滤（群聊ID / 机器人消息）
    ├── FAQ 匹配（关键词 / 模糊）
    ├── AI 分类（ARK 豆包大模型 / 飞书内置 AI）
    ├── 消息存储（线程安全）
    └── 每日摘要报告
         ├── Markdown 生成
         └── 飞书云文档创建（lark-cli docs +create）
```

## 常见问题

### Q: 收不到消息事件？

确认机器人已在飞书开放平台后台配置 `im.message.receive_v1` 事件订阅，且已发布新版本。群聊中需要 @机器人 才会触发事件。

### Q: AI 分类返回 P2 fallback？

检查 `ARK_API_KEY` 和 `ark_endpoint_id` 是否正确配置，可通过以下命令验证：

```bash
python3 msg_assistant.py --dry-run
```

### Q: 如何监听所有群消息（不只是 @消息）？

在飞书开放平台后台，将 `im.message.receive_v1` 事件配置为接收所有群消息。

### Q: 每日报告没有生成？

确认 `config.yaml` 中 `report.enabled` 为 `true`，且脚本在报告时间点（默认 18:00）正在运行。

### Q: 如何查看运行日志？

```bash
tail -f listen_feishu.log
```

## License

MIT
