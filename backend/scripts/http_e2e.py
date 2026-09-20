"""study_helper 真实 HTTP 端到端验证：注册 → 登录 → 上传文档 → SSE 问答 → 校验引用溯源 → 清理。"""
from __future__ import annotations

import json
import uuid

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
USERNAME = "e2e_" + uuid.uuid4().hex[:8]
PASSWORD = "e2e_pass_123"

DOC_TEXT = """操作系统进程与线程笔记

进程是操作系统分配资源的基本单位，拥有独立的地址空间。
线程是 CPU 调度的基本单位，同一进程内的多个线程共享地址空间。
创建进程的开销明显大于创建线程，因为进程需要复制页表并分配独立的地址空间。
线程之间共享全局变量与堆内存，因此需要用互斥锁保护临界区。
进程之间通信必须借助管道、消息队列或共享内存等进程间通信机制。
上下文切换时，线程切换需要保存的寄存器状态比进程切换少，所以线程切换更快。
死锁产生的四个必要条件分别是互斥、占有并等待、不可抢占与循环等待。
破坏循环等待条件最常见的做法是按固定顺序申请锁。
"""

results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  → {detail}" if detail else ""))
    results.append((label, ok, detail))


with httpx.Client(timeout=180.0) as c:
    print("\n【1】注册 + 登录")
    r = c.post(f"{BASE}/auth/register", json={"username": USERNAME, "password": PASSWORD})
    check("注册返回 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:100]}")
    r = c.post(f"{BASE}/auth/login", json={"username": USERNAME, "password": PASSWORD})
    check("登录返回 200", r.status_code == 200, f"HTTP {r.status_code}")
    token = r.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = c.get(f"{BASE}/auth/me", headers=headers)
    check("带 token 取到用户信息", r.status_code == 200 and r.json()["data"]["username"] == USERNAME)

    print("\n【2】上传知识库文档")
    r = c.post(
        f"{BASE}/documents/upload",
        headers=headers,
        files={"file": ("os_thread.txt", DOC_TEXT.encode("utf-8"), "text/plain")},
    )
    check("上传返回 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:150]}")
    doc_id = r.json()["data"]["id"]

    for _ in range(30):
        listing = c.get(f"{BASE}/documents", headers=headers).json()["data"]
        me = next((d for d in listing["items"] if d["id"] == doc_id), None)
        if me and me["status"] in ("ready", "completed", "success"):
            break
        import time

        time.sleep(1)
    check(
        "文档处理完成",
        bool(me) and me["status"] in ("ready", "completed", "success"),
        f"status={me['status'] if me else None}",
    )

    print("\n【3】SSE 流式问答")
    events: list[dict] = []
    with c.stream(
        "POST",
        f"{BASE}/chat",
        headers=headers,
        json={"content": "线程和进程的区别是什么？死锁需要哪些条件？"},
    ) as resp:
        check("SSE 返回 200", resp.status_code == 200, f"HTTP {resp.status_code}")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    kinds = [e.get("type") for e in events]
    print(f"     收到事件 {len(events)} 个: {sorted(set(kinds))}")
    check("出现 conversation_id 事件", "conversation_id" in kinds)
    check("出现 token 事件", "token" in kinds)
    check("出现 sources 事件", "sources" in kinds)
    check("出现 done 事件", "done" in kinds)

    answer = "".join(str(e["content"]) for e in events if e.get("type") == "token")
    print(f"     回答: {answer[:100]}...")
    check("回答非空", bool(answer.strip()))
    check("回答覆盖到线程与进程的对比", "线程" in answer and "进程" in answer, answer[:60])

    print("\n【4】引用溯源（精确到 document_id / chunk_index）")
    source_events = [e for e in events if e.get("type") == "sources"]
    sources = source_events[0]["content"] if source_events else []
    print(f"     引用来源 {len(sources)} 条")
    check("引用来源非空", len(sources) > 0)
    if sources:
        for s in sources:
            print(
                f"       document_id={s['document_id']} chunk_index={s['chunk_index']} "
                f"score={s['score']:.4f} title={s['document_title']}"
            )
        check(
            "document_id 是真实值而非占位 0",
            all(s["document_id"] == doc_id for s in sources),
            f"期望 {doc_id}，实际 {[s['document_id'] for s in sources]}",
        )
        check(
            "chunk_index 是真实值而非占位 -1",
            all(s["chunk_index"] >= 0 for s in sources),
            f"{[s['chunk_index'] for s in sources]}",
        )
        check(
            "score 在 0-1 之间",
            all(0.0 <= s["score"] <= 1.0 for s in sources),
            f"{[round(s['score'], 4) for s in sources]}",
        )
        check(
            "snippet 来自文档正文",
            any(("线程" in s["snippet"] or "进程" in s["snippet"]) for s in sources),
        )

    print("\n【5】会话与历史消息落库")
    conv_id = next((e["content"] for e in events if e.get("type") == "conversation_id"), None)
    r = c.get(f"{BASE}/conversations", headers=headers)
    listing = r.json()["data"]
    check("会话列表能查到该会话", any(x["id"] == conv_id for x in listing["items"]), f"total={listing['total']}")
    r = c.get(f"{BASE}/conversations/{conv_id}/messages", headers=headers)
    msgs = r.json()["data"]
    check("历史消息包含用户消息与助手回答", len(msgs) >= 2, f"{len(msgs)} 条")
    stored = next((m for m in msgs if m["role"] == "assistant"), None)
    check("助手消息持久化了 sources 字段", bool(stored) and bool(stored.get("sources")), f"{stored.get('sources') if stored else None}")
    if stored and stored.get("sources"):
        s0 = stored["sources"][0]
        check(
            "落库的 sources 也是真实 document_id / chunk_index",
            s0["document_id"] == doc_id and s0["chunk_index"] >= 0,
            f"document_id={s0['document_id']} chunk_index={s0['chunk_index']}",
        )

    print("\n【6】缓存命中：同一问题第二次提问更快且来源一致")
    second: list[dict] = []
    with c.stream("POST", f"{BASE}/chat", headers=headers, json={"content": "线程和进程的区别是什么？死锁需要哪些条件？"}) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                second.append(json.loads(line[6:]))
    second_sources = next((e["content"] for e in second if e.get("type") == "sources"), [])
    check("第二次提问仍返回相同引用来源", len(second_sources) == len(sources), f"{len(sources)} → {len(second_sources)}")
    check(
        "第二次引用 chunk_index 一致",
        [s["chunk_index"] for s in second_sources] == [s["chunk_index"] for s in sources],
    )

    print("\n【7】清理")
    r = c.delete(f"{BASE}/conversations/{conv_id}", headers=headers)
    check("删除会话返回 200", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.delete(f"{BASE}/documents/{doc_id}", headers=headers)
    check("删除文档返回 200", r.status_code == 200, f"HTTP {r.status_code}")

failed = [label for label, ok, _ in results if not ok]
print("\n" + ("全部通过" if not failed else f"存在失败: {failed}"))
raise SystemExit(1 if failed else 0)
