# -*- coding: utf-8 -*-
"""OneBot API 连通性测试 v2：用 echo 字段精确配对响应"""
import asyncio
import json
import sys
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def call(ws, action, params=None):
    tag = f"echo_{action}"
    payload = {"action": action, "params": params or {}, "echo": tag}
    await ws.send(json.dumps(payload, ensure_ascii=False))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        msg = json.loads(raw)
        if msg.get("echo") == tag:
            return msg


async def main():
    async with websockets.connect("ws://127.0.0.1:3001") as ws:
        # 先消费连接后的 lifecycle 事件
        try:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            print("[initial event]", first.get("meta_event_type") or first.get("post_type"))
        except asyncio.TimeoutError:
            pass

        info = await call(ws, "get_login_info")
        print("[get_login_info]", json.dumps(info.get("data", {}), ensure_ascii=False))

        friends = await call(ws, "get_friend_list")
        data = friends.get("data", []) or []
        print(f"[get_friend_list] count={len(data)}")
        for f in data[:5]:
            print("   friend:", f.get("user_id"), f.get("nickname"))

        groups = await call(ws, "get_group_list")
        gdata = groups.get("data", []) or []
        print(f"[get_group_list] count={len(gdata)}")
        for g in gdata[:5]:
            print("   group:", g.get("group_id"), g.get("group_name"))

        # 发送链路测试：给自己（bot 本人）发一条，不打扰他人
        me = (info.get("data") or {}).get("user_id")
        if me:
            r = await call(ws, "send_private_msg", {"user_id": me, "message": "链路测试 OK：这是 AI 程序发来的消息，看到即双向通道正常"})
            print("[send test]", r.get("status"), r.get("message"))


asyncio.run(main())
