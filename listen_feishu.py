#!/usr/bin/env python3
"""
飞书消息监听 & AI 分类脚本

功能：
  - 通过 lark-cli 监听飞书群聊消息（im.message.receive_v1 事件）
  - 使用飞书内置 AI（spark-lite）或火山引擎 ARK（豆包大模型）进行优先级分类（P0-P3）
  - 支持 FAQ 自动回复（关键词 / 模糊匹配）
  - 每日定时生成摘要报告并创建飞书云文档
  - 线程安全的消息存储，跨天自动清空
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml

# ============================================================
# 常量定义
# ============================================================

PRIORITY_LEVELS: dict[str, dict[str, str]] = {
    "P0": {"label": "紧急", "emoji": "🔴", "description": "生产环境故障、线上事故、核心服务不可用"},
    "P1": {"label": "重要", "emoji": "🟠", "description": "客户严重问题、关键任务、重要会议通知"},
    "P2": {"label": "一般", "emoji": "🟡", "description": "日常开发讨论、代码审查、一般性技术问题"},
    "P3": {"label": "低优", "emoji": "🟢", "description": "闲聊、非工作话题、已解决问题的后续讨论"},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "listener": {
        "event_name": "im.message.receive_v1",
        "output_format": "ndjson",
        "allowed_chat_ids": [],
        "ignore_bot_messages": True,
    },
    "ai": {
        "provider": "ark",          # "ark"（豆包大模型）或 "lark"（飞书内置 AI）
        "model": "spark-lite",
        "timeout": 30,
        "enabled": True,
        "classification_prompt": "",
        # ARK（火山引擎方舟）配置
        "ark_api_key": "",           # 也可通过环境变量 ARK_API_KEY 设置
        "ark_endpoint_id": "",       # ARK 推理接入点 ID
        "ark_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "faq": {
        "enabled": False,
        "file_path": "faq.yaml",
        "match_mode": "keyword",
        "fuzzy_threshold": 0.6,
    },
    "report": {
        "enabled": True,
        "hour": 18,
        "minute": 0,
        "title_prefix": "飞书消息每日摘要",
        "clear_after_report": True,
        "create_timeout": 60,
    },
    "logging": {
        "level": "INFO",
        "file_path": "listen_feishu.log",
        "max_size_mb": 10,
        "backup_count": 5,
        "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    },
}

logger = logging.getLogger("listen_feishu")


# ============================================================
# 配置加载
# ============================================================

def deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 中的值覆盖 base 中的值。"""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str) -> dict[str, Any]:
    """加载配置文件并与默认值合并。"""
    path = Path(config_path)
    if not path.exists():
        logger.warning("配置文件 %s 不存在，使用默认配置", config_path)
        return DEFAULT_CONFIG.copy()

    with open(path, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}

    config = deep_merge(DEFAULT_CONFIG, user_config)
    logger.info("配置已加载: %s", config_path)
    return config


# ============================================================
# 日志配置
# ============================================================

