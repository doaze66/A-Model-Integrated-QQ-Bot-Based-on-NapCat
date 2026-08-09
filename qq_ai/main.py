#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QQ AI 替身 - NapCat OneBot11 WebSocket 客户端

模式:
  listen - 只监听记录，不回复
  draft  - 生成草稿写入 replies.txt，不发送
  auto   - 白名单会话自动回复
"""
import asyncio
import json
import logging
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import requests
import websockets
import yaml

# PyInstaller 打包后 __file__ 指向临时解包目录，须用 sys.executable 定位 exe 所在目录
if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.yaml"
LOG_PATH = BASE / "qq_ai.log"
REPLIES_PATH = BASE / "replies.txt"
PERSONA_PATH = BASE / "persona.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("qq_ai")


# ---------- 配置 ----------
def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_persona(cfg):
    """说话风格：优先读 persona.txt（过滤 # 开头的说明行），否则用 config.yaml 的 persona"""
    if PERSONA_PATH.exists():
        try:
            lines = PERSONA_PATH.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            log.warning("读取 persona.txt 失败: %s", e)
            lines = []
        body = "\n".join(l for l in lines if not l.strip().startswith("#")).strip()
        if body:
            return body
        log.info("persona.txt 为空或全为注释，回退 config.yaml 的 persona")
    return cfg["persona"]


# ---------- 安全层 ----------
class Safety:
    def __init__(self, cfg):
        self.cfg = cfg
        self.paused = False
        self._last_reply = {}          # session_key -> timestamp
        self._reply_times = deque()    # 全局回复时间戳（1 分钟窗口）

    def session_key(self, event):
        return str(event.get("group_id") or event.get("user_id"))

    def is_self(self, event):
        return event.get("user_id") == self.cfg["bot_qq"]

    def is_at_me(self, event):
        """群消息中是否点名 @ 了机器人（不含 @全体）"""
        bot = str(self.cfg["bot_qq"])
        for seg in event.get("message", []):
            if seg.get("type") == "at":
                qq = str(seg.get("data", {}).get("qq", ""))
                if qq == bot:
                    return True
        return False

    def blocked_word(self, text):
        for w in self.cfg["block_words"]:
            if w in text:
                return w
        return None

    def check_pause_resume(self, text):
        if text.strip() in self.cfg["pause_words"]:
            self.paused = True
            return "paused"
        if text.strip() in self.cfg["resume_words"]:
            self.paused = False
            return "resumed"
        return None

    def in_whitelist(self, event):
        wl = self.cfg["whitelist"]
        gid = event.get("group_id")
        uid = event.get("user_id")
        if gid and gid in wl["groups"]:
            return True
        if uid and uid in wl["users"]:
            return True
        return False

    def rate_ok(self, key):
        now = time.time()
        rl = self.cfg["rate_limit"]
        if now - self._last_reply.get(key, 0) < rl["min_interval_sec"]:
            return False
        # 清理 60 秒前的记录
        while self._reply_times and self._reply_times[0] < now - 60:
            self._reply_times.popleft()
        max_per_min = rl["max_replies_per_min"]
        if max_per_min and max_per_min > 0 and len(self._reply_times) >= max_per_min:
            return False
        return True

    def note_reply(self, key):
        now = time.time()
        self._last_reply[key] = now
        self._reply_times.append(now)


# ---------- LLM 层 ----------
class LLM:
    def __init__(self, cfg):
        self.cfg = cfg["llm"]

    def generate(self, persona, history, user_msg):
        """返回回复文本；失败返回 None"""
        backend = self.cfg["backend"]
        try:
            if backend == "echo":
                return f"（echo）你说：{user_msg}"
            if backend == "ollama":
                return self._ollama(persona, history, user_msg)
            if backend == "openai":
                return self._openai(persona, history, user_msg)
            return None
        except Exception as e:
            log.error("LLM 调用失败: %s", e)
            return None

    def _build_messages(self, persona, history, user_msg):
        msgs = [{"role": "system", "content": persona}]
        for item in history[-self.cfg.get("context_window", 20):]:
            role = "assistant" if item.get("self") else "user"
            msgs.append({"role": role, "content": item.get("text", "")})
        msgs.append({"role": "user", "content": user_msg})
        return msgs

    def _ollama(self, persona, history, user_msg):
        url = self.cfg["ollama_url"].rstrip("/") + "/api/chat"
        payload = {
            "model": self.cfg["model"],
            "messages": self._build_messages(persona, history, user_msg),
            "stream": False,
            "options": {"temperature": self.cfg["temperature"]},
        }
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()

    def _openai(self, persona, history, user_msg, retries=3):
        url = self.cfg["api_base"].rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.cfg['api_key']}"}
        payload = {
            "model": self.cfg["api_model"],
            "messages": self._build_messages(persona, history, user_msg),
            "temperature": self.cfg["temperature"],
        }
        last_err = None
        for attempt in range(retries):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                last_err = e
                log.warning("LLM 调用第 %d/%d 次失败: %s", attempt + 1, retries, e)
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
        log.error("LLM 调用最终失败: %s", last_err)
        return None


