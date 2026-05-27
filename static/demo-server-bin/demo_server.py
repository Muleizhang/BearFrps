#!/usr/bin/env python3
import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PALETTE = [
    ("#f6eee8", "#b86d52"),
    ("#edf4f8", "#5d7fa6"),
    ("#f2eef8", "#7d6cb1"),
    ("#eef5f0", "#5a8b72"),
    ("#f8f0ec", "#ba7a60"),
    ("#f0f5ea", "#7e9b54"),
    ("#f4f0eb", "#8b7663"),
    ("#edf7f5", "#4f8f89"),
    ("#f7f3ea", "#b18c46"),
    ("#f1eef7", "#8b6fb7"),
    ("#f6ecef", "#b76b7d"),
    ("#edf2f4", "#627b8b"),
]

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NICKNAME__ #__PORT__</title>
<style>
:root{--bg:__BG__;--accent:__ACCENT__;--card:rgba(255,255,255,.82);--text:#24303a;--muted:#5f6e78;--line:rgba(36,48,58,.12);--shadow:0 24px 60px rgba(36,48,58,.12);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at top right,rgba(255,255,255,.65),transparent 28%),radial-gradient(circle at bottom left,rgba(255,255,255,.45),transparent 30%),var(--bg);color:var(--text)}.shell{width:min(880px,calc(100vw - 32px));margin:32px auto;display:grid;gap:20px}.hero,.panel{background:var(--card);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shadow);backdrop-filter:blur(10px)}.hero{padding:28px;display:grid;gap:10px}.badge{display:inline-flex;width:fit-content;padding:6px 12px;border-radius:999px;background:rgba(255,255,255,.8);border:1px solid rgba(255,255,255,.9);color:var(--accent);font-size:13px;font-weight:700;letter-spacing:.02em}h1{margin:0;font-size:clamp(30px,5vw,42px);line-height:1.1}.subtitle{margin:0;color:var(--muted);font-size:15px;line-height:1.7}.panel{padding:22px}.panel h2{margin:0 0 16px;font-size:18px}form{display:grid;gap:14px}label{display:grid;gap:8px;color:var(--muted);font-size:14px;font-weight:600}input,textarea,button{font:inherit}input,textarea{width:100%;border:1px solid rgba(36,48,58,.14);border-radius:16px;background:rgba(255,255,255,.92);color:var(--text);padding:14px 16px;outline:none;transition:border-color .2s ease,box-shadow .2s ease}input:focus,textarea:focus{border-color:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 18%,transparent)}textarea{min-height:120px;resize:vertical}.actions{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.hint{color:var(--muted);font-size:13px}button{border:0;border-radius:999px;padding:12px 20px;background:var(--accent);color:#fff;font-weight:700;cursor:pointer;box-shadow:0 12px 28px color-mix(in srgb,var(--accent) 34%,transparent)}button:hover{filter:brightness(.98)}button:active{transform:translateY(1px)}#message-list{display:grid;gap:14px}.message{background:rgba(255,255,255,.76);border:1px solid rgba(36,48,58,.1);border-radius:18px;padding:16px 18px}.meta{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:10px;color:var(--muted);font-size:13px}.meta strong{color:var(--text);font-size:15px}.message p{margin:0;line-height:1.75;white-space:pre-wrap;word-break:break-word}.empty{margin:0;padding:28px;border-radius:18px;border:1px dashed rgba(36,48,58,.16);color:var(--muted);text-align:center;background:rgba(255,255,255,.45)}@media (max-width:640px){.shell{width:min(100vw - 20px,880px);margin:20px auto}.hero,.panel{border-radius:20px}.hero{padding:22px}.panel{padding:18px}.meta{flex-direction:column;align-items:flex-start}}
</style>
</head>
<body>
<main class="shell">
<section class="hero"><span class="badge">Dorm Demo</span><h1>__NICKNAME__ #__PORT__</h1><p class="subtitle">__MESSAGE__</p></section>
<section class="panel"><h2>写一条留言</h2><form id="message-form"><label>昵称（可选）<input id="nickname" name="nickname" type="text" maxlength="40" placeholder="匿名"></label><label>内容（必填）<textarea id="content" name="content" maxlength="200" required placeholder="写点什么吧，最多 200 字。"></textarea></label><div class="actions"><span class="hint">页面会每 3 秒自动刷新一次留言列表。</span><button type="submit">发布留言</button></div></form></section>
<section class="panel"><h2>最新留言</h2><div id="message-list"><p class="empty">正在加载留言...</p></div></section>
</main>
<script>
const form=document.getElementById('message-form');
const nicknameInput=document.getElementById('nickname');
const contentInput=document.getElementById('content');
const list=document.getElementById('message-list');
function escapeHtml(value){return String(value||'').replace(/[&<>\"']/g,function(char){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[char];});}
function render(messages){const items=messages.slice().reverse();if(!items.length){list.innerHTML='<p class="empty">还没有留言，来写第一条吧。</p>';return;}list.innerHTML=items.map(function(item){return '<article class="message"><div class="meta"><strong>'+escapeHtml(item.nickname||'匿名')+'</strong><span>'+escapeHtml(item.timestamp||'')+'</span></div><p>'+escapeHtml(item.content||'')+'</p></article>';}).join('');}
async function loadMessages(){const response=await fetch('/api/messages');if(!response.ok)throw new Error('load failed');render(await response.json());}
async function submitMessage(event){event.preventDefault();const content=contentInput.value.trim();if(!content){contentInput.focus();return;}const response=await fetch('/api/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nickname:nicknameInput.value.trim(),content:content})});if(!response.ok){alert(await response.text()||'提交失败');return;}contentInput.value='';contentInput.focus();await loadMessages();}
form.addEventListener('submit',function(event){submitMessage(event).catch(function(){alert('提交失败，请稍后重试。');});});
loadMessages().catch(function(){list.innerHTML='<p class="empty">留言加载失败，请稍后刷新页面。</p>';});
setInterval(function(){loadMessages().catch(function(){});},3000);
</script>
</body>
</html>
"""

MESSAGES = []
BACKGROUND, ACCENT = random.Random(int(time.time())).choice(PALETTE)


def page_bytes(port, nickname, message):
    return PAGE.replace("__PORT__", str(port)).replace("__NICKNAME__", nickname).replace("__MESSAGE__", message).replace("__BG__", BACKGROUND).replace("__ACCENT__", ACCENT).encode("utf-8")


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "DormBoard/1.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, code, payload):
        body = json_bytes(payload)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = page_bytes(self.server.server_port, self.server.NICKNAME, self.server.MESSAGE)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/messages":
            self.send_json(200, MESSAGES)
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/messages":
            self.send_json(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "invalid json"})
            return
        nickname = str((data or {}).get("nickname") or "").strip() or "匿名"
        content = str((data or {}).get("content") or "").strip()
        if not content:
            self.send_json(400, {"error": "content required"})
            return
        if len(content) > 200:
            self.send_json(400, {"error": "content too long"})
            return
        MESSAGES.append({
            "nickname": nickname,
            "content": content,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        })
        self.send_json(200, {"ok": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="临时留言板")
    parser.add_argument("--port", type=int, default=527)
    parser.add_argument("--nickname", type=str, default="留言板")
    parser.add_argument("--message", type=str, default="这是一个会在进程启动时随机换背景色的临时留言板。留言只保存在内存里，刷新可见，重启即失。")
    args = parser.parse_args()
    server = HTTPServer(("0.0.0.0", args.port), Handler)
    server.NICKNAME = args.nickname
    server.MESSAGE = args.message
    print(f"留言板已启动: http://localhost:{args.port} (背景色: {BACKGROUND})")
    server.serve_forever()
