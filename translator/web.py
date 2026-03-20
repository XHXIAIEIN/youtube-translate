"""Web-based subtitle overlay — frosted glass style, inspired by simple-translate-extension."""

import json, sys, os, threading, queue, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# SSE subscribers
_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()
_header_info: dict = {}
_restart_event = threading.Event()
_switch_url = None  # new URL to switch to
_switch_lock = threading.Lock()
_last_client_time = 0.0  # last time a client was connected
_watchdog_timeout = 180   # seconds without any client → exit

def request_restart():
    """Signal the pipeline to soft-restart (reconnect stream, keep Whisper)."""
    _restart_event.set()

def request_switch(url):
    """Signal the pipeline to switch to a new URL."""
    global _switch_url
    with _switch_lock:
        _switch_url = url
    _restart_event.set()

def get_switch_url():
    """Get and clear the pending switch URL."""
    global _switch_url
    with _switch_lock:
        url = _switch_url
        _switch_url = None
    return url

def check_restart():
    """Check and clear the restart signal."""
    if _restart_event.is_set():
        _restart_event.clear()
        return True
    return False

def _watchdog():
    """Exit process if no browser client for _watchdog_timeout seconds."""
    import time
    global _last_client_time
    _last_client_time = time.time()
    while True:
        time.sleep(10)
        with _clients_lock:
            has_clients = len(_clients) > 0
        if has_clients:
            _last_client_time = time.time()
        elif time.time() - _last_client_time > _watchdog_timeout:
            sys.stdout.write("\033[38;5;242mno browser connected for 180s, exiting\033[0m\n")
            sys.stdout.flush()
            os._exit(0)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Live Translator</title>
<style>
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
  background: #0a0a0a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "SF Pro Display", sans-serif;
  color: #fff;
  overflow: hidden;
}

/* ── Header ── */
#header {
  position: fixed; top: 0; left: 0; right: 0;
  padding: 10px 20px;
  background: rgba(28, 28, 30, 0.82);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  z-index: 10;
  display: flex; flex-direction: column; gap: 6px;
  opacity: 0; transform: translateY(-8px);
  animation: slideDown 400ms 200ms cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
}
#header-row1 {
  display: flex; align-items: center; gap: 8px;
}
#url-input {
  flex: 1; min-width: 0;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px; color: rgba(255,255,255,0.6);
  font-family: inherit; outline: none;
  transition: border-color 200ms, color 200ms;
}
#url-input:focus { border-color: rgba(255,255,255,0.2); color: rgba(255,255,255,0.8); }
#url-input::placeholder { color: rgba(255,255,255,0.2); }
.header-btn {
  flex-shrink: 0;
  width: 30px; height: 30px; border-radius: 8px;
  border: none; background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.3); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 200ms, color 200ms;
}
.header-btn:hover { background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.6); }
.header-btn:active { transform: scale(0.92); }
.header-btn svg { width: 14px; height: 14px; }
#header-row2 {
  display: flex; align-items: center; justify-content: space-between;
}
#header-row2 .info {
  font-size: 12px; color: rgba(255,255,255,0.4);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0; flex: 1;
}
#header-row2 .info a { color: rgba(255,255,255,0.55); text-decoration: none; }
#header-row2 .info a:hover { color: rgba(255,255,255,0.8); text-decoration: underline; }

/* ── Subtitle history area ── */
#history {
  position: fixed; bottom: 42vh; left: 0; right: 0; top: 80px;
  overflow-y: auto; overflow-x: hidden;
  padding: 0 28px;
  display: flex; flex-direction: column;
  gap: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.1) transparent;
}

.history-pair {
  opacity: 0; transform: translateY(6px);
  animation: fadeUp 250ms cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
}
.history-ts {
  font-size: 11px; color: rgba(255,255,255,0.15);
  margin-bottom: 2px;
}
.history-en {
  font-size: 13px; color: rgba(255,255,255,0.3);
  line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
}
.history-cn {
  font-size: 15px; color: rgba(255,255,255,0.55);
  line-height: 1.5; font-weight: 500;
  white-space: pre-wrap; word-break: break-word;
}

/* ── Live subtitle card ── */
#subtitle {
  position: fixed;
  position: fixed;
  bottom: 24px; left: 20px; right: 20px;
  max-height: 40vh;
  z-index: 100;
}

#card {
  background: rgba(28, 28, 30, 0.82);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  padding: 16px 22px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.35);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.1) transparent;
}
#card::-webkit-scrollbar { width: 4px; }
#card::-webkit-scrollbar-track { background: transparent; }
#card::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
}
#card::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

