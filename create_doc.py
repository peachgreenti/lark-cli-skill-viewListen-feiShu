#!/usr/bin/env python3
"""
飞书云文档创建脚本

将 README.md 的内容通过 lark-cli docs +create 创建为飞书云文档。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def create_doc(title: str, content: str, timeout: int = 60) -> str | None:
    """
    通过 lark-cli docs +create 创建飞书云文档。

    Args:
        title: 文档标题
        content: 文档内容（Markdown 格式）
        timeout: 创建超时时间（秒）

    Returns:
        创建的文档 URL，或 None（失败时）
    """
    # 将内容写入临时文件
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="feishu_doc_",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["lark-cli", "docs", "+create", "--title", title, "--file", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            print(f"创建飞书文档失败: {result.stderr.strip()}", file=sys.stderr)
            return None

        output = result.stdout.strip()
        print(f"飞书文档已创建: {output}")
        return output

    except subprocess.TimeoutExpired:
        print(f"创建飞书文档超时（{timeout} 秒）", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("未找到 lark-cli 命令，请确保已安装并添加到 PATH", file=sys.stderr)
        return None
    except Exception as e:
        print(f"创建飞书文档异常: {e}", file=sys.stderr)
        return None
    finally:
        # 清理临时文件
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()


def main() -> None:
    """主程序入口。"""
    # 读取 README.md 内容
    readme_path = Path(__file__).parent / "README.md"
    if not readme_path.exists():
        print(f"README.md 不存在: {readme_path}", file=sys.stderr)
        sys.exit(1)

    content = readme_path.read_text(encoding="utf-8")
    title = "飞书消息监听 & AI 分类 - 使用文档"

    print(f"正在创建飞书云文档: {title}")
    print(f"内容来源: {readme_path}")
    print(f"内容长度: {len(content)} 字符")
    print()

    doc_url = create_doc(title, content)

    if doc_url:
        print()
        print(f"文档创建成功!")
        print(f"URL: {doc_url}")
    else:
        print()
        print("文档创建失败，请检查错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    main()
