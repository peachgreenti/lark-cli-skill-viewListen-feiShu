#!/usr/bin/env python3
"""
飞书本周日历事件与任务列表获取脚本（含 AI 周报生成 & 自动创建飞书文档）
通过调用 lark-cli 获取本周的日历事件和任务列表，
组装为 Prompt 调用火山方舟 AI 生成正式周报，
并自动创建飞书文档、推送到群聊，输出为 Markdown + JSON 格式。
"""

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone


# ============================================================
# 配置文件加载
# ============================================================

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config(config_path: str | None = None) -> dict:
    """
    加载配置文件，合并环境变量。
    优先级：环境变量 > 配置文件 > 默认值
    """
    path = config_path or DEFAULT_CONFIG_PATH
    config = {}

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            print(f"⚙️  已加载配置文件: {path}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[警告] 配置文件加载失败: {e}，使用默认配置", file=sys.stderr)

    # 环境变量覆盖（最高优先级）
    env_overrides = {
        "ai.model": os.environ.get("ARK_MODEL"),
        "ai.base_url": os.environ.get("ARK_BASE_URL"),
        "ai.api_key": os.environ.get("ARK_API_KEY"),
    }
    for key, val in env_overrides.items():
        if val:
            section, field = key.split(".", 1)
            config.setdefault(section, {})[field] = val

    return config


def get_config_value(config: dict, key_path: str, default=None):
    """从嵌套字典中获取配置值，如 get_config_value(config, 'ai.model', 'default')。"""
    keys = key_path.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
        if val is None:
            return default
    return val


# ============================================================
# 工具函数
# ============================================================