.card-en {
  font-size: 13px;
  color: rgba(255,255,255,0.45);
  line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
  transition: color 200ms;
}
.card-en:hover { color: rgba(255,255,255,0.65); }

.card-cn {
  font-size: 18px;
  color: #fff;
  font-weight: 600;
  line-height: 1.4;
  margin-top: 6px;
  white-space: pre-wrap; word-break: break-word;
}

/* ── Loading spinner ── */
.loading {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px;
}
.spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.15);
  border-top-color: rgba(255,255,255,0.6);
  border-radius: 50%;
  animation: spin 600ms linear infinite;
}
.loading-text {
  font-size: 14px; color: rgba(255,255,255,0.35);
}

/* ── Status dot ── */
#status {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: rgba(255,255,255,0.3);
  flex-shrink: 0;
}
#status .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #555;
  transition: background 300ms;
}
#status .dot.live { background: #30d158; animation: pulse 2s infinite; }

/* ── Animations ── */
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes fadeUp {
  to { opacity: 1; transform: translateY(0); }
}
@keyframes slideDown {
  to { opacity: 1; transform: translateY(0); }
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
</head>
<body>

<div id="header">
  <div id="header-row1">
    <input id="url-input" type="text" placeholder="粘贴 YouTube URL，回车切换直播...">
    <button class="header-btn" id="switch-btn" title="切换直播"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg></button>
    <button class="header-btn" id="refresh-btn" title="重连"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg></button>
  </div>
  <div id="header-row2">
    <span class="info" id="h-info">连接中...</span>
    <div id="status">
      <span class="dot" id="dot"></span>
      <span id="status-text">等待连接</span>
    </div>
  </div>
</div>

<div id="history"><div id="history-spacer" style="flex:1"></div></div>

<div id="subtitle">
  <div id="card">
    <div class="card-en" id="live-en"></div>
    <div class="card-cn" id="live-cn"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const card = $('card');
const liveEn = $('live-en');
const liveCn = $('live-cn');
const history = $('history');
const dot = $('dot');

let currentEn = '';
let cnParts = [];
let connected = false;
let pending = null; // {en, cn, ts} — completed translation sitting in live area

function pushHistory(en, cn, ts) {
  const pair = document.createElement('div');
  pair.className = 'history-pair';
  const time = ts || new Date().toLocaleTimeString();
  pair.innerHTML =
    '<div class="history-ts">' + esc(time) + '</div>' +
    '<div class="history-en">' + esc(en) + '</div>' +
    '<div class="history-cn">' + esc(cn) + '</div>';
  history.appendChild(pair);
  // keep last 200
  const spacer = $('history-spacer');
  while (history.children.length > 201) {
    const first = spacer.nextElementSibling;
    if (first) history.removeChild(first);
  }
  // auto-scroll only if user is near bottom
  const atBottom = history.scrollHeight - history.scrollTop - history.clientHeight < 60;
  if (atBottom) history.scrollTop = history.scrollHeight;
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function connect() {
  const es = new EventSource('/events');

  es.onopen = () => {
    connected = true;
    dot.classList.add('live');
    $('status-text').textContent = '已连接';
  };

  es.onerror = () => {
    connected = false;
    dot.classList.remove('live');
    $('status-text').textContent = '连接断开，重连中...';
  };

  es.addEventListener('header', e => {
    const d = JSON.parse(e.data);
    const parts = [];
    if (d.title) parts.push(d.url ? '<a href="' + esc(d.url) + '" target="_blank">' + esc(d.title) + '</a>' : esc(d.title));
    if (d.channel) parts.push(esc(d.channel));
    parts.push(d.is_live ? 'LIVE' : 'video');
    if (d.provider) parts.push(esc(d.provider + '/' + (d.model || '')));
    $('h-info').innerHTML = parts.join(' · ');
    if (d.url) $('url-input').value = d.url;
    document.title = (d.title || 'YouTube Translator') + ' — 实时翻译';
  });

  function flushPending() {
    if (pending) {
      pushHistory(pending.en, pending.cn, pending.ts);
      pending = null;
      liveCn.textContent = '';
    }
  }

  // en_interim/en_final: flush previous pair to history, show new English
  es.addEventListener('en_interim', e => {
    flushPending();
    const d = JSON.parse(e.data);
    currentEn = d.text;
    liveEn.textContent = d.text;
  });

  es.addEventListener('en_final', e => {
    flushPending();
    const d = JSON.parse(e.data);
    currentEn = d.text;
    liveEn.textContent = d.text;
  });

  // cn_start: flush previous to history, show new state
  es.addEventListener('cn_start', () => {
    if (pending) {
      pushHistory(pending.en, pending.cn, pending.ts);
      pending = null;
    }
    liveEn.textContent = currentEn;
    cnParts = [];
    liveCn.innerHTML = '<div class="loading"><div class="spinner"></div><span class="loading-text">翻译中...</span></div>';
  });

  // cn_token: stream tokens in real-time
  es.addEventListener('cn_token', e => {
    const d = JSON.parse(e.data);
    cnParts.push(d.token);
    liveCn.textContent = cnParts.join('');
  });

  // cn_end: keep in live area until next cn_start
  es.addEventListener('cn_end', e => {
    const d = JSON.parse(e.data);
    liveEn.textContent = currentEn;
    liveCn.textContent = d.cn;
    pending = {en: d.en, cn: d.cn, ts: d.ts};
  });

  es.addEventListener('log', e => {
    const d = JSON.parse(e.data);
    $('status-text').textContent = d.text;
  });
}

connect();
$('refresh-btn').onclick = () => {
  $('status-text').textContent = '重连中...';
  dot.classList.remove('live');
  fetch('/restart').catch(() => {});
};

function switchUrl() {
  const url = $('url-input').value.trim();
  if (!url) return;
  $('status-text').textContent = '切换中...';
  dot.classList.remove('live');
  $('h-title').textContent = '切换中...';
  $('h-meta').textContent = '';
  history.innerHTML = '';
  liveEn.textContent = '';
  liveCn.textContent = '';
  pending = null;
  fetch('/switch?url=' + encodeURIComponent(url)).catch(() => {});
}
$('switch-btn').onclick = switchUrl;
$('url-input').addEventListener('keydown', e => { if (e.key === 'Enter') switchUrl(); });
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/events':
            self._handle_sse()
        elif path == '/restart':
            self._handle_restart()
        elif path.startswith('/switch'):
            self._handle_switch()
        else:
            self._serve_page()

    def _handle_restart(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        request_restart()

    def _handle_switch(self):
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        url = qs.get('url', [''])[0]
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if url:
            request_switch(url)
            self.wfile.write(b'{"ok":true}')
        else:
            self.wfile.write(b'{"ok":false,"error":"no url"}')

    def _serve_page(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))

    def _handle_sse(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        q: queue.Queue = queue.Queue()
        with _clients_lock:
            _clients.append(q)

        # send header info immediately
        if _header_info:
            self._send_event('header', _header_info)

        try:
            while True:
                event = q.get()
                if event is None:
                    break
                self._send_event(event['type'], event.get('data', {}))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _clients_lock:
                if q in _clients:
                    _clients.remove(q)

    def _send_event(self, event_type, data):
        payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        self.wfile.write(payload.encode('utf-8'))
        self.wfile.flush()

    def log_message(self, fmt, *args):
        pass  # suppress request logs


def _broadcast(event_type, data=None):
    msg = {'type': event_type, 'data': data or {}}
    with _clients_lock:
        for q in _clients:
            q.put(msg)


def start_web_server(port=9875):
    server = HTTPServer(('127.0.0.1', port), _Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    webbrowser.open(f'http://127.0.0.1:{port}')
    return server


def set_header(title, channel, is_live, url, provider, model, chunk, srt_path):
    global _header_info
    _header_info = {
        'title': title, 'channel': channel, 'is_live': is_live,
        'url': url, 'provider': provider, 'model': model,
    }
    _broadcast('header', _header_info)


def web_render_loop(out_q):
    """Drop-in replacement for render_loop — pushes events to browser via SSE."""
    from .names import annotate
    from .srt import save_record

    en_buffer = []
    in_cn = False

    while True:
        msg = out_q.get()
        if msg is None:
            break

        kind = msg[0]

        if kind == "en_interim":
            _, text, ts = msg
            _broadcast('en_interim', {'text': text, 'ts': ts})

        elif kind == "en_final":
            if in_cn:
                en_buffer.append(msg)
            else:
                _, text, ts = msg
                _broadcast('en_final', {'text': text, 'ts': ts})

        elif kind == "cn_start":
            in_cn = True
            _broadcast('cn_start')

        elif kind == "cn_token":
            _broadcast('cn_token', {'token': msg[1]})

        elif kind == "cn_end":
            _, en, cn, ts = msg
            display, clean = annotate(cn)
            save_record(en, clean, ts)
            _broadcast('cn_end', {'en': en, 'cn': display, 'ts': ts})
            in_cn = False

            for _, text, ts2 in en_buffer:
                _broadcast('en_final', {'text': text, 'ts': ts2})
            en_buffer.clear()

        elif kind == "log":
            _broadcast('log', {'text': msg[1]})