def setup_logging(log_config: dict[str, Any]) -> None:
    """配置日志：同时输出到控制台和文件（RotatingFileHandler）。"""
    log_level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    log_format = log_config.get("format", "%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    log_file = log_config.get("file_path", "listen_feishu.log")
    max_bytes = log_config.get("max_size_mb", 10) * 1024 * 1024
    backup_count = log_config.get("backup_count", 5)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有 handler，避免重复
    root_logger.handlers.clear()

    formatter = logging.Formatter(log_format)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件 handler（RotatingFileHandler）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger.info("日志已初始化: level=%s, file=%s", log_level, log_file)


# ============================================================
# AI 分类
# ============================================================

def call_ark_ai(message: str, config: dict[str, Any]) -> dict | None:
    """
    通过火山引擎 ARK（豆包大模型）进行消息分类。
    ARK 兼容 OpenAI API 格式，使用 urllib 直接调用（无需额外依赖）。

    Args:
        message: 待分类的消息文本
        config: AI 配置段

    Returns:
        解析后的分类结果字典，或 None（调用失败时）
    """
    api_key = config.get("ark_api_key", "") or os.environ.get("ARK_API_KEY", "")
    endpoint_id = config.get("ark_endpoint_id", "")
    base_url = config.get("ark_base_url", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    timeout = config.get("timeout", 30)
    prompt_template = config.get("classification_prompt", "")

    if not api_key:
        logger.warning("ARK_API_KEY 未配置，无法调用豆包大模型")
        return None
    if not endpoint_id:
        logger.warning("ark_endpoint_id 未配置，无法调用豆包大模型")
        return None
    if not prompt_template:
        logger.warning("AI classification_prompt 未配置，跳过分类")
        return None

    prompt = prompt_template.replace("{message}", message)

    # ARK 兼容 OpenAI 格式，model 字段填 endpoint_id
    request_body = json.dumps({
        "model": endpoint_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }).encode("utf-8")

    url = f"{base_url}/chat/completions"
    req = urllib.request.Request(url, data=request_body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("ARK AI 返回内容为空")
                return None
            return parse_ai_response(content)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        logger.error("ARK API HTTP 错误 %s: %s", e.code, error_body[:300])
        return None
    except urllib.error.URLError as e:
        logger.error("ARK API 网络错误: %s", e.reason)
        return None
    except Exception as e:
        logger.error("ARK AI 分类异常: %s", e)
        return None


def call_lark_ai(message: str, config: dict[str, Any]) -> dict | None:
    """
    通过 lark-cli api 调用飞书内置 AI 进行消息分类。

    Args:
        message: 待分类的消息文本
        config: AI 配置段

    Returns:
        解析后的分类结果字典，或 None（调用失败时）
    """
    model = config.get("model", "spark-lite")
    timeout = config.get("timeout", 30)
    prompt_template = config.get("classification_prompt", "")

    if not prompt_template:
        logger.warning("AI classification_prompt 未配置，跳过分类")
        return None

    prompt = prompt_template.replace("{message}", message)

    try:
        result = subprocess.run(
            ["lark-cli", "api", "ai/v1/chat/completions",
             "--method", "POST",
             "--data", json.dumps({
                 "model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "temperature": 0.1,
             })],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.error("lark-cli api 调用失败: %s", result.stderr.strip())
            return None

        response = json.loads(result.stdout.strip())
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            logger.warning("AI 返回内容为空")
            return None

        return parse_ai_response(content)

    except subprocess.TimeoutExpired:
        logger.error("AI 调用超时（%s 秒）", timeout)
        return None
    except json.JSONDecodeError as e:
        logger.error("AI 返回内容 JSON 解析失败: %s", e)
        return None
    except Exception as e:
        logger.error("AI 分类异常: %s", e)
        return None


def call_ai(message: str, config: dict[str, Any]) -> dict | None:
    """
    统一 AI 调用入口，根据配置自动选择 provider。

    Args:
        message: 待分类的消息文本
        config: AI 配置段

    Returns:
        解析后的分类结果字典，或 None
    """
    provider = config.get("provider", "lark")

    if provider == "ark":
        return call_ark_ai(message, config)
    else:
        return call_lark_ai(message, config)


def parse_ai_response(content: str) -> dict | None:
    """
    解析 AI 返回的内容，提取 JSON 分类结果。

    支持以下格式：
    - 纯 JSON 字符串
    - Markdown 代码块包裹的 JSON
    - 混合文本中嵌入的 JSON
    """
    # 尝试从 Markdown 代码块中提取 JSON
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    if code_block_match:
        content = code_block_match.group(1).strip()

    # 尝试直接解析
    try:
        result = json.loads(content)
        if "priority" in result:
            return result
    except json.JSONDecodeError:
        pass

    # 尝试从文本中提取 JSON 对象
    json_match = re.search(r"\{[^{}]*\"priority\"[^{}]*\}", content, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            if "priority" in result:
                return result
        except json.JSONDecodeError:
            pass

    # 尝试从文本中提取优先级标识（如 "P0"、"P1" 等）
    priority_match = re.search(r"\b(P[0-3])\b", content, re.IGNORECASE)
    if priority_match:
        priority = priority_match.group(1).upper()
        if priority in PRIORITY_LEVELS:
            return {"priority": priority, "reason": content[:100]}

    logger.warning("无法从 AI 返回内容中解析出有效的分类结果: %s", content[:200])
    return {"priority": "P2", "reason": "无法解析 AI 分类结果"}


# ============================================================
# FAQ 匹配
# ============================================================

class FAQMatcher:
    """FAQ 知识库匹配器，支持关键词精确匹配和 Jaccard 模糊匹配。"""

    def __init__(self, faq_config: dict[str, Any]) -> None:
        self.enabled: bool = faq_config.get("enabled", False)
        self.file_path: str = faq_config.get("file_path", "faq.yaml")
        self.match_mode: str = faq_config.get("match_mode", "keyword")
        self.fuzzy_threshold: float = faq_config.get("fuzzy_threshold", 0.6)
        self.faqs: list[dict[str, Any]] = []

        if self.enabled:
            self._load_faqs()

    def _load_faqs(self) -> None:
        """从 YAML 文件加载 FAQ 数据。"""
        path = Path(self.file_path)
        if not path.exists():
            logger.warning("FAQ 文件 %s 不存在", self.file_path)
            self.enabled = False
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.faqs = data.get("faqs", [])
            logger.info("已加载 %d 条 FAQ", len(self.faqs))
        except Exception as e:
            logger.error("加载 FAQ 文件失败: %s", e)
            self.enabled = False

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """简单分词：按空格和标点拆分，转小写。"""
        text = text.lower()
        tokens = set(re.findall(r"[\w]+", text))
        return tokens

    @staticmethod
    def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
        """计算两个集合的 Jaccard 相似度。"""
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    def match(self, message: str) -> dict | None:
        """
        根据消息内容匹配 FAQ。

        Args:
            message: 消息文本

        Returns:
            匹配到的 FAQ 字典（含 question, answer），或 None
        """
        if not self.enabled or not self.faqs:
            return None

        if self.match_mode == "keyword":
            return self._match_keyword(message)
        elif self.match_mode == "fuzzy":
            return self._match_fuzzy(message)
        else:
            logger.warning("未知的 FAQ 匹配模式: %s", self.match_mode)
            return None

    def _match_keyword(self, message: str) -> dict | None:
        """关键词精确匹配：消息中包含任一 FAQ 的任一关键词即命中。"""
        message_lower = message.lower()
        for faq in self.faqs:
            keywords = faq.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    logger.info("FAQ 关键词命中: '%s' -> %s", keyword, faq.get("question", ""))
                    return faq
        return None

    def _match_fuzzy(self, message: str) -> dict | None:
        """模糊匹配：使用 Jaccard 相似度，返回得分最高的 FAQ（需超过阈值）。"""
        message_tokens = self._tokenize(message)
        best_match: dict | None = None
        best_score = 0.0

        for faq in self.faqs:
            # 合并 question 和 keywords 作为匹配文本
            match_text = faq.get("question", "")
            keywords = faq.get("keywords", [])
            if keywords:
                match_text += " " + " ".join(keywords)

            faq_tokens = self._tokenize(match_text)
            score = self._jaccard_similarity(message_tokens, faq_tokens)

            if score > best_score:
                best_score = score
                best_match = faq

        if best_match and best_score >= self.fuzzy_threshold:
            logger.info("FAQ 模糊匹配命中 (score=%.2f): %s", best_score, best_match.get("question", ""))
            return best_match

        return None


# ============================================================
# 消息存储
# ============================================================

class MessageStore:
    """线程安全的消息存储，支持跨天自动清空。"""

    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._current_date: date = date.today()

    def add(self, message: dict[str, Any]) -> None:
        """添加一条消息，如果跨天则自动清空历史消息。"""
        with self._lock:
            today = date.today()
            if today != self._current_date:
                logger.info("检测到日期变更 (%s -> %s)，清空历史消息", self._current_date, today)
                self._messages.clear()
                self._current_date = today
            self._messages.append(message)

    def get_all(self) -> list[dict[str, Any]]:
        """获取所有已存储的消息（副本）。"""
        with self._lock:
            return list(self._messages)

    def clear(self) -> int:
        """清空所有消息，返回被清空的消息数量。"""
        with self._lock:
            count = len(self._messages)
            self._messages.clear()
            return count

    @property
    def count(self) -> int:
        """当前存储的消息数量。"""
        with self._lock:
            return len(self._messages)


# ============================================================
# 消息解析
# ============================================================

def parse_message(event_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    解析飞书事件数据，提取消息的关键信息。

    Args:
        event_data: lark-cli 输出的原始事件 JSON

    Returns:
        解析后的消息字典，或 None（解析失败时）
    """
    try:
        event = event_data.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})

        msg_id = message.get("message_id", "")
        msg_type = message.get("message_type", "")
        chat_id = message.get("chat_id", "")
        content_str = message.get("content", "{}")

        # 解析消息内容
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            content = {"text": content_str}

        sender_id = sender.get("user_id", "") or sender.get("open_id", "")
        sender_type = event.get("sender", {}).get("sender_type", "")

        # 提取纯文本
        text = ""
        if msg_type == "text":
            text = content.get("text", "")
        elif msg_type == "post":
            # 富文本消息，提取所有文本段落
            title = content.get("title", "")
            body = content.get("content", [])
            paragraphs = []
            for item in body:
                if isinstance(item, list):
                    for node in item:
                        if isinstance(node, dict) and node.get("tag") == "text":
                            paragraphs.append(node.get("text", ""))
                elif isinstance(item, dict):
                    if item.get("tag") == "text":
                        paragraphs.append(item.get("text", ""))
            text = f"{title}\n" + "\n".join(paragraphs) if title else "\n".join(paragraphs)
        else:
            text = f"[{msg_type}消息]"

        # 时间戳
        create_time = message.get("create_time", "")
        timestamp = ""
        if create_time:
            try:
                dt = datetime.fromtimestamp(int(create_time) / 1000)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                timestamp = create_time

        return {
            "message_id": msg_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "sender_type": sender_type,
            "message_type": msg_type,
            "text": text.strip(),
            "content": content,
            "timestamp": timestamp,
            "raw": event_data,
        }

    except Exception as e:
        logger.error("解析消息失败: %s", e)
        return None


def format_content(text: str, max_length: int = 200) -> str:
    """格式化消息内容，超长则截断。"""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def format_time(timestamp: str) -> str:
    """格式化时间戳，仅保留时分。"""
    if not timestamp:
        return ""
    parts = timestamp.split(" ")
    if len(parts) >= 2:
        return parts[1][:5]  # HH:MM
    return timestamp


# ============================================================
# 每日摘要报告
# ============================================================

def generate_report_markdown(messages: list[dict[str, Any]]) -> str:
    """
    根据存储的消息生成 Markdown 格式的每日摘要报告。

    Args:
        messages: 消息列表

    Returns:
        Markdown 格式的报告文本
    """
    if not messages:
        return "# 飞书消息每日摘要\n\n今日暂无消息记录。\n"

    today = date.today().strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# 飞书消息每日摘要",
        f"",
        f"**日期**: {today}",
        f"**消息总数**: {len(messages)}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
    ]

    # 按优先级分组统计
    priority_groups: dict[str, list[dict[str, Any]]] = {"P0": [], "P1": [], "P2": [], "P3": []}
    unclassified: list[dict[str, Any]] = []

    for msg in messages:
        priority = msg.get("priority", "")
        if priority in priority_groups:
            priority_groups[priority].append(msg)
        else:
            unclassified.append(msg)

    # 统计概览
    lines.append("---")
    lines.append("")
    lines.append("## 优先级分布")
    lines.append("")
    lines.append("| 优先级 | 级别 | 数量 |")
    lines.append("|--------|------|------|")

    for p_level in ["P0", "P1", "P2", "P3"]:
        info = PRIORITY_LEVELS[p_level]
        count = len(priority_groups[p_level])
        lines.append(f"| {p_level} | {info['emoji']} {info['label']} | {count} |")

    if unclassified:
        lines.append(f"| 未分类 | - | {len(unclassified)} |")

    lines.append("")

    # 各优先级详情
    for p_level in ["P0", "P1", "P2", "P3"]:
        group = priority_groups[p_level]
        if not group:
            continue

        info = PRIORITY_LEVELS[p_level]
        lines.append("---")
        lines.append("")
        lines.append(f"## {p_level} - {info['emoji']} {info['label']}")
        lines.append("")
        lines.append(f"> {info['description']}")
        lines.append("")

        for i, msg in enumerate(group, 1):
            time_str = format_time(msg.get("timestamp", ""))
            sender = msg.get("sender_id", "未知")[:8]
            text = format_content(msg.get("text", ""), max_length=300)
            reason = msg.get("reason", "")
            category = msg.get("category", "")

            lines.append(f"### {i}. [{time_str}] {sender}")
            if category:
                lines.append(f"**类别**: {category}")
            lines.append(f"")
            lines.append(f"{text}")
            if reason:
                lines.append(f"")
                lines.append(f"*分类理由: {reason}*")
            lines.append("")

    # 未分类消息
    if unclassified:
        lines.append("---")
        lines.append("")
        lines.append("## 未分类消息")
        lines.append("")

        for i, msg in enumerate(unclassified, 1):
            time_str = format_time(msg.get("timestamp", ""))
            sender = msg.get("sender_id", "未知")[:8]
            text = format_content(msg.get("text", ""), max_length=300)
            lines.append(f"{i}. **[{time_str}] {sender}**: {text}")

        lines.append("")

    return "\n".join(lines)


def create_feishu_doc(title: str, content: str, timeout: int = 60) -> str | None:
    """
    通过 lark-cli docs +create 创建飞书云文档。

    Args:
        title: 文档标题
        content: 文档内容（Markdown 格式）
        timeout: 创建超时时间（秒）

    Returns:
        创建的文档 URL，或 None（失败时）
    """
    try:
        result = subprocess.run(
            ["lark-cli", "docs", "+create", "--title", title, "--markdown", content],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.error("创建飞书文档失败: %s", result.stderr.strip())
            return None

        # 尝试从输出中提取文档 URL
        output = result.stdout.strip()
        url_match = re.search(r"https?://[^\s]+", output)
        if url_match:
            doc_url = url_match.group(0)
            logger.info("飞书文档已创建: %s", doc_url)
            return doc_url

        logger.info("飞书文档已创建（未提取到URL）: %s", output)
        return output

    except subprocess.TimeoutExpired:
        logger.error("创建飞书文档超时（%s 秒）", timeout)
        return None
    except Exception as e:
        logger.error("创建飞书文档异常: %s", e)
        return None


# ============================================================
# 定时调度
# ============================================================

class ReportScheduler:
    """每日摘要报告定时调度器（daemon 线程）。"""

    def __init__(
        self,
        report_config: dict[str, Any],
        message_store: MessageStore,
    ) -> None:
        self.enabled: bool = report_config.get("enabled", True)
        self.hour: int = report_config.get("hour", 18)
        self.minute: int = report_config.get("minute", 0)
        self.title_prefix: str = report_config.get("title_prefix", "飞书消息每日摘要")
        self.clear_after_report: bool = report_config.get("clear_after_report", True)
        self.create_timeout: int = report_config.get("create_timeout", 60)
        self.message_store = message_store
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动调度器线程。"""
        if not self.enabled:
            logger.info("每日摘要报告已禁用")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ReportScheduler")
        self._thread.start()
        logger.info("报告调度器已启动，每日 %02d:%02d 生成摘要", self.hour, self.minute)

    def stop(self) -> None:
        """停止调度器线程。"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("报告调度器已停止")

    def _run(self) -> None:
        """调度器主循环。"""
        while not self._stop_event.is_set():
            now = datetime.now()

            # 计算到下次报告时间的秒数
            target = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
            if now >= target:
                # 今天的时间已过，计算到明天的
                target = target.replace(day=now.day + 1)

            wait_seconds = (target - now).total_seconds()

            # 每分钟检查一次，以便能及时响应停止信号
            if wait_seconds > 60:
                self._stop_event.wait(timeout=60)
                continue

            # 等待到目标时间
            logger.info("距离下次报告生成还有 %.0f 秒", wait_seconds)
            self._stop_event.wait(timeout=wait_seconds)

            if self._stop_event.is_set():
                break

            # 生成报告
            self._generate_report()

    def _generate_report(self) -> None:
        """生成并创建每日摘要报告。"""
        logger.info("开始生成每日摘要报告...")
        messages = self.message_store.get_all()

        if not messages:
            logger.info("今日无消息，跳过报告生成")
            return

        report_md = generate_report_markdown(messages)
        today = date.today().strftime("%Y-%m-%d")
        title = f"{self.title_prefix} ({today})"

        doc_url = create_feishu_doc(title, report_md, timeout=self.create_timeout)

        if doc_url:
            logger.info("每日摘要报告已创建: %s", doc_url)
        else:
            logger.error("每日摘要报告创建失败")

        if self.clear_after_report:
            cleared = self.message_store.clear()
            logger.info("已清空 %d 条历史消息", cleared)


# ============================================================
# 消息处理
# ============================================================

class MessageHandler:
    """消息处理器，整合过滤、FAQ 匹配、AI 分类和消息存储。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.listener_config = config.get("listener", {})
        self.ai_config = config.get("ai", {})
        self.message_store = MessageStore()
        self.faq_matcher = FAQMatcher(config.get("faq", {}))
        self.report_scheduler = ReportScheduler(config.get("report", {}), self.message_store)

    def start(self) -> None:
        """启动报告调度器。"""
        self.report_scheduler.start()

    def stop(self) -> None:
        """停止报告调度器。"""
        self.report_scheduler.stop()

    def handle(self, event_data: dict[str, Any]) -> None:
        """
        处理一条飞书消息事件。

        Args:
            event_data: lark-cli 输出的原始事件 JSON
        """
        # 1. 解析消息
        parsed = parse_message(event_data)
        if not parsed:
            return

        # 2. 过滤机器人消息
        if self.listener_config.get("ignore_bot_messages", True):
            if parsed.get("sender_type") == "bot":
                logger.debug("忽略机器人消息: %s", parsed.get("message_id"))
                return

        # 3. 过滤不在白名单中的 chat_id
        allowed_ids: list[str] = self.listener_config.get("allowed_chat_ids", [])
        if allowed_ids:
            chat_id = parsed.get("chat_id", "")
            if chat_id not in allowed_ids:
                logger.debug("忽略非白名单消息: chat_id=%s", chat_id)
                return

        text = parsed.get("text", "")
        logger.info(
            "收到消息 [%s] %s: %s",
            parsed.get("timestamp", ""),
            parsed.get("sender_id", "")[:8],
            format_content(text, 100),
        )

        # 4. FAQ 匹配
        faq_result = self.faq_matcher.match(text)
        if faq_result:
            logger.info("FAQ 自动回复: %s", faq_result.get("answer", "")[:100])
            # FAQ 匹配成功，仍然进行 AI 分类和存储

        # 5. AI 分类
        priority_info: dict[str, str] = {}
        if self.ai_config.get("enabled", True) and text:
            ai_result = call_ai(text, self.ai_config)
            if ai_result:
                priority = ai_result.get("priority", "P3")
                priority_info = {
                    "priority": priority,
                    "reason": ai_result.get("reason", ""),
                    "category": ai_result.get("category", ""),
                }
                level_info = PRIORITY_LEVELS.get(priority, {})
                logger.info(
                    "AI 分类: %s %s - %s (%s)",
                    priority,
                    level_info.get("emoji", ""),
                    level_info.get("label", ""),
                    ai_result.get("reason", ""),
                )
            else:
                priority_info = {"priority": "P3", "reason": "AI 分类失败，默认为 P3", "category": ""}
        else:
            priority_info = {"priority": "P3", "reason": "AI 分类未启用", "category": ""}

        # 6. 存储消息
        stored_msg = {**parsed, **priority_info}
        if faq_result:
            stored_msg["faq_matched"] = True
            stored_msg["faq_answer"] = faq_result.get("answer", "")
        self.message_store.add(stored_msg)


# ============================================================
# 主程序
# ============================================================

def main() -> None:
    """主程序入口。"""
    parser = argparse.ArgumentParser(
        description="飞书消息监听 & AI 分类",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）",
    )
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 配置日志
    setup_logging(config.get("logging", {}))

    logger.info("=" * 60)
    logger.info("飞书消息监听 & AI 分类 启动")
    logger.info("=" * 60)

    # 初始化消息处理器
    handler = MessageHandler(config)
    handler.start()

    try:
        # 通过 lark-cli event +subscribe 监听飞书事件（NDJSON 输出）
        event_name = config.get("listener", {}).get("event_name", "im.message.receive_v1")

        cmd = [
            "lark-cli",
            "event",
            "+subscribe",
            "--event-types", event_name,
            "--as", "bot",
            "--quiet",
        ]

        logger.info("启动事件监听: %s", " ".join(cmd))
        logger.info("监听事件: %s", event_name)

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # 行缓冲
        )

        # 逐行读取 lark-cli 的 ndjson 输出
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                event_data = json.loads(line)
                handler.handle(event_data)
            except json.JSONDecodeError as e:
                logger.warning("JSON 解析失败: %s (line: %s)", e, line[:200])
            except Exception as e:
                logger.error("处理消息异常: %s", e)

        # 如果 lark-cli 进程退出
        return_code = process.wait()
        logger.warning("lark-cli 进程已退出，返回码: %d", return_code)

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
    except FileNotFoundError:
        logger.error("未找到 lark-cli 命令，请确保已安装并添加到 PATH")
    except Exception as e:
        logger.error("程序异常: %s", e)
    finally:
        handler.stop()
        logger.info("程序已退出")


if __name__ == "__main__":
    main()
