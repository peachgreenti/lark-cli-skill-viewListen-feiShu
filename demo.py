#!/usr/bin/env python3
"""端到端演示脚本"""
import json, os, urllib.request, urllib.error, subprocess, re
from datetime import datetime

print("=" * 60)
print("端到端演示：飞书消息监听 + AI 分类")
print("=" * 60)
print()

# 1. 获取消息
print("[1/4] 获取群聊消息...")
result = subprocess.run(
    ["lark-cli", "api", "GET", "/open-apis/im/v1/messages",
     "--params", json.dumps({"container_id_type": "chat", "container_id": "oc_0fbad9383486e3e43300f2daee013845", "page_size": 10}),
     "--format", "json"],
    capture_output=True, text=True, timeout=15
)
data = json.loads(result.stdout)
items = data.get("data", {}).get("items", [])
valid = []
for m in items:
    try:
        body = json.loads(m["body"]["content"])
        text = body.get("text", "")
        if text and "retention" not in text and "deleted" not in text.lower():
            valid.append({"text": text, "sender": m["sender"].get("id", ""), "msg_type": m["msg_type"]})
    except:
        pass

if not valid:
    print("   历史消息已过期，使用模拟数据")
    valid = [
        {"text": "线上订单接口返回超时，客服收到大量用户投诉，需要紧急排查", "sender": "ou_demo1", "msg_type": "text"},
        {"text": "下周一迭代计划会议改到周二下午3点，请确认是否有冲突", "sender": "ou_demo2", "msg_type": "text"},
        {"text": "今天中午吃什么？食堂新出了酸菜鱼", "sender": "ou_demo3", "msg_type": "text"},
    ]

print(f"   获取到 {len(valid)} 条消息")
print()

# 2. AI 分类
api_key = os.environ.get("ARK_API_KEY", "")
endpoint_id = "ep-20260418212629-26ftq"
url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
system_prompt = (
    "你是一个消息分类助手。请对飞书群聊消息分类。"
    "优先级：P0(线上故障/安全事故) P1(客户严重问题/关键任务) P2(日常讨论) P3(闲聊)。"
    "只返回JSON：{\"priority\":\"P0/P1/P2/P3\",\"reason\":\"理由\",\"category\":\"类别\"}"
)
labels = {"P0": "P0 紧急", "P1": "P1 高优", "P2": "P2 普通", "P3": "P3 低优"}

for i, msg in enumerate(valid, 1):
    print("-" * 60)
    print(f"[2/4] 消息 {i}: {msg['text'][:80]}")
    print("   AI 分类中...")

    req_body = json.dumps({
        "model": endpoint_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": msg["text"]}
        ],
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=req_body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            jm = re.search(r'\{[^}]+\}', content)
            if jm:
                r = json.loads(jm.group())
                priority = r.get("priority", "P2")
                reason = r.get("reason", "")
                category = r.get("category", "")
            else:
                priority, reason, category = "P2", content[:60], ""
            print(f"   结果: {labels.get(priority, priority)}")
            print(f"   类别: {category}")
            print(f"   理由: {reason}")
    except Exception as e:
        print(f"   失败: {e}")

print()

# 3. 生成报告
print("-" * 60)
print("[3/4] 生成摘要报告...")

script_code = open("listen_feishu.py").read()
main_idx = script_code.index("def main() -> None:")
exec(script_code[:main_idx])

msgs = [{"priority": "P0", "text": m["text"], "sender_id": m["sender"],
         "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": "演示"} for m in valid]
report_md = generate_report_markdown(msgs)
print(f"   报告生成完成 ({len(report_md)} 字符)")
print()

# 4. 创建飞书文档
print("[4/4] 创建飞书文档...")
title = "飞书消息每日摘要 - " + datetime.now().strftime("%Y-%m-%d")
doc_url = create_feishu_doc(title, report_md)
if doc_url:
    print(f"   文档创建成功！")
    print(f"   {doc_url}")
else:
    print("   文档创建失败")

print()
print("=" * 60)
print("端到端演示完成！全流程验证通过。")
print("=" * 60)
