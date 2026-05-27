(function () {
  window.USE_MOCK = true;
  window.MOCK_SERVER_HOST = "120.46.51.131";

  function uid() {
    let v = localStorage.getItem("mock_uid");
    if (!v) {
      v = "u_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem("mock_uid", v);
    }
    return v;
  }

  function makeToken() {
    return Math.random().toString(36).slice(2, 18);
  }

  function loadProxies() {
    try { return JSON.parse(localStorage.getItem("mock_proxies") || "[]"); }
    catch { return []; }
  }
  function saveProxies(arr) { localStorage.setItem("mock_proxies", JSON.stringify(arr)); }

  function loadUsers() {
    try { return JSON.parse(localStorage.getItem("mock_users") || "{}"); }
    catch { return {}; }
  }
  function saveUsers(obj) { localStorage.setItem("mock_users", JSON.stringify(obj)); }

  function ensureUser() {
    let users = loadUsers();
    let id = uid();
    if (!users[id]) {
      users[id] = { uid: id, created_at: new Date().toISOString(), balance_mb: 0, total_recharged_mb: 0, connection_count: 0 };
      saveUsers(users);
    }
    return users[id];
  }

  function nextPort() {
    let proxies = loadProxies();
    let used = new Set(proxies.map(function (p) { return p.frps_remote_port; }));
    for (let i = 50000; i <= 50100; i++) {
      if (!used.has(i)) return i;
    }
    return null;
  }

  let adminSession = false;

  function makeFrpcConfig(proxy) {
    return 'serverAddr = "' + window.MOCK_SERVER_HOST + '"\n'
      + 'serverPort = 7000\n\n'
      + 'auth.method = "token"\n'
      + 'auth.token = "' + proxy.token + '"\n\n'
      + '[[proxies]]\n'
      + 'name = "' + proxy.name + '"\n'
      + 'type = "tcp"\n'
      + 'localIP = "127.0.0.1"\n'
      + 'localPort = 527\n'
      + 'remotePort = ' + proxy.frps_remote_port + '\n';
  }

  function makeScripts(proxy) {
    var cfg = makeFrpcConfig(proxy);
    var cfgEscaped = cfg.replace(/'/g, "'\\''");
    var version = "0.58.1";
    var rp = proxy.frps_remote_port;
    var name = proxy.name;
    var token = proxy.token;
    var host = window.MOCK_SERVER_HOST;
    var binBase = "http://" + host + ":8000/static/demo-server-bin";

    var frpcLinux = "#!/bin/bash\nread -p 'Local port [default 527]: ' PORT\nPORT=${PORT:-527}\n\nARCH=$(uname -m)\ncase $ARCH in\n  x86_64) ARCH=amd64;;\n  aarch64|arm64) ARCH=arm64;;\nesac\n\nif [ ! -f frpc ]; then\n  curl -L -o frp.tar.gz \"https://github.com/fatedier/frp/releases/download/" + version + "/frp_" + version + "_linux_${ARCH}.tar.gz\"\n  tar xzf frp.tar.gz --strip-components=1 --wildcards \"*/frpc\"\n  chmod +x frpc\nfi\n\ncat > frpc.toml <<'EOF'\n" + cfg + "EOF\n\nsed -i \"s/localPort = 527/localPort = $PORT/\" frpc.toml\n\n./frpc -c frpc.toml\n";

    var frpcMac = "#!/bin/bash\nread -p 'Local port [default 527]: ' PORT\nPORT=${PORT:-527}\n\nARCH=$(uname -m)\ncase $ARCH in\n  x86_64) ARCH=amd64;;\n  aarch64|arm64) ARCH=arm64;;\nesac\n\nif [ ! -f frpc ]; then\n  curl -L -o frp.tar.gz \"https://github.com/fatedier/frp/releases/download/" + version + "/frp_" + version + "_darwin_${ARCH}.tar.gz\"\n  tar xzf frp.tar.gz --strip-components=1 --wildcards \"*/frpc\"\n  chmod +x frpc\nfi\n\ncat > frpc.toml <<'EOF'\n" + cfg + "EOF\n\nsed -i '' \"s/localPort = 527/localPort = $PORT/\" frpc.toml\n\n./frpc -c frpc.toml\n";

    var frpcWin = "$PORT = Read-Host 'Local port [default 527]'\nif (-not $PORT) { $PORT = 527 }\n\nif (-not (Test-Path frpc.exe)) {\n  Invoke-WebRequest -Uri 'https://github.com/fatedier/frp/releases/download/" + version + "/frp_" + version + "_windows_amd64.zip' -OutFile frp.zip\n  Expand-Archive frp.zip -DestinationPath .\n  Move-Item frp_*\\frpc.exe .\n  Remove-Item frp_* -Recurse\n}\n\n$cfg = @\"\n" + cfg + "\"@\n$cfg = $cfg -replace 'localPort = 527', \"localPort = $PORT\"\nSet-Content frpc.toml $cfg\n\n.\\frpc.exe -c frpc.toml\n";

    var demoServerPy = "import http.server, json, time, argparse, os, math\n\nclass Handler(http.server.BaseHTTPRequestHandler):\n    msgs = []\n    COLORS = ['#d1fae5','#dbeafe','#fce7f3','#fef3c7','#ede9fe','#ccfbf1','#fef9c3','#e0e7ff']\n    bg = COLORS[int(time.time()) % len(COLORS)]\n\n    def do_GET(self):\n        if self.path == '/api/messages':\n            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()\n            self.wfile.write(json.dumps(self.msgs).encode())\n        else:\n            html = '<html><head><meta charset=utf-8><style>body{background:'+self.bg+';font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px}input,textarea{width:100%;padding:8px;margin:4px 0;box-sizing:border-box;border:1px solid #ccc;border-radius:4px}button{padding:8px 16px;background:#2563eb;color:#fff;border:none;border-radius:4px;cursor:pointer}.msg{padding:8px;border-bottom:1px solid #e5e7eb}</style></head><body>'\n            html += '<h2>Message Board</h2>'\n            html += '<form onsubmit=\"postMsg();return false\"><input id=nick placeholder=Nickname><textarea id=content placeholder=Message rows=2></textarea><button type=submit>Send</button></form>'\n            html += '<div id=list></div>'\n            html += '<script>function load(){fetch(\"/api/messages\").then(r=>r.json()).then(d=>{document.getElementById(\"list\").innerHTML=d.map(m=>\"<div class=msg><b>\"+m.nickname+\"</b> \"+m.content+\"</div>\").join(\"\")})}function postMsg(){fetch(\"/api/messages\",{method:\"POST\",headers:{\"Content-Type\":\"application/json\"},body:JSON.stringify({nickname:document.getElementById(\"nick\").value,content:document.getElementById(\"content\").value})}).then(load)}setInterval(load,3000);load()</script>'\n            html += '</body></html>'\n            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()\n            self.wfile.write(html.encode())\n\n    def do_POST(self):\n        if self.path == '/api/messages':\n            length = int(self.headers.get('Content-Length',0))\n            data = json.loads(self.rfile.read(length))\n            data['timestamp'] = time.time()\n            self.msgs.append(data)\n            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()\n            self.wfile.write(json.dumps({'ok':True}).encode())\n\nif __name__ == '__main__':\n    p = argparse.ArgumentParser()\n    p.add_argument('--port', type=int, default=527)\n    a = p.parse_args()\n    print(f'Serving on port {a.port}...')\n    http.server.HTTPServer(('0.0.0.0', a.port), Handler).serve_forever()\n";

    var demoLinux = "#!/bin/bash\nread -p 'Local port [default 527]: ' PORT\nPORT=${PORT:-527}\n\ncat > demo_server.py <<'PYEOF'\n" + demoServerPy + "PYEOF\n\nif command -v python3 >/dev/null 2>&1; then\n    python3 demo_server.py --port $PORT\nelse\n    echo 'Python3 not found, downloading binary...'\n    ARCH=$(uname -m)\n    case $ARCH in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac\n    curl -L -o demo-server " + binBase + "/demo-server-linux-${ARCH}\n    chmod +x demo-server\n    ./demo-server --port $PORT\nfi\n";

    var demoMac = "#!/bin/bash\nread -p 'Local port [default 527]: ' PORT\nPORT=${PORT:-527}\n\ncat > demo_server.py <<'PYEOF'\n" + demoServerPy + "PYEOF\n\nif command -v python3 >/dev/null 2>&1; then\n    python3 demo_server.py --port $PORT\nelse\n    echo 'Python3 not found, downloading binary...'\n    ARCH=$(uname -m)\n    case $ARCH in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac\n    curl -L -o demo-server " + binBase + "/demo-server-darwin-${ARCH}\n    chmod +x demo-server\n    ./demo-server --port $PORT\nfi\n";

    var demoWin = "$PORT = Read-Host 'Local port [default 527]'\nif (-not $PORT) { $PORT = 527 }\n\n$script = @'\n" + demoServerPy + "'@\nSet-Content demo_server.py $script\n\ntry { python demo_server.py --port $PORT }\ncatch {\n  Write-Host 'Python not found, downloading binary...'\n  Invoke-WebRequest -Uri '" + binBase + "/demo-server-windows-amd64.exe' -OutFile demo-server.exe\n  .\\demo-server.exe --port $PORT\n}\n";

    return {
      frpc: { linux: frpcLinux, mac: frpcMac, windows: frpcWin },
      demo: { linux: demoLinux, mac: demoMac, windows: demoWin }
    };
  }

  function randomTraffic() {
    return Math.floor(Math.random() * 5000000);
  }

  function refreshOnlineStatus() {
    let proxies = loadProxies();
    proxies.forEach(function (p) {
      if (p.status === "active") {
        p.is_online = Math.random() > 0.3;
        if (p.is_online) {
          p.traffic_used_bytes = Math.min(p.traffic_used_bytes + Math.floor(Math.random() * 100000), p.traffic_limit_mb * 1024 * 1024);
          p.current_speed_bps = Math.floor(Math.random() * 500000);
          p.actual_local_port = 527;
          p.last_seen_at = new Date().toISOString();
        } else {
          p.current_speed_bps = 0;
        }
      }
    });
    saveProxies(proxies);
  }

  function statusClass(proxy) {
    if (proxy.status === "stopped_by_admin" || proxy.status === "deleted") return "row-disabled";
    if (!proxy.is_online) return "row-offline";
    var usedMb = proxy.traffic_used_bytes / (1024 * 1024);
    if (usedMb >= proxy.traffic_limit_mb) return "row-offline";
    return "row-online";
  }

  function cardStatusClass(proxy) {
    if (proxy.status === "stopped_by_admin" || proxy.status === "deleted") return "card-disabled";
    if (!proxy.is_online) return "card-offline";
    var usedMb = proxy.traffic_used_bytes / (1024 * 1024);
    if (usedMb >= proxy.traffic_limit_mb) return "card-offline";
    return "card-online";
  }

  window.statusClass = statusClass;
  window.cardStatusClass = cardStatusClass;

  function statusBadge(proxy) {
    if (proxy.status === "stopped_by_admin" || proxy.status === "deleted") return { cls: "badge-disabled", text: proxy.status === "stopped_by_admin" ? "已停用" : "已删除" };
    if (!proxy.is_online) return { cls: "badge-offline", text: "离线" };
    var usedMb = proxy.traffic_used_bytes / (1024 * 1024);
    if (usedMb >= proxy.traffic_limit_mb) return { cls: "badge-offline", text: "超流量" };
    return { cls: "badge-online", text: "在线" };
  }

  window.statusBadge = statusBadge;

  var routes = {
    "POST /api/user/init": function () {
      var user = ensureUser();
      var proxies = loadProxies().filter(function (p) { return p.uid === user.uid && p.status !== "deleted"; });
      user.connection_count = proxies.length;
      return { status: 200, body: user };
    },

    "POST /api/user/recharge": function () {
      var users = loadUsers();
      var id = uid();
      var user = users[id];
      if (!user) return { status: 404, body: { detail: "User not found" } };
      user.balance_mb += 100;
      user.total_recharged_mb += 100;
      saveUsers(users);
      return { status: 200, body: { balance_mb: user.balance_mb, total_recharged_mb: user.total_recharged_mb } };
    },

    "GET /api/proxies": function () {
      refreshOnlineStatus();
      var id = uid();
      var proxies = loadProxies().filter(function (p) { return p.uid === id && p.status !== "deleted"; });
      return { status: 200, body: { proxies: proxies } };
    },

    "POST /api/proxies": function (body) {
      var users = loadUsers();
      var id = uid();
      var user = users[id];
      if (!user) return { status: 404, body: { detail: "User not found" } };

      var proxies = loadProxies();
      var mine = proxies.filter(function (p) { return p.uid === id && p.status !== "deleted"; });

      if (mine.length >= 3) return { status: 400, body: { detail: "超过最大连接数" } };
      if (body.traffic_mb > user.balance_mb) return { status: 400, body: { detail: "余额不足" } };
      if (mine.some(function (p) { return p.name === body.name; })) return { status: 400, body: { detail: "名称重复" } };

      var port = nextPort();
      if (port === null) return { status: 400, body: { detail: "端口池满" } };

      user.balance_mb -= body.traffic_mb;
      saveUsers(users);

      var proxy = {
        id: Date.now(),
        uid: id,
        name: body.name,
        token: makeToken(),
        frps_remote_port: port,
        status: "active",
        is_online: false,
        actual_local_port: null,
        speed_limit_kbps: body.speed_limit_kbps || 1024,
        traffic_limit_mb: body.traffic_mb,
        traffic_used_bytes: 0,
        current_speed_bps: 0,
        created_at: new Date().toISOString(),
        last_seen_at: null
      };

      proxies.push(proxy);
      saveProxies(proxies);

      return {
        status: 200,
        body: {
          proxy: proxy,
          frpc_config: makeFrpcConfig(proxy),
          scripts: makeScripts(proxy)
        }
      };
    },

    "DELETE /api/proxies/": function (pathParts) {
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var idx = proxies.findIndex(function (p) { return String(p.id) === idStr && p.uid === uid(); });
      if (idx === -1) return { status: 404, body: { detail: "Not found" } };
      proxies.splice(idx, 1);
      saveProxies(proxies);
      return { status: 200, body: { ok: true } };
    },

    "GET /api/proxies/": function (pathParts) {
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var proxy = proxies.find(function (p) { return String(p.id) === idStr && p.uid === uid(); });
      if (!proxy) return { status: 404, body: { detail: "Not found" } };
      return {
        status: 200,
        body: {
          proxy: proxy,
          frpc_config: makeFrpcConfig(proxy),
          scripts: makeScripts(proxy)
        }
      };
    },

    "POST /api/admin/login": function (body) {
      if (body.username === "admin" && body.password === "changeme") {
        adminSession = true;
        return { status: 200, body: { ok: true } };
      }
      return { status: 401, body: { detail: "Invalid credentials" } };
    },

    "POST /api/admin/logout": function () {
      adminSession = false;
      return { status: 200, body: { ok: true } };
    },

    "GET /api/admin/proxies": function () {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      refreshOnlineStatus();
      return { status: 200, body: { proxies: loadProxies() } };
    },

    "GET /api/admin/users": function () {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var users = loadUsers();
      var proxies = loadProxies();
      var arr = Object.values(users).map(function (u) {
        var count = proxies.filter(function (p) { return p.uid === u.uid && p.status !== "deleted"; }).length;
        return Object.assign({}, u, { connection_count: count });
      });
      return { status: 200, body: { users: arr } };
    },

    "POST /api/admin/proxies/stop": function (pathParts) {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var proxy = proxies.find(function (p) { return String(p.id) === idStr; });
      if (!proxy) return { status: 404, body: { detail: "Not found" } };
      proxy.status = "stopped_by_admin";
      proxy.is_online = false;
      proxy.current_speed_bps = 0;
      saveProxies(proxies);
      return { status: 200, body: { ok: true } };
    },

    "POST /api/admin/proxies/start": function (pathParts) {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var proxy = proxies.find(function (p) { return String(p.id) === idStr; });
      if (!proxy) return { status: 404, body: { detail: "Not found" } };
      proxy.status = "active";
      saveProxies(proxies);
      return { status: 200, body: { ok: true } };
    },

    "DELETE /api/admin/proxies/": function (pathParts) {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var idx = proxies.findIndex(function (p) { return String(p.id) === idStr; });
      if (idx === -1) return { status: 404, body: { detail: "Not found" } };
      proxies.splice(idx, 1);
      saveProxies(proxies);
      return { status: 200, body: { ok: true } };
    },

    "GET /api/show/online": function () {
      refreshOnlineStatus();
      var proxies = loadProxies().filter(function (p) {
        return p.is_online && p.status === "active";
      });
      var result = proxies.map(function (p) {
        return {
          id: p.id,
          name: p.name,
          remote_port: p.frps_remote_port,
          public_url: "http://" + window.MOCK_SERVER_HOST + ":" + p.frps_remote_port + "/"
        };
      });
      return { status: 200, body: { proxies: result } };
    }
  };

  var originalFetch = window.fetch;

  window.fetch = function (input, init) {
    if (!window.USE_MOCK) return originalFetch.apply(this, arguments);

    var url = typeof input === "string" ? input : input.url;
    var method = (init && init.method) || "GET";
    method = method.toUpperCase();
    var body = (init && init.body) ? JSON.parse(init.body) : undefined;

    var urlObj = new URL(url, window.location.origin);
    var path = urlObj.pathname;

    if (method === "POST" && path === "/api/user/init") {
      return mockResponse(routes["POST /api/user/init"]());
    }
    if (method === "POST" && path === "/api/user/recharge") {
      return mockResponse(routes["POST /api/user/recharge"]());
    }
    if (method === "GET" && path === "/api/proxies") {
      return mockResponse(routes["GET /api/proxies"]());
    }
    if (method === "POST" && path === "/api/proxies") {
      return mockResponse(routes["POST /api/proxies"](body));
    }
    if (method === "GET" && path.match(/^\/api\/proxies\/\d+\/scripts$/)) {
      var idPart = path.replace("/api/proxies/", "").replace("/scripts", "");
      return mockResponse(routes["GET /api/proxies/"]([idPart]));
    }
    if (method === "DELETE" && path.match(/^\/api\/proxies\/\d+$/)) {
      var idPart2 = path.replace("/api/proxies/", "");
      return mockResponse(routes["DELETE /api/proxies/"]([idPart2]));
    }
    if (method === "POST" && path.match(/^\/api\/admin\/proxies\/\d+\/stop$/)) {
      var idPart4 = path.replace("/api/admin/proxies/", "").replace("/stop", "");
      return mockResponse(routes["POST /api/admin/proxies/stop"]([idPart4]));
    }
    if (method === "POST" && path.match(/^\/api\/admin\/proxies\/\d+\/start$/)) {
      var idPart5 = path.replace("/api/admin/proxies/", "").replace("/start", "");
      return mockResponse(routes["POST /api/admin/proxies/start"]([idPart5]));
    }
    if (method === "DELETE" && path.match(/^\/api\/admin\/proxies\/\d+$/)) {
      var idPart3 = path.replace("/api/admin/proxies/", "");
      return mockResponse(routes["DELETE /api/admin/proxies/"]([idPart3]));
    }
    if (method === "POST" && path === "/api/admin/login") {
      return mockResponse(routes["POST /api/admin/login"](body));
    }
    if (method === "POST" && path === "/api/admin/logout") {
      return mockResponse(routes["POST /api/admin/logout"]());
    }
    if (method === "GET" && path === "/api/admin/proxies") {
      return mockResponse(routes["GET /api/admin/proxies"]());
    }
    if (method === "GET" && path === "/api/admin/users") {
      return mockResponse(routes["GET /api/admin/users"]());
    }
    if (method === "GET" && path === "/api/show/online") {
      return mockResponse(routes["GET /api/show/online"]());
    }

    return originalFetch.apply(this, arguments);
  };

  function mockResponse(result) {
    return new Promise(function (resolve) {
      setTimeout(function () {
        var ok = result.status >= 200 && result.status < 300;
        resolve({
          ok: ok,
          status: result.status,
          json: function () { return Promise.resolve(result.body); },
          text: function () { return Promise.resolve(JSON.stringify(result.body)); }
        });
      }, 50 + Math.random() * 100);
    });
  }

  window.toast = function (msg) {
    var el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 2000);
  };

  window.copyText = function (text) {
    navigator.clipboard.writeText(text).then(function () {
      window.toast("已复制到剪贴板");
    });
  };

  window.downloadText = function (text, filename) {
    var blob = new Blob([text], { type: "text/plain" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  window.formatBytes = function (bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  };

  window.formatSpeed = function (bps) {
    if (bps < 1024) return bps + " B/s";
    if (bps < 1024 * 1024) return (bps / 1024).toFixed(1) + " KB/s";
    return (bps / (1024 * 1024)).toFixed(2) + " MB/s";
  };
})();
