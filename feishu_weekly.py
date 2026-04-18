#!/usr/bin/env python3
"""
飞书本周日历事件与任务列表获取脚本（含 AI 周报生成 & 自动创建飞书文档）
通过调用 lark-cli 获取本周的日历事件和任务列表，
组装为 Prompt 调用火山方舟 AI 生成正式周报，
并自动创建飞书文档，输出为 Markdown + JSON 格式。
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta


# ============================================================
# 配置区域
# ============================================================

# 火山方舟 AI 配置（OpenAI 兼容 API）
# 也可通过环境变量 ARK_API_KEY / ARK_BASE_URL / ARK_MODEL 覆盖
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.environ.get("ARK_MODEL", "doubao-1-5-pro-256k")

# 飞书文档创建命令
DOCS_CREATE_COMMAND = ["lark-cli", "docs", "+create"]
DOCS_CREATE_MODE = "file"  # 可选: "arg" | "file" | "stdin"


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
                # 截取描述前 200 字符，避免 Prompt 过长
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
            created_at = task.get("created_at", "")
            url = task.get("url", "")

            # 判断是否过期
            status = ""
            if due_at:
                try:
                    due_dt = datetime.fromisoformat(due_at.replace("+08:00", "+08:00"))
                    if due_dt < datetime.now():
                        status = " ⚠️ 已过期"
                except ValueError:
                    pass

            lines.append(f"- {summary}{status}")
            if due_at:
                lines.append(f"  截止: {due_at[:16]}")
            lines.append("")
    except Exception as e:
        lines.append(f"（任务数据解析异常: {e}）")
    return "\n".join(lines)


# ============================================================
# Prompt 构建 & AI 调用（火山方舟 OpenAI 兼容 API）
# ============================================================

WEEKLY_REPORT_PROMPT_TEMPLATE = """你是一位专业的职场助手。请根据以下本周工作数据，生成一份正式周报。

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
) -> str:
    """将日历事件和任务数据提取为结构化信息，组装为 Prompt。"""
    calendar_info = extract_calendar_info(calendar_events)
    tasks_info = extract_tasks_info(tasks)

    return WEEKLY_REPORT_PROMPT_TEMPLATE.format(
        start_date=start_date,
        end_date=end_date,
        calendar_events=calendar_info,
        tasks=tasks_info,
    )


def call_ai(prompt: str) -> str:
    """调用火山方舟 AI（OpenAI 兼容 API）生成周报。"""
    if not ARK_API_KEY:
        print("[错误] 未配置 ARK_API_KEY。请设置环境变量后重试：", file=sys.stderr)
        print("  export ARK_API_KEY='your-api-key'", file=sys.stderr)
        sys.exit(1)

    print(f"🤖 正在调用 AI ({ARK_MODEL}) 生成周报...")

    url = f"{ARK_BASE_URL}/chat/completions"
    payload = json.dumps({
        "model": ARK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一位专业的职场周报助手，擅长从工作数据中提炼关键信息，生成结构清晰、内容充实的周报。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ARK_API_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            return content.strip()
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

def create_feishu_doc(
    title: str,
    content: str,
    mode: str = DOCS_CREATE_MODE,
    docs_cmd: list[str] | None = None,
) -> str:
    """创建飞书文档并返回文档 URL 或 ID。"""
    cmd = docs_cmd or DOCS_CREATE_COMMAND
    print(f"📝 正在创建飞书文档: {title}...")

    if mode == "arg":
        command = cmd + ["--title", title, "--markdown", content]
        result = run_cli_command(command, expect_json=False)
    elif mode == "file":
        import tempfile
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        try:
            tmp_file.write(content)
            tmp_file.close()
            command = cmd + ["--title", title, "--markdown", f"@{tmp_file.name}"]
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
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="飞书本周数据获取 + AI 周报生成 + 自动创建飞书文档"
    )
    parser.add_argument("--no-ai", action="store_true", help="仅获取数据，不调用 AI 生成周报")
    parser.add_argument("--no-doc", action="store_true", help="不自动创建飞书文档")
    parser.add_argument("--docs-cmd", nargs="+", default=None, help="自定义文档创建命令")
    parser.add_argument("--docs-mode", choices=["arg", "file", "stdin"], default=None, help="文档内容传入模式")
    args = parser.parse_args()

    docs_cmd = args.docs_cmd or DOCS_CREATE_COMMAND
    docs_mode = args.docs_mode or DOCS_CREATE_MODE

    # 1. 计算本周日期范围
    start_date, end_date = get_this_week_range()
    print(f"📅 本周范围: {start_date} ~ {end_date}\n")

    # 2. 获取日历事件
    calendar_events = fetch_calendar_events(start_date, end_date)

    # 3. 获取任务列表
    tasks = fetch_tasks()

    # 4. 构建 Prompt 并调用 AI 生成周报
    weekly_report = None
    if not args.no_ai:
        prompt = build_weekly_prompt(start_date, end_date, calendar_events, tasks)
        weekly_report = call_ai(prompt)

    # 5. 自动创建飞书文档
    doc_url = None
    if weekly_report and not args.no_doc:
        doc_title = f"周报 ({start_date} ~ {end_date})"
        doc_content = (
            f"# {doc_title}\n\n{weekly_report}\n\n"
            f"---\n*由 AI 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        )
        doc_url = create_feishu_doc(title=doc_title, content=doc_content, mode=docs_mode, docs_cmd=docs_cmd)

    # 6. 组装最终输出
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