def get_this_week_range() -> tuple[str, str]:
    """计算本周（周一到周日）的日期范围。"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def run_cli_command(
    command: list[str],
    expect_json: bool = True,
    stdin_data: str | None = None,
) -> dict | list | str:
    """执行 lark-cli 命令。"""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, input=stdin_data,
        )
        if expect_json:
            return json.loads(result.stdout.strip())
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[错误] 命令执行失败: {' '.join(command)}", file=sys.stderr)
        print(f"  返回码: {e.returncode}", file=sys.stderr)
        if e.stderr:
            print(f"  错误信息: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[错误] JSON 解析失败: {e}", file=sys.stderr)
        print(f"  原始输出: {result.stdout[:500]}", file=sys.stderr)
        sys.exit(1)


# ============================================================
# 数据获取
# ============================================================

def fetch_calendar_events(start_date: str, end_date: str) -> dict | list:
    """获取本周日历事件。"""
    print(f"📅 正在获取日历事件 ({start_date} ~ {end_date})...")
    return run_cli_command([
        "lark-cli", "calendar", "+agenda",
        "--start", start_date, "--end", end_date,
    ])


def fetch_tasks() -> dict | list:
    """获取任务列表。"""
    print("✅ 正在获取任务列表...")
    return run_cli_command(["lark-cli", "task", "+get-my-tasks"])


# ============================================================
# 排除规则过滤
# ============================================================

def should_exclude(text: str, keywords: list[str]) -> bool:
    """检查文本是否匹配任一排除关键词（支持通配符 *）。"""
    if not keywords or not text:
        return False
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if "*" in kw or "?" in kw:
            if fnmatch.fnmatch(text, kw):
                return True
        elif kw.lower() in text.lower():
            return True
    return False


def filter_calendar_events(raw: dict | list, config: dict) -> dict | list:
    """根据排除规则过滤日历事件。"""
    keywords = get_config_value(config, "exclude.calendar_keywords", [])
    organizers = get_config_value(config, "exclude.calendar_organizers", [])

    if not keywords and not organizers:
        return raw

    events = raw.get("data", []) if isinstance(raw, dict) else raw
    if not isinstance(events, list):
        return raw

    filtered = []
    excluded_count = 0
    for ev in events:
        summary = ev.get("summary", "")
        organizer = ev.get("event_organizer", {}).get("display_name", "")

        if should_exclude(summary, keywords):
            excluded_count += 1
            print(f"  🔕 排除事件: {summary}")
            continue
        if should_exclude(organizer, organizers):
            excluded_count += 1
            print(f"  🔕 排除事件（组织者）: {summary} (by {organizer})")
            continue
        filtered.append(ev)

    if excluded_count > 0:
        print(f"  📊 日历事件: 原始 {len(events)} 条 → 过滤后 {len(filtered)} 条（排除 {excluded_count} 条）")

    result = dict(raw) if isinstance(raw, dict) else {"data": events}
    if isinstance(raw, dict):
        result["data"] = filtered
        if "meta" in result and isinstance(result["meta"], dict):
            result["meta"]["count"] = len(filtered)
    return result


def filter_tasks(raw: dict | list, config: dict) -> dict | list:
    """根据排除规则过滤任务列表。"""
    keywords = get_config_value(config, "exclude.task_keywords", [])
    hide_completed = get_config_value(config, "exclude.hide_completed_tasks", False)

    if not keywords and not hide_completed:
        return raw

    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return raw

    filtered = []
    excluded_count = 0
    for task in items:
        summary = task.get("summary", "")
        completed = task.get("completed", False)

        if completed and hide_completed:
            excluded_count += 1
            continue
        if should_exclude(summary, keywords):
            excluded_count += 1
            print(f"  🔕 排除任务: {summary}")
            continue
        filtered.append(task)

    if excluded_count > 0:
        print(f"  📊 任务列表: 原始 {len(items)} 条 → 过滤后 {len(filtered)} 条（排除 {excluded_count} 条）")

    result = dict(raw) if isinstance(raw, dict) else {"data": {"items": items}}
    if isinstance(raw, dict) and isinstance(result.get("data"), dict):
        result["data"]["items"] = filtered
    return result


# ============================================================
# 数据提取 — 从原始 JSON 中提取关键信息，构建结构化 Prompt
# ============================================================

def extract_calendar_info(raw: dict | list) -> str:
    """从日历事件原始数据中提取关键信息，生成结构化文本。"""
    lines = []
    try:
        events = raw.get("data", []) if isinstance(raw, dict) else raw
        if not events:
            return "（本周无日历事件）"

        for ev in events:
            summary = ev.get("summary", "无标题")
            start = ev.get("start_time", {})
            end = ev.get("end_time", {})
            start_str = start.get("datetime", "")[:16] if start else ""
            end_str = end.get("datetime", "")[:16] if end else ""
            organizer = ev.get("event_organizer", {})
            organizer_name = organizer.get("display_name", "未知")
            desc = ev.get("description", "").strip()
            vchat = ev.get("vchat", {})
            meeting_url = vchat.get("meeting_url", "")

            lines.append(f"- **{summary}**")
            lines.append(f"  时间: {start_str} ~ {end_str}")
            lines.append(f"  组织者: {organizer_name}")
            if meeting_url:
                lines.append(f"  会议链接: {meeting_url}")
            if desc:
                desc_short = desc[:200] + ("..." if len(desc) > 200 else "")
                lines.append(f"  描述: {desc_short}")
            lines.append("")
    except Exception as e:
        lines.append(f"（日历数据解析异常: {e}）")
    return "\n".join(lines)


def extract_tasks_info(raw: dict | list) -> str:
    """从任务列表原始数据中提取关键信息，生成结构化文本。"""
    lines = []
    try:
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            return "（无待办任务）"

        for task in items:
            summary = task.get("summary", "无标题")
            due_at = task.get("due_at", "")

            status = ""
            if due_at:
                try:
                    due_dt = datetime.fromisoformat(due_at)
                    now_dt = datetime.now(timezone.utc).astimezone(due_dt.tzinfo)
                    if due_dt < now_dt:
                        status = " ⚠️ 已过期"
                except (ValueError, TypeError):
                    pass

            lines.append(f"- {summary}{status}")
            if due_at:
                lines.append(f"  截止: {due_at[:16]}")
            lines.append("")
    except Exception as e:
        lines.append(f"（任务数据解析异常: {e}）")
    return "\n".join(lines)


# ============================================================
# Prompt 构建 & AI 调用
# ============================================================

BUILTIN_PROMPT_TEMPLATE = """你是一位专业的职场助手。请根据以下本周工作数据，生成一份正式周报。

## 时间范围
{start_date} ~ {end_date}

## 本周日历事件
{calendar_events}

## 待办任务
{tasks}

## 输出要求
请严格按以下结构生成周报（Markdown 格式），每个板块都要有实质内容：

### 一、本周工作总结
用 2-3 句话概括本周主要工作方向和整体进展。

### 二、重点工作与成果
按项目/主题分类，逐条列出：
- 会议名称、时间、关键内容
- 重要的阶段性成果或交付物
- 值得关注的亮点

### 三、进行中的工作
列出正在持续推进的事项及其当前状态。

### 四、待办与下周计划
- 列出未完成的任务（标注是否已过期）
- 基于本周工作进展，提出 2-3 条下周工作建议

### 五、风险与协调事项（如有）

