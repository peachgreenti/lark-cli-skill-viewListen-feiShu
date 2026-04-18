#!/usr/bin/env python3
"""
飞书消息监听 - Dry Run 测试脚本

验证所有配置和依赖是否正常，不实际监听消息。
检查项：
  1. 配置文件加载
  2. lark-cli 可用性
  3. lark-cli 登录状态
  4. ARK API（豆包大模型）连通性
  5. FAQ 知识库加载
  6. 群聊列表验证
  7. 每日报告配置

用法：
  python3 msg_assistant.py --dry-run
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


# ============================================================
# 配色
# ============================================================

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✅ {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"  {RED}❌ {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠️  {msg}{RESET}")


def info(msg: str) -> None:
    print(f"  {CYAN}ℹ️  {msg}{RESET}")


# ============================================================
# 加载配置
# ============================================================

def deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


DEFAULT_CONFIG = {
    "listener": {"event_name": "im.message.receive_v1", "output_format": "ndjson",
                  "allowed_chat_ids": [], "ignore_bot_messages": True},
    "ai": {"provider": "ark", "model": "spark-lite", "timeout": 30, "enabled": True,
           "classification_prompt": "", "ark_api_key": "", "ark_endpoint_id": "",
           "ark_base_url": "https://ark.cn-beijing.volces.com/api/v3"},
    "faq": {"enabled": False, "file_path": "faq.yaml", "match_mode": "keyword", "fuzzy_threshold": 0.6},
    "report": {"enabled": True, "hour": 18, "minute": 0, "title_prefix": "飞书消息每日摘要",
               "clear_after_report": True, "create_timeout": 60},
    "logging": {"level": "INFO", "file_path": "listen_feishu.log", "max_size_mb": 10,
                "backup_count": 5, "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s"},
}


def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        return DEFAULT_CONFIG.copy()
    with open(p, "r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    return deep_merge(DEFAULT_CONFIG, user)


# ============================================================
# 检查函数
# ============================================================

def check_config_file(config: dict) -> bool:
    """检查配置文件加载。"""
    print(f"\n{BOLD}[1/7] 配置文件{RESET}")
    ok(f"配置加载成功")

    listener = config.get("listener", {})
    ai = config.get("ai", {})
    faq = config.get("faq", {})
    report = config.get("report", {})

    info(f"事件名称:     {listener.get('event_name')}")
    info(f"输出格式:     {listener.get('output_format')}")
    info(f"监听群聊数:   {len(listener.get('allowed_chat_ids', []))}")
    info(f"忽略机器人:   {listener.get('ignore_bot_messages')}")
    info(f"AI 提供商:    {ai.get('provider', 'lark')}")
    info(f"FAQ 启用:     {faq.get('enabled')}")
    info(f"报告时间:     {report.get('hour', 18):02d}:{report.get('minute', 0):02d}")

    allowed = listener.get("allowed_chat_ids", [])
    if not allowed:
        warn("allowed_chat_ids 为空，将监听所有群聊")
    else:
        for cid in allowed:
            info(f"  → {cid}")

    return True


def check_lark_cli() -> bool:
    """检查 lark-cli 是否可用。"""
    print(f"\n{BOLD}[2/7] lark-cli{RESET}")

    import shutil
    if not shutil.which("lark-cli"):
        fail("未找到 lark-cli 命令")
        info("安装: npm install -g @larksuite/cli")
        return False

    import subprocess
    try:
        result = subprocess.run(["lark-cli", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            ok(f"lark-cli 版本: {result.stdout.strip()}")
            return True
        else:
            fail(f"lark-cli 返回错误: {result.stderr.strip()[:100]}")
            return False
    except Exception as e:
        fail(f"lark-cli 检查失败: {e}")
        return False


def check_lark_auth() -> bool:
    """检查 lark-cli 登录状态。"""
    print(f"\n{BOLD}[3/7] lark-cli 登录状态{RESET}")

    import subprocess
    try:
        result = subprocess.run(["lark-cli", "auth", "status"], capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()

        if result.returncode != 0:
            fail(f"未登录或登录已过期")
            info("请运行: lark-cli auth login --recommend")
            return False

        # 检查输出中是否有登录信息
        if "logged" in output.lower() or "已登录" in output or result.returncode == 0:
            ok("已登录")
            # 尝试显示用户信息
            for line in output.split("\n"):
                line = line.strip()
                if line and "error" not in line.lower():
                    info(line)
            return True
        else:
            warn("登录状态不确定，请确认: lark-cli auth status")
            for line in output.split("\n")[:5]:
                if line.strip():
                    info(line.strip())
            return True  # 不阻塞

    except FileNotFoundError:
        fail("未找到 lark-cli")
        return False
    except Exception as e:
        warn(f"检查登录状态失败: {e}")
        return True  # 不阻塞


def check_ark_api(config: dict) -> bool:
    """检查 ARK API 连通性。"""
    print(f"\n{BOLD}[4/7] ARK API（豆包大模型）{RESET}")

    ai = config.get("ai", {})
    provider = ai.get("provider", "lark")

    if provider != "ark":
        info(f"当前 provider 为 '{provider}'，跳过 ARK 检查")
        return True

    api_key = ai.get("ark_api_key", "") or os.environ.get("ARK_API_KEY", "")
    endpoint_id = ai.get("ark_endpoint_id", "")
    base_url = ai.get("ark_base_url", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")

    if not api_key:
        fail("ARK_API_KEY 未配置")
        info("设置方式（任选其一）:")
        info("  1. config.yaml 中填写 ark_api_key")
        info("  2. 环境变量: export ARK_API_KEY='your-key'")
        info("  3. source ~/.feishu_weekly_env")
        return False

    if not endpoint_id:
        fail("ark_endpoint_id 未配置")
        info("请在 config.yaml 中填写 ark_endpoint_id")
        return False

    ok(f"API Key:    {api_key[:10]}...{api_key[-6:]}")
    ok(f"Endpoint:   {endpoint_id}")
    ok(f"Base URL:   {base_url}")

    # 实际调用测试
    print("  正在测试 API 调用...")
    request_body = json.dumps({
        "model": endpoint_id,
        "messages": [{"role": "user", "content": "回复 OK"}],
        "temperature": 0,
    }).encode("utf-8")

    url = f"{base_url}/chat/completions"
    req = urllib.request.Request(url, data=request_body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            model = body.get("model", "")
            usage = body.get("usage", {})
            ok(f"API 调用成功！模型: {model}")
            ok(f"返回内容: {content[:50]}")
            if usage:
                info(f"Token 用量: 输入={usage.get('prompt_tokens', '?')}, 输出={usage.get('completion_tokens', '?')}")

            # 测试分类 prompt
            print("  正在测试分类能力...")
            classify_prompt = """请对以下消息分类，返回JSON: {"priority":"P0/P1/P2/P3","reason":"理由"}
