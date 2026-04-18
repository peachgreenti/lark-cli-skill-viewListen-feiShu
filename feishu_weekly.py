#!/usr/bin/env python3
"""
飞书本周日历事件与任务列表获取脚本（含 AI 周报生成 & 自动创建飞书文档）
通过调用 lark-cli 获取本周的日历事件和任务列表，
组装为 Prompt 调用飞书 AI 生成正式周报，
并自动创建飞书文档，输出为 Markdown + JSON 格式。
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta


# ============================================================
# 配置区域 - 可根据实际 lark-cli 命令格式调整
# ============================================================

# 飞书 AI 调用命令
AI_COMMAND = ["lark-cli", "ai"]

# 飞书文档创建命令
# 实际参数格式：
#   lark-cli docs +create --title "标题" --markdown "内容"
#   lark-cli docs +create --title "标题" --markdown @file.md
#   lark-cli docs +create --title "标题" --markdown -   (stdin)
DOCS_CREATE_COMMAND = ["lark-cli", "docs", "+create"]
DOCS_CREATE_MODE = "file"  # 可选: "arg" | "file" | "stdin"


# ============================================================
# 工具函数
# ============================================================

def get_this_week_range() -> tuple[str, str]:
    """计算本周（周一到周日）的日期范围，返回 (start_date, end_date) 字符串。"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    start_date = monday.strftime("%Y-%m-%d")
    end_date = sunday.strftime("%Y-%m-%d")
    return start_date, end_date


def run_cli_command(
    command: list[str],
    expect_json: bool = True,
    stdin_data: str | None = None,
) -> dict | list | str:
    """
    执行 lark-cli 命令。
    - expect_json=True 时解析 JSON 输出，否则返回原始文本。
    - stdin_data: 通过管道传入的输入内容（用于 stdin 模式）。
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            input=stdin_data,
        )
        if expect_json:
            data = json.loads(result.stdout.strip())
            return data
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
    command = [
        "lark-cli",
        "calendar",
        "+agenda",
        "--start", start_date,
        "--end", end_date,
    ]
    return run_cli_command(command)


def fetch_tasks() -> dict | list:
    """获取任务列表。"""
    print("✅ 正在获取任务列表...")
    command = [
        "lark-cli",
        "task",
        "+get-my-tasks",
    ]
    return run_cli_command(command)


# ============================================================
# Prompt 构建 & AI 调用
# ============================================================

WEEKLY_REPORT_PROMPT_TEMPLATE = """你是一位专业的职场助手，请根据以下飞书日历事件和任务数据，生成一份正式的周报。

## 时间范围
{start_date} ~ {end_date}

## 日历事件
{calendar_events}

## 任务列表
{tasks}

## 周报要求
请按以下结构生成正式周报（使用 Markdown 格式）：

1. **本周工作总结**
   - 概述本周主要工作方向和进展

2. **重点工作与成果**
   - 按项目/主题分类，列出重要会议、关键里程碑和交付成果
   - 突出完成的亮点工作

3. **进行中的工作**
   - 列出正在推进的事项及当前进展

4. **待办与计划**
   - 列出未完成的任务和下周需要跟进的事项

5. **风险与需要协调的事项**（如有）