## 约束
- 只使用上面提供的数据，不要编造不存在的信息
- 语言简洁专业，使用要点式表达
- 如果某个板块确实没有数据，写"暂无相关数据"即可，不要强行填充
- 过期的任务要特别标注"""


def build_weekly_prompt(
    start_date: str,
    end_date: str,
    calendar_events: dict | list,
    tasks: dict | list,
    config: dict,
    template_path: str | None = None,
) -> str:
    """将日历事件和任务数据提取为结构化信息，组装为 Prompt。"""
    calendar_info = extract_calendar_info(calendar_events)
    tasks_info = extract_tasks_info(tasks)

    # 优先级：命令行 --template > 配置文件 custom_prompt > 内置模板
    if template_path and os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read().strip()
        print(f"📝 已加载自定义模板: {template_path}")
    else:
        custom_prompt = get_config_value(config, "report.custom_prompt", "")
        template = custom_prompt.strip() if custom_prompt else BUILTIN_PROMPT_TEMPLATE

    return template.format(
        start_date=start_date,
        end_date=end_date,
        start=start_date,
        end=end_date,
        calendar_events=calendar_info,
        tasks=tasks_info,
    )


def call_ai(prompt: str, config: dict) -> str:
    """调用火山方舟 AI（OpenAI 兼容 API）生成周报。"""
    api_key = get_config_value(config, "ai.api_key", "")
    base_url = get_config_value(config, "ai.base_url", "https://ark.cn-beijing.volces.com/api/v3")
    model = get_config_value(config, "ai.model", "doubao-1-5-pro-256k")
    temperature = float(get_config_value(config, "ai.temperature", 0.3))
    max_tokens = int(get_config_value(config, "ai.max_tokens", 4096))

    if not api_key:
        print("[错误] 未配置 ARK_API_KEY。请设置环境变量或在 config.json 中配置 ai.api_key", file=sys.stderr)
        sys.exit(1)

    print(f"🤖 正在调用 AI ({model}) 生成周报...")

    url = f"{base_url}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位专业的职场周报助手，擅长从工作数据中提炼关键信息，生成结构清晰、内容充实的周报。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[错误] AI API 请求失败 (HTTP {e.code})", file=sys.stderr)
        print(f"  响应: {body[:500]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[错误] AI API 连接失败: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, IndexError) as e:
        print(f"[错误] AI API 响应格式异常: {e}", file=sys.stderr)
        sys.exit(1)


# ============================================================
# 飞书文档创建
# ============================================================

def create_feishu_doc(title: str, content: str, mode: str = "file") -> str:
    """创建飞书文档并返回文档 URL 或 ID。"""
    cmd = ["lark-cli", "docs", "+create"]
    print(f"📝 正在创建飞书文档: {title}...")

    if mode == "arg":
        command = cmd + ["--title", title, "--markdown", content]
        result = run_cli_command(command, expect_json=False)
    elif mode == "file":
        import tempfile
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8", dir=os.getcwd()
        )
        try:
            tmp_file.write(content)
            tmp_file.close()
            command = cmd + ["--title", title, "--markdown", f"@{os.path.basename(tmp_file.name)}"]
            result = run_cli_command(command, expect_json=False)
        finally:
            os.unlink(tmp_file.name)
    elif mode == "stdin":
        command = cmd + ["--title", title, "--markdown", "-"]
        result = run_cli_command(command, expect_json=False, stdin_data=content)
    else:
        print(f"[错误] 不支持的文档创建模式: {mode}", file=sys.stderr)
        sys.exit(1)

    return result


# ============================================================
# 消息推送
# ============================================================

def send_to_chat(text: str, config: dict, send_to: str | None = None) -> str | None:
    """将周报推送到飞书群聊或用户。send_to 可覆盖配置文件中的目标。"""
    # 优先使用命令行 --send-to
    target = send_to or get_config_value(config, "notify.chat_id", "") or get_config_value(config, "notify.user_id", "")
    send_as = get_config_value(config, "notify.send_as", "user")

    if not target:
        return None

    print(f"💬 正在发送周报到飞书 ({target[:8]}...)...")

    # 自动判断目标类型
    command = ["lark-cli", "im", "+messages-send", "--as", send_as]
    if target.startswith("oc_"):
        command += ["--chat-id", target]
    elif target.startswith("ou_"):
        command += ["--user-id", target]
    else:
        # 默认当作 chat_id
        command += ["--chat-id", target]

    command += ["--text", text]

    result = run_cli_command(command, expect_json=False)
    return result


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="飞书本周数据获取 + AI 周报生成 + 自动创建飞书文档"
    )
    parser.add_argument("--no-ai", action="store_true", help="仅获取数据，不调用 AI 生成周报")
    parser.add_argument("--no-doc", action="store_true", help="不自动创建飞书文档")
    parser.add_argument("--no-notify", action="store_true", help="不发送消息到群聊")
    parser.add_argument("--dry-run", action="store_true", help="预览模式：仅获取和过滤数据，不调用 AI/创建文档/推送")
    parser.add_argument("--send-to", default=None, help="指定推送目标（群聊 ID 如 oc_xxx 或用户 ID 如 ou_xxx），覆盖配置文件")
    parser.add_argument("--template", default=None, help="自定义 Prompt 模板文件路径（Markdown 格式，支持占位符）")
    parser.add_argument("--config", default=None, help="指定配置文件路径（默认: ./config.json）")
    parser.add_argument("--docs-mode", choices=["arg", "file", "stdin"], default=None, help="文档内容传入模式")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    docs_mode = args.docs_mode or get_config_value(config, "docs.mode", "file")

    # dry-run 模式：隐含 --no-ai --no-doc --no-notify
    if args.dry_run:
        args.no_ai = True
        args.no_doc = True
        args.no_notify = True
        print("🔍 预览模式（dry-run）：仅获取和过滤数据\n")

    # 1. 计算本周日期范围
    start_date, end_date = get_this_week_range()
    print(f"📅 本周范围: {start_date} ~ {end_date}\n")

    # 2. 获取日历事件
    calendar_events = fetch_calendar_events(start_date, end_date)

    # 3. 获取任务列表
    tasks = fetch_tasks()

    # 4. 应用排除规则
    calendar_events = filter_calendar_events(calendar_events, config)
    tasks = filter_tasks(tasks, config)

    # 5. dry-run: 输出过滤后的数据摘要并退出
    if args.dry_run:
        print("\n" + "=" * 60)
        print("📊 数据预览（dry-run）")
        print("=" * 60)
        calendar_info = extract_calendar_info(calendar_events)
        tasks_info = extract_tasks_info(tasks)
        print(f"\n📅 日历事件:\n{calendar_info}")
        print(f"\n✅ 任务列表:\n{tasks_info}")
        print(f"\n💡 完整运行命令: python3 {os.path.basename(__file__)}")
        return

    # 6. 构建 Prompt 并调用 AI 生成周报
    weekly_report = None
    if not args.no_ai:
        prompt = build_weekly_prompt(start_date, end_date, calendar_events, tasks, config, template_path=args.template)
        weekly_report = call_ai(prompt, config)

    # 6. 自动创建飞书文档
    doc_url = None
    if weekly_report and not args.no_doc:
        title_pattern = get_config_value(config, "report.title_pattern", "周报 ({start} ~ {end})")
        doc_title = title_pattern.format(start=start_date, end=end_date)
        doc_content = (
            f"# {doc_title}\n\n{weekly_report}\n\n"
            f"---\n*由 AI 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        )
        doc_url = create_feishu_doc(title=doc_title, content=doc_content, mode=docs_mode)

    # 7. 发送消息到群聊
    notify_result = None
    if weekly_report and not args.no_notify:
        notify_text = (
            f"📋 {title_pattern.format(start=start_date, end=end_date)}\n\n"
            f"{weekly_report}"
        )
        notify_result = send_to_chat(notify_text, config, send_to=args.send_to)

    # 8. 组装最终输出
    output = {
        "week_range": {"start": start_date, "end": end_date},
        "calendar_events": calendar_events,
        "tasks": tasks,
        "fetched_at": datetime.now().isoformat(),
    }
    if weekly_report:
        output["weekly_report"] = weekly_report
    if doc_url:
        output["feishu_doc"] = doc_url
    if notify_result:
        output["notify_result"] = notify_result

    # ---- Markdown 输出 ----
    if weekly_report:
        print("\n" + "=" * 60)
        print("📋 AI 生成的周报")
        print("=" * 60)
        print(weekly_report)

    if doc_url:
        print("\n" + "=" * 60)
        print("🔗 飞书文档")
        print("=" * 60)
        print(doc_url)

    if notify_result:
        print("\n" + "=" * 60)
        print("💬 消息推送")
        print("=" * 60)
        print("已发送")

    # ---- JSON 保存 ----
    json_output = json.dumps(output, ensure_ascii=False, indent=2)
    output_file = f"feishu_weekly_{start_date}_{end_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json_output)
    print(f"\n💾 结果已保存到: {output_file}")

    # ---- Markdown 周报文件 ----
    if weekly_report:
        md_file = f"weekly_report_{start_date}_{end_date}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# 周报 ({start_date} ~ {end_date})\n\n{weekly_report}\n\n")
            f.write(f"---\n*由 AI 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
        print(f"📄 周报已保存到: {md_file}")


if __name__ == "__main__":
    main()