消息：线上接口报500错误"""
            classify_body = json.dumps({
                "model": endpoint_id,
                "messages": [{"role": "user", "content": classify_prompt}],
                "temperature": 0.1,
            }).encode("utf-8")
            req2 = urllib.request.Request(url, data=classify_body, method="POST")
            req2.add_header("Content-Type", "application/json")
            req2.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                body2 = json.loads(resp2.read().decode("utf-8"))
                content2 = body2.get("choices", [{}])[0].get("message", {}).get("content", "")
                ok(f"分类测试: {content2[:100]}")
            return True

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        fail(f"API HTTP 错误 {e.code}")
        info(f"响应: {error_body[:200]}")
        return False
    except urllib.error.URLError as e:
        fail(f"网络错误: {e.reason}")
        return False
    except Exception as e:
        fail(f"调用失败: {e}")
        return False


def check_faq(config: dict) -> bool:
    """检查 FAQ 知识库。"""
    print(f"\n{BOLD}[5/7] FAQ 知识库{RESET}")

    faq = config.get("faq", {})

    if not faq.get("enabled", False):
        info("FAQ 未启用，跳过")
        return True

    faq_path = Path(faq.get("file_path", "faq.yaml"))
    if not faq_path.exists():
        fail(f"FAQ 文件不存在: {faq_path}")
        return False

    try:
        with open(faq_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        faqs = data.get("faqs", [])
        ok(f"已加载 {len(faqs)} 条 FAQ ({faq_path})")
        for i, item in enumerate(faqs[:3], 1):
            q = item.get("question", "")[:40]
            kws = ", ".join(item.get("keywords", [])[:3])
            info(f"  {i}. [{kws}] {q}")
        if len(faqs) > 3:
            info(f"  ... 还有 {len(faqs) - 3} 条")
        return True
    except Exception as e:
        fail(f"FAQ 加载失败: {e}")
        return False


def check_chat_ids(config: dict) -> bool:
    """验证群聊 ID 是否有效。"""
    print(f"\n{BOLD}[6/7] 群聊验证{RESET}")

    allowed = config.get("listener", {}).get("allowed_chat_ids", [])
    if not allowed:
        info("未配置群聊过滤，跳过验证")
        return True

    import subprocess
    all_valid = True
    for cid in allowed:
        try:
            result = subprocess.run(
                ["lark-cli", "im", "chats", "info", "--chat-id", cid, "--format", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout.strip())
                name = data.get("data", {}).get("name", "未知")
                ok(f"{cid} → {name}")
            else:
                warn(f"{cid} → 无法获取群聊信息（可能无权限）")
        except Exception as e:
            warn(f"{cid} → 验证失败: {e}")
            all_valid = False

    return all_valid


def check_report_config(config: dict) -> bool:
    """检查每日报告配置。"""
    print(f"\n{BOLD}[7/7] 每日报告配置{RESET}")

    report = config.get("report", {})

    if not report.get("enabled", True):
        info("每日报告未启用")
        return True

    hour = report.get("hour", 18)
    minute = report.get("minute", 0)
    ok(f"报告时间: 每天 {hour:02d}:{minute:02d}")
    ok(f"标题前缀: {report.get('title_prefix', '飞书消息每日摘要')}")
    ok(f"生成后清空: {report.get('clear_after_report', True)}")

    # 检查 lark-cli docs 命令是否可用
    import shutil
    if shutil.which("lark-cli"):
        ok("lark-cli docs +create 命令可用")
    else:
        fail("lark-cli 不可用，无法创建飞书文档")

    return True


# ============================================================
# 主程序
# ============================================================

def main():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  飞书消息监听 - Dry Run 测试")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 50}{RESET}")

    # 加载配置
    config_path = "config.yaml"
    for i, arg in enumerate(sys.argv):
        if arg in ("--config", "-c") and i + 1 < len(sys.argv):
            config_path = sys.argv[i + 1]

    config = load_config(config_path)

    # 逐项检查
    results = {}
    results["config"] = check_config_file(config)
    results["lark_cli"] = check_lark_cli()
    results["lark_auth"] = check_lark_auth()
    results["ark_api"] = check_ark_api(config)
    results["faq"] = check_faq(config)
    results["chat_ids"] = check_chat_ids(config)
    results["report"] = check_report_config(config)

    # 汇总
    total = len(results)
    passed = sum(1 for v in results.values() if v)

    print(f"\n{BOLD}{'=' * 50}")
    print(f"  测试结果: {GREEN}{passed}/{total} 通过{RESET}" +
          (f"  {RED}{total - passed} 项失败{RESET}" if passed < total else "  🎉"))
    print(f"{'=' * 50}{RESET}\n")

    if passed < total:
        print(f"{YELLOW}部分检查未通过，请根据上方提示修复后再运行。{RESET}\n")
        sys.exit(1)
    else:
        print(f"{GREEN}所有检查通过！可以运行: source ~/.feishu_weekly_env && python3 listen_feishu.py{RESET}\n")


if __name__ == "__main__":
    main()
