package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math/rand"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode/utf8"
)

type message struct {
	Nickname  string `json:"nickname"`
	Content   string `json:"content"`
	Timestamp string `json:"timestamp"`
}

type app struct {
	port     int
	nickname string
	message  string
	bg       string
	accent   string
	mu       sync.Mutex
	messages []message
}

var palette = [][2]string{
	{"#f6eee8", "#b86d52"},
	{"#edf4f8", "#5d7fa6"},
	{"#f2eef8", "#7d6cb1"},
	{"#eef5f0", "#5a8b72"},
	{"#f8f0ec", "#ba7a60"},
	{"#f0f5ea", "#7e9b54"},
	{"#f4f0eb", "#8b7663"},
	{"#edf7f5", "#4f8f89"},
	{"#f7f3ea", "#b18c46"},
	{"#f1eef7", "#8b6fb7"},
	{"#f6ecef", "#b76b7d"},
	{"#edf2f4", "#627b8b"},
}

const pageTemplate = `<!doctype html>
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
`

func main() {
	port := flag.Int("port", 527, "listen port")
	nickname := flag.String("nickname", "留言板", "board nickname")
	message := flag.String("message", "这是一个会在进程启动时随机换背景色的临时留言板。留言只保存在内存里，刷新可见，重启即失。", "board description")
	flag.Parse()
	pair := palette[rand.New(rand.NewSource(time.Now().Unix())).Intn(len(palette))]
	a := &app{port: *port, nickname: *nickname, message: *message, bg: pair[0], accent: pair[1]}
	mux := http.NewServeMux()
	mux.HandleFunc("/", a.handleIndex)
	mux.HandleFunc("/api/messages", a.handleMessages)
	fmt.Printf("留言板已启动: http://localhost:%d (背景色: %s)\n", *port, pair[0])
	if err := http.ListenAndServe(fmt.Sprintf(":%d", *port), mux); err != nil {
		panic(err)
	}
}

func (a *app) handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	page := strings.NewReplacer(
		"__PORT__", strconv.Itoa(a.port),
		"__NICKNAME__", a.nickname,
		"__MESSAGE__", a.message,
		"__BG__", a.bg,
		"__ACCENT__", a.accent,
	).Replace(pageTemplate)
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(page))
}

func (a *app) handleMessages(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		a.mu.Lock()
		messages := append([]message(nil), a.messages...)
		a.mu.Unlock()
		writeJSON(w, http.StatusOK, messages)
	case http.MethodPost:
		defer r.Body.Close()
		var req struct {
			Nickname string `json:"nickname"`
			Content  string `json:"content"`
		}
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}
		nickname := strings.TrimSpace(req.Nickname)
		if nickname == "" {
			nickname = "匿名"
		}
		content := strings.TrimSpace(req.Content)
		if content == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "content required"})
			return
		}
		if utf8.RuneCountInString(content) > 200 {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "content too long"})
			return
		}
		a.mu.Lock()
		a.messages = append(a.messages, message{
			Nickname:  nickname,
			Content:   content,
			Timestamp: time.Now().Format("2006-01-02 15:04:05"),
		})
		a.mu.Unlock()
		writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