注意事项：
- 语言简洁专业，避免冗余描述
- 用数据和时间节点支撑描述
- 如果某些板块没有对应数据，可以简要说明"暂无"
- 不要编造数据中不存在的信息"""


def build_weekly_prompt(
    start_date: str,
    end_date: str,
    calendar_events: dict | list,
    tasks: dict | list,
) -> str:
    """将日历事件和任务数据组装为 AI Prompt。"""
    calendar_text = json.dumps(calendar_events, ensure_ascii=False, indent=2)
    tasks_text = json.dumps(tasks, ensure_ascii=False, indent=2)

    prompt = WEEKLY_REPORT_PROMPT_TEMPLATE.format(
        start_date=start_date,
        end_date=end_date,
        calendar_events=calendar_text,
        tasks=tasks_text,
    )
    return prompt


def call_ai(prompt: str, ai_cmd: list[str] | None = None) -> str:
    """调用飞书 AI 生成周报文本。"""
    print("🤖 正在调用飞书 AI 生成周报...")
    command = (ai_cmd or AI_COMMAND) + [prompt]
    result = run_cli_command(command, expect_json=False)
    return result


# ============================================================
# 飞书文档创建
# ============================================================

def create_feishu_doc(
    title: str,
    content: str,
    mode: str = DOCS_CREATE_MODE,
    docs_cmd: list[str] | None = None,
) -> str:
    """
    创建飞书文档并返回文档 URL 或 ID。

    Args:
        title: 文档标题
        content: 文档内容（Markdown 格式）
        mode: 传参模式，可选 "arg" | "file" | "stdin"
        docs_cmd: 自定义文档创建命令（默认使用 DOCS_CREATE_COMMAND）

    Returns:
        命令输出的文档 URL 或 ID
    """
    cmd = docs_cmd or DOCS_CREATE_COMMAND
    print(f"📝 正在创建飞书文档: {title}...")

    if mode == "arg":
        # 模式一：通过命令行参数传入内容
        command = cmd + ["--title", title, "--markdown", content]
        result = run_cli_command(command, expect_json=False)
    elif mode == "file":
        # 模式二：通过临时文件传入内容（使用 @file 语法）
        import tempfile
        import os
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
        # 模式三：通过管道 stdin 传入内容（使用 - 表示 stdin）
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
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="仅获取数据，不调用 AI 生成周报",
    )
    parser.add_argument(
        "--no-doc",
        action="store_true",
        help="不自动创建飞书文档",
    )
    parser.add_argument(
        "--ai-cmd",
        nargs="+",
        default=None,
        help=f"自定义 AI 命令（默认: {' '.join(AI_COMMAND)}）",
    )
    parser.add_argument(
        "--docs-cmd",
        nargs="+",
        default=None,
        help=f"自定义文档创建命令（默认: {' '.join(DOCS_CREATE_COMMAND)}）",
    )
    parser.add_argument(
        "--docs-mode",
        choices=["arg", "file", "stdin"],
        default=None,
        help=f"文档内容传入模式（默认: {DOCS_CREATE_MODE}）",
    )
    args = parser.parse_args()

    # 允许通过命令行覆盖配置
    ai_cmd = args.ai_cmd if args.ai_cmd else AI_COMMAND
    docs_cmd = args.docs_cmd if args.docs_cmd else DOCS_CREATE_COMMAND
    docs_mode = args.docs_mode if args.docs_mode else DOCS_CREATE_MODE

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
        weekly_report = call_ai(prompt, ai_cmd=ai_cmd)

    # 5. 自动创建飞书文档
    doc_url = None
    if weekly_report and not args.no_doc:
        doc_title = f"周报 ({start_date} ~ {end_date})"
        doc_content = (
            f"# {doc_title}\n\n"
            f"{weekly_report}\n\n"
            f"---\n*由飞书 AI 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        )
        doc_url = create_feishu_doc(
            title=doc_title,
            content=doc_content,
            mode=docs_mode,
            docs_cmd=docs_cmd,
        )

    # 6. 组装最终输出
    output = {
        "week_range": {
            "start": start_date,
            "end": end_date,
        },
        "calendar_events": calendar_events,
        "tasks": tasks,
        "fetched_at": datetime.now().isoformat(),
    }
    if weekly_report:
        output["weekly_report"] = weekly_report
    if doc_url:
        output["feishu_doc"] = doc_url

    # ---- Markdown 输出到标准输出 ----
    if weekly_report:
        print("\n" + "=" * 60)
        print("📋 AI 生成的周报")
        print("=" * 60)
        print(weekly_report)

    # ---- 飞书文档链接 ----
    if doc_url:
        print("\n" + "=" * 60)
        print("🔗 飞书文档")
        print("=" * 60)
        print(doc_url)

    # ---- JSON 保存到文件 ----
    json_output = json.dumps(output, ensure_ascii=False, indent=2)
    output_file = f"feishu_weekly_{start_date}_{end_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json_output)
    print(f"\n💾 结果已保存到: {output_file}")

    # ---- 如果有周报，额外保存一份 Markdown 文件 ----
    if weekly_report:
        md_file = f"weekly_report_{start_date}_{end_date}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# 周报 ({start_date} ~ {end_date})\n\n")
            f.write(weekly_report)
            f.write(f"\n\n---\n*由飞书 AI 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
        print(f"📄 周报已保存到: {md_file}")


if __name__ == "__main__":
    main()