# ---------- 主逻辑 ----------
class QQBot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.safety = Safety(cfg)
        self.llm = LLM(cfg)
        self.contexts = defaultdict(deque)  # session -> deque(maxlen)

    def extract_text(self, event):
        parts = []
        for seg in event.get("message", []):
            if seg.get("type") == "text":
                parts.append(seg.get("data", {}).get("text", ""))
        return "".join(parts).strip()

    def save_draft(self, key, sender, text, reply):
        with open(REPLIES_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {key} @{sender}: {text}\n")
            f.write(f"  -> 草稿: {reply}\n")

    def handle_message(self, event):
        if self.safety.is_self(event):
            return
        text = self.extract_text(event)
        if not text:
            return

        key = self.safety.session_key(event)
        etype = "群" if event.get("message_type") == "group" else "私聊"
        uid = event.get("user_id")
        log.info("接收 %s[%s] @%s: %s", etype, key, uid, text[:80])

        # 群消息只回复 @了机器人的
        if event.get("message_type") == "group" and not self.safety.is_at_me(event):
            log.info("群消息未 @机器人，跳过")
            return

        # 指令（暂停/恢复）
        cmd = self.safety.check_pause_resume(text)
        if cmd == "paused":
            log.warning("收到暂停指令，AI 已暂停")
            return
        if cmd == "resumed":
            log.warning("收到恢复指令，AI 已恢复")
            return
        if self.safety.paused:
            return

        # 敏感词
        bad = self.safety.blocked_word(text)
        if bad:
            log.warning("命中敏感词 [%s]，不回复。会话=%s 用户=%s 内容=%s", bad, key, uid, text)
            return

        # 记录上下文
        self.contexts[key].append({"self": False, "text": text})

        mode = self.cfg["mode"]
        if mode == "listen":
            return

        # 是否允许回复
        allow = self.safety.in_whitelist(event) if mode == "auto" else True
        if mode == "auto" and not allow:
            log.info("会话不在白名单，仅记录")
            return

        if not self.safety.rate_ok(key):
            log.info("频率受限，跳过回复")
            return

        history = list(self.contexts[key])
        reply = self.llm.generate(self.cfg["persona"], history, text)
        if not reply:
            return
        reply = reply[: self.cfg["max_reply_len"]]

        if mode == "draft":
            self.save_draft(key, uid, text, reply)
            log.info("草稿已保存 -> %s", reply)
            return

        # auto: 发送
        self.safety.note_reply(key)
        self.contexts[key].append({"self": True, "text": reply})
        asyncio.create_task(self.send_reply(event, reply))
        log.info("已回复 %s: %s", key, reply)

    async def send_reply(self, event, reply):
        try:
            async with websockets.connect(self.cfg["ws_url"]) as ws:
                if event.get("message_type") == "group":
                    action = {"action": "send_group_msg", "params": {"group_id": event["group_id"], "message": reply}}
                else:
                    action = {"action": "send_private_msg", "params": {"user_id": event["user_id"], "message": reply}}
                action["echo"] = "qq_ai_send"
                await ws.send(json.dumps(action, ensure_ascii=False))
                # 跳过 lifecycle/meta 事件，等待带 echo 的 API 响应
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    msg = json.loads(raw)
                    if msg.get("echo") == "qq_ai_send":
                        if msg.get("status") != "ok":
                            log.error("发送失败: %s", msg)
                        break
        except Exception as e:
            log.error("发送异常: %s", e)

    async def run(self):
        url = self.cfg["ws_url"]
        log.info("QQ AI 替身启动，模式=%s，连接 %s", self.cfg["mode"], url)
        while True:
            try:
                async with websockets.connect(url) as ws:
                    log.info("已连接 WebSocket")
                    async for raw in ws:
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if event.get("post_type") == "message":
                            self.handle_message(event)
            except Exception as e:
                log.error("连接断开: %s，5 秒后重连...", e)
                await asyncio.sleep(5)


def main():
    cfg = load_config()
    cfg["persona"] = load_persona(cfg)
    bot = QQBot(cfg)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        log.info("已退出")


if __name__ == "__main__":
    main()
