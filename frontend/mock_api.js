(function () {
  window.USE_MOCK = true;
  window.MOCK_SERVER_HOST = "120.46.51.131";
  window.MOCK_SUBDOMAIN_HOST = "apps.bearfrps.test";

  function makeUid() {
    return "u_" + Math.random().toString(16).slice(2, 10).padEnd(8, "0").slice(0, 8);
  }

  function legacyUid() {
    return localStorage.getItem("mock_uid");
  }

  function currentUid() {
    return localStorage.getItem("mock_user_session_uid");
  }

  function setCurrentUid(uid) {
    localStorage.setItem("mock_user_session_uid", uid);
    localStorage.setItem("mock_uid", uid);
  }

  function clearCurrentUid() {
    localStorage.removeItem("mock_user_session_uid");
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

  function normalizeUsername(username) {
    return String(username || "").trim().toLowerCase();
  }

  function publicUser(user) {
    return {
      uid: user.uid,
      username: user.username,
      created_at: user.created_at,
      balance_mb: user.balance_mb || 0,
      total_recharged_mb: user.total_recharged_mb || 0,
      connection_count: user.connection_count || 0
    };
  }

  function requireUser() {
    let id = currentUid();
    if (!id) return null;
    let user = loadUsers()[id];
    if (!user || !user.username) return null;
    return user;
  }

  function usernameExists(users, username) {
    return Object.values(users).some(function (u) { return u.username === username; });
  }

  function tcpMappings(proxy) {
    proxy.proxy_type = proxy.proxy_type || "tcp";
    if (proxy.proxy_type !== "tcp") return [];
    if (Array.isArray(proxy.tcp_mappings) && proxy.tcp_mappings.length) return proxy.tcp_mappings;
    if (proxy.frps_remote_port != null) {
      return [{
        frps_name: proxy.frps_name || proxy.name,
        remote_port: proxy.frps_remote_port,
        local_port: proxy.local_port || proxy.actual_local_port || 9527,
        actual_local_port: proxy.actual_local_port || proxy.local_port || 9527,
        is_online: !!proxy.is_online,
        current_speed_bps: proxy.current_speed_bps || 0
      }];
    }
    return [];
  }

  function usedTcpPorts() {
    let proxies = loadProxies();
    let used = new Set();
    proxies
      .filter(function (p) { return (p.proxy_type || "tcp") === "tcp" && p.status !== "deleted"; })
      .forEach(function (p) {
        tcpMappings(p).forEach(function (m) { used.add(Number(m.remote_port)); });
      });
    return used;
  }

  function allocateContiguous(count) {
    var used = usedTcpPorts();
    for (let i = mockAllocatableStart; i <= mockAllocatableEnd - count + 1; i++) {
      var ports = [];
      var ok = true;
      for (var j = 0; j < count; j++) {
        var port = i + j;
        if (used.has(port)) { ok = false; break; }
        ports.push(port);
      }
      if (ok) return ports;
    }
    return null;
  }

  function unavailablePorts(ports) {
    var used = usedTcpPorts();
    return ports.filter(function (port) {
      return port < mockAllocatableStart || port > mockAllocatableEnd || used.has(port);
    });
  }

  function validPort(port) {
    return port >= 1 && port <= 65535;
  }

  function localPortsFromStart(start, count) {
    if (!validPort(start) || start + count - 1 > 65535) {
      return { error: "本地端口段必须在 1-65535 之间" };
    }
    var ports = [];
    for (var i = 0; i < count; i++) ports.push(start + i);
    return { ports: ports };
  }

  function buildTcpPortPlan(body, fallbackLocalPort) {
    var cfg = body.tcp_ports || { mode: "auto", count: 1, local_start_port: fallbackLocalPort };
    var mode = cfg.mode || "auto";
    if (mode === "auto") {
      var count = Number(cfg.count || 1);
      if (!count || count < 1 || count > 10) return { error: "单个 TCP 配置最多 10 个端口" };
      var localStart = Number(cfg.local_start_port || fallbackLocalPort);
      var localPlan = localPortsFromStart(localStart, count);
      if (localPlan.error) return localPlan;
      var remotePorts = allocateContiguous(count);
      if (!remotePorts) return { error: "端口池没有连续可用端口段" };
      return { remote_ports: remotePorts, local_ports: localPlan.ports };
    }
    if (mode === "single") {
      var remotePort = Number(cfg.remote_port || 0);
      var localPort = Number(cfg.local_port || 0);
      if (!validPort(remotePort)) return { error: "请输入有效公网端口" };
      if (!validPort(localPort)) return { error: "请输入有效本地端口" };
      var unavailable = unavailablePorts([remotePort]);
      if (unavailable.length) return { error: "公网端口不可用: [" + unavailable.join(", ") + "]" };
      return { remote_ports: [remotePort], local_ports: [localPort] };
    }
    var remoteStart = Number(cfg.remote_start_port || 0);
    var remoteEnd = Number(cfg.remote_end_port || 0);
    var rangeLocalStart = Number(cfg.local_start_port || 0);
    if (!validPort(remoteStart) || !validPort(remoteEnd)) return { error: "请输入有效公网端口段" };
    if (!validPort(rangeLocalStart)) return { error: "请输入有效本地起始端口" };
    if (remoteStart > remoteEnd) return { error: "公网起始端口不能大于结束端口" };
    var rangeCount = remoteEnd - remoteStart + 1;
    if (rangeCount > 10) return { error: "单个 TCP 配置最多 10 个端口" };
    var rangeLocalPlan = localPortsFromStart(rangeLocalStart, rangeCount);
    if (rangeLocalPlan.error) return rangeLocalPlan;
    var requested = [];
    for (var j = 0; j < rangeCount; j++) requested.push(remoteStart + j);
    var blocked = unavailablePorts(requested);
    if (blocked.length) return { error: "公网端口不可用: [" + blocked.join(", ") + "]" };
    return { remote_ports: requested, local_ports: rangeLocalPlan.ports };
  }

  let adminSession = false;
  let mockAllocatableStart = 50000;
  let mockAllocatableEnd = 50100;

  function withPublicUrl(proxy) {
    var p = Object.assign({}, proxy);
    p.proxy_type = p.proxy_type || "tcp";
    p.local_ip = p.local_ip || "127.0.0.1";
    p.local_port = p.local_port || p.actual_local_port || 527;
    if (p.proxy_type === "http") {
      p.public_url = p.subdomain ? "http://" + p.subdomain + "." + window.MOCK_SUBDOMAIN_HOST + ":8080/" : null;
      p.public_urls = p.public_url ? [p.public_url] : [];
      p.tcp_mappings = [];
    } else if (p.proxy_type === "xtcp") {
      p.public_url = null;
      p.public_urls = [];
      p.tcp_mappings = [];
      p.visitor_bind_addr = p.visitor_bind_addr || "127.0.0.1";
      p.visitor_bind_port = p.visitor_bind_port || 9001;
      p.visitor_endpoint = p.visitor_bind_addr + ":" + p.visitor_bind_port;
    } else {
      p.tcp_mappings = tcpMappings(p);
      if (p.tcp_mappings.length) {
        p.frps_remote_port = p.tcp_mappings[0].remote_port;
        p.local_port = p.tcp_mappings[0].local_port;
        p.actual_local_port = p.tcp_mappings[0].actual_local_port;
      }
      p.public_urls = p.tcp_mappings.map(function (m) {
        return "http://" + window.MOCK_SERVER_HOST + ":" + m.remote_port + "/";
      });
      p.public_url = p.public_urls[0] || null;
    }
    return p;
  }

  function makeFrpcConfig(proxy) {
    proxy = withPublicUrl(proxy);
    var lines = [
      'serverAddr = "' + window.MOCK_SERVER_HOST + '"',
      'serverPort = 7000',
      '',
      'auth.method = "token"',
      'auth.token = "bearfrps-internal"',
      'metadatas.token = "' + proxy.token + '"',
      ''
    ];
    if (proxy.proxy_type === "http") {
      lines.push('[[proxies]]');
      lines.push('name = "' + (proxy.frps_name || proxy.name) + '"');
      lines.push('type = "http"');
      lines.push('localIP = "' + proxy.local_ip + '"');
      lines.push('localPort = ' + proxy.local_port);
      lines.push('subdomain = "' + proxy.subdomain + '"');
    } else if (proxy.proxy_type === "xtcp") {
      var secret = proxy.p2p_secret_key || proxy.token;
      var fallbackName = proxy.p2p_fallback_name || ((proxy.frps_name || proxy.name) + "__fallback");
      [
        { name: proxy.frps_name || proxy.name, type: "xtcp" },
        { name: fallbackName, type: "stcp" }
      ].forEach(function (item) {
        lines.push('[[proxies]]');
        lines.push('name = "' + item.name + '"');
        lines.push('type = "' + item.type + '"');
        lines.push('secretKey = "' + secret + '"');
        lines.push('localIP = "' + proxy.local_ip + '"');
        lines.push('localPort = ' + proxy.local_port);
        lines.push('allowUsers = ["*"]');
        lines.push('transport.bandwidthLimit = "' + (proxy.speed_limit_kbps || 1024) + 'KB"');
        lines.push('transport.bandwidthLimitMode = "server"');
        lines.push('');
      });
      return lines.join("\n");
    } else {
      tcpMappings(proxy).forEach(function (m) {
        lines.push('[[proxies]]');
        lines.push('name = "' + m.frps_name + '"');
        lines.push('type = "tcp"');
        lines.push('localIP = "' + proxy.local_ip + '"');
        lines.push('localPort = ' + m.local_port);
        lines.push('remotePort = ' + m.remote_port);
        lines.push('transport.bandwidthLimit = "' + (proxy.speed_limit_kbps || 1024) + 'KB"');
        lines.push('transport.bandwidthLimitMode = "server"');
        lines.push('');
      });
      return lines.join("\n");
    }
    lines.push('transport.bandwidthLimit = "' + (proxy.speed_limit_kbps || 1024) + 'KB"');
    lines.push('transport.bandwidthLimitMode = "server"');
    lines.push('');
    return lines.join("\n");
  }

  function makeVisitorConfig(proxy) {
    proxy = withPublicUrl(proxy);
    if (proxy.proxy_type !== "xtcp") return makeFrpcConfig(proxy);
    var secret = proxy.p2p_secret_key || proxy.token;
    var fallbackName = proxy.p2p_fallback_name || ((proxy.frps_name || proxy.name) + "__fallback");
    var visitorName = (proxy.frps_name || proxy.name) + "__visitor";
    var fallbackVisitorName = fallbackName + "__visitor";
    return [
      'serverAddr = "' + window.MOCK_SERVER_HOST + '"',
      'serverPort = 7000',
      '',
      'auth.method = "token"',
      'auth.token = "bearfrps-internal"',
      'metadatas.token = "' + proxy.token + '"',
      '',
      '[[visitors]]',
      'name = "' + visitorName + '"',
      'type = "xtcp"',
      'serverName = "' + (proxy.frps_name || proxy.name) + '"',
      'secretKey = "' + secret + '"',
      'bindAddr = "' + (proxy.visitor_bind_addr || "127.0.0.1") + '"',
      'bindPort = ' + (proxy.visitor_bind_port || 9001),
      'keepTunnelOpen = true',
      'maxRetriesAnHour = 8',
      'minRetryInterval = 90',
      'fallbackTo = "' + fallbackVisitorName + '"',
      'fallbackTimeoutMs = ' + (proxy.fallback_timeout_ms || 1000),
      '',
      '[[visitors]]',
      'name = "' + fallbackVisitorName + '"',
      'type = "stcp"',
      'serverName = "' + fallbackName + '"',
      'secretKey = "' + secret + '"',
      'bindAddr = "' + (proxy.visitor_bind_addr || "127.0.0.1") + '"',
      'bindPort = -1',
      ''
    ].join("\n");
  }

  function makeFrpcConfigs(proxy) {
    var configs = { server: makeFrpcConfig(proxy) };
    if ((proxy.proxy_type || "tcp") === "xtcp") configs.visitor = makeVisitorConfig(proxy);
    return configs;
  }

  function makeScripts(proxy) {
    var cfg = makeFrpcConfig(proxy);
    var visitorCfg = makeVisitorConfig(proxy);
    var version = "v0.58.1";
    var versionNoV = "0.58.1";
    var host = window.MOCK_SERVER_HOST;
    var binBase = "http://" + host + ":8000/static/demo-server-bin";

    function unixScript(os, config) {
      return "#!/bin/bash\nset -e\n\nARCH=$(uname -m)\ncase $ARCH in\n  x86_64) ARCH=amd64;;\n  aarch64|arm64) ARCH=arm64;;\nesac\n\nif [ ! -f frpc ]; then\n  curl -L -o frp.tar.gz \"https://github.com/fatedier/frp/releases/download/" + version + "/frp_" + versionNoV + "_" + os + "_${ARCH}.tar.gz\"\n  tar xzf frp.tar.gz --strip-components=1 --wildcards \"*/frpc\"\n  chmod +x frpc\nfi\n\ncat > frpc.toml <<'EOF'\n" + config + "EOF\n\n./frpc -c frpc.toml\n";
    }

    function winScript(config) {
      return "if (-not (Test-Path frpc.exe)) {\n  Invoke-WebRequest -Uri 'https://github.com/fatedier/frp/releases/download/" + version + "/frp_" + versionNoV + "_windows_amd64.zip' -OutFile frp.zip\n  Expand-Archive frp.zip -DestinationPath .\n  Move-Item frp_*\\frpc.exe .\n  Remove-Item frp_* -Recurse\n}\n\n$cfg = @\"\n" + config + "\"@\nSet-Content frpc.toml $cfg\n\n.\\frpc.exe -c frpc.toml\n";
    }

    var frpcLinux = unixScript("linux", cfg);
    var frpcMac = unixScript("darwin", cfg);
    var frpcWin = winScript(cfg);

    var demoServerPy = "import http.server, json, time, argparse, os, math\n\nclass Handler(http.server.BaseHTTPRequestHandler):\n    msgs = []\n    COLORS = ['#d1fae5','#dbeafe','#fce7f3','#fef3c7','#ede9fe','#ccfbf1','#fef9c3','#e0e7ff']\n    bg = COLORS[int(time.time()) % len(COLORS)]\n\n    def do_GET(self):\n        if self.path == '/api/messages':\n            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()\n            self.wfile.write(json.dumps(self.msgs).encode())\n        else:\n            html = '<html><head><meta charset=utf-8><style>body{background:'+self.bg+';font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px}input,textarea{width:100%;padding:8px;margin:4px 0;box-sizing:border-box;border:1px solid #ccc;border-radius:4px}button{padding:8px 16px;background:#2563eb;color:#fff;border:none;border-radius:4px;cursor:pointer}.msg{padding:8px;border-bottom:1px solid #e5e7eb}</style></head><body>'\n            html += '<h2>Message Board</h2>'\n            html += '<form onsubmit=\"postMsg();return false\"><input id=nick placeholder=Nickname><textarea id=content placeholder=Message rows=2></textarea><button type=submit>Send</button></form>'\n            html += '<div id=list></div>'\n            html += '<script>function load(){fetch(\"/api/messages\").then(r=>r.json()).then(d=>{document.getElementById(\"list\").innerHTML=d.map(m=>\"<div class=msg><b>\"+m.nickname+\"</b> \"+m.content+\"</div>\").join(\"\")})}function postMsg(){fetch(\"/api/messages\",{method:\"POST\",headers:{\"Content-Type\":\"application/json\"},body:JSON.stringify({nickname:document.getElementById(\"nick\").value,content:document.getElementById(\"content\").value})}).then(load)}setInterval(load,3000);load()</script>'\n            html += '</body></html>'\n            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()\n            self.wfile.write(html.encode())\n\n    def do_POST(self):\n        if self.path == '/api/messages':\n            length = int(self.headers.get('Content-Length',0))\n            data = json.loads(self.rfile.read(length))\n            data['timestamp'] = time.time()\n            self.msgs.append(data)\n            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()\n            self.wfile.write(json.dumps({'ok':True}).encode())\n\nif __name__ == '__main__':\n    p = argparse.ArgumentParser()\n    p.add_argument('--port', type=int, default=527)\n    a = p.parse_args()\n    print(f'Serving on port {a.port}...')\n    http.server.HTTPServer(('0.0.0.0', a.port), Handler).serve_forever()\n";

    var demoLinux = "#!/bin/bash\nread -p 'Local port [default 527]: ' PORT\nPORT=${PORT:-527}\n\ncat > demo_server.py <<'PYEOF'\n" + demoServerPy + "PYEOF\n\nif command -v python3 >/dev/null 2>&1; then\n    python3 demo_server.py --port $PORT\nelse\n    echo 'Python3 not found, downloading binary...'\n    ARCH=$(uname -m)\n    case $ARCH in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac\n    curl -L -o demo-server " + binBase + "/demo-server-linux-${ARCH}\n    chmod +x demo-server\n    ./demo-server --port $PORT\nfi\n";

    var demoMac = "#!/bin/bash\nread -p 'Local port [default 527]: ' PORT\nPORT=${PORT:-527}\n\ncat > demo_server.py <<'PYEOF'\n" + demoServerPy + "PYEOF\n\nif command -v python3 >/dev/null 2>&1; then\n    python3 demo_server.py --port $PORT\nelse\n    echo 'Python3 not found, downloading binary...'\n    ARCH=$(uname -m)\n    case $ARCH in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac\n    curl -L -o demo-server " + binBase + "/demo-server-darwin-${ARCH}\n    chmod +x demo-server\n    ./demo-server --port $PORT\nfi\n";

    var demoWin = "$PORT = Read-Host 'Local port [default 527]'\nif (-not $PORT) { $PORT = 527 }\n\n$script = @'\n" + demoServerPy + "'@\nSet-Content demo_server.py $script\n\ntry { python demo_server.py --port $PORT }\ncatch {\n  Write-Host 'Python not found, downloading binary...'\n  Invoke-WebRequest -Uri '" + binBase + "/demo-server-windows-amd64.exe' -OutFile demo-server.exe\n  .\\demo-server.exe --port $PORT\n}\n";

    var scripts = {
      frpc: { linux: frpcLinux, mac: frpcMac, windows: frpcWin },
      demo: { linux: demoLinux, mac: demoMac, windows: demoWin }
    };
    if ((proxy.proxy_type || "tcp") === "xtcp") {
      scripts.visitor = {
        linux: unixScript("linux", visitorCfg),
        mac: unixScript("darwin", visitorCfg),
        windows: winScript(visitorCfg)
      };
    }
    return scripts;
  }

  function randomTraffic() {
    return Math.floor(Math.random() * 5000000);
  }

  function refreshOnlineStatus() {
    let proxies = loadProxies();
    proxies.forEach(function (p) {
      if (p.status === "active") {
        if ((p.proxy_type || "tcp") === "tcp") {
          p.tcp_mappings = tcpMappings(p).map(function (m) {
            var online = Math.random() > 0.3;
            var speed = online ? Math.floor(Math.random() * 500000) : 0;
            return Object.assign({}, m, {
              is_online: online,
              actual_local_port: m.local_port,
              current_speed_bps: speed
            });
          });
          p.is_online = p.tcp_mappings.some(function (m) { return m.is_online; });
          p.current_speed_bps = p.tcp_mappings.reduce(function (sum, m) { return sum + (m.current_speed_bps || 0); }, 0);
          if (p.tcp_mappings.length) {
            p.frps_remote_port = p.tcp_mappings[0].remote_port;
            p.local_port = p.tcp_mappings[0].local_port;
            p.actual_local_port = p.tcp_mappings[0].actual_local_port;
          }
        } else if ((p.proxy_type || "tcp") === "xtcp") {
          p.p2p_xtcp_is_online = Math.random() > 0.3;
          p.p2p_fallback_is_online = Math.random() > 0.85;
          p.is_online = p.p2p_xtcp_is_online || p.p2p_fallback_is_online;
          p.current_speed_bps = p.p2p_fallback_is_online ? Math.floor(Math.random() * 500000) : 0;
          p.actual_local_port = p.local_port || 527;
        } else {
          p.is_online = Math.random() > 0.3;
          if (p.is_online) {
            p.current_speed_bps = Math.floor(Math.random() * 500000);
            p.actual_local_port = p.local_port || 527;
          } else {
            p.current_speed_bps = 0;
          }
        }
        if (p.is_online && ((p.proxy_type || "tcp") !== "xtcp" || p.p2p_fallback_is_online)) {
          p.traffic_used_bytes = Math.min(p.traffic_used_bytes + Math.floor(Math.random() * 100000), p.traffic_limit_mb * 1024 * 1024);
          p.last_seen_at = new Date().toISOString();
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
    "POST /api/user/register": function (body) {
      var username = normalizeUsername(body && body.username);
      var password = String((body && body.password) || "");
      if (!/^[a-z0-9_]{3,32}$/.test(username)) {
        return { status: 400, body: { detail: "用户名需为 3-32 位字母、数字或下划线" } };
      }
      if (password.length < 8 || password.length > 128) {
        return { status: 400, body: { detail: "密码长度需为 8-128 位" } };
      }

      var users = loadUsers();
      if (usernameExists(users, username)) {
        return { status: 400, body: { detail: "用户名已存在" } };
      }

      var id = legacyUid();
      var user = id ? users[id] : null;
      if (!user || user.username) {
        id = makeUid();
        while (users[id]) id = makeUid();
        user = { uid: id, created_at: new Date().toISOString(), balance_mb: 0, total_recharged_mb: 0, connection_count: 0 };
      }
      user.username = username;
      user.password = password;
      users[id] = user;
      saveUsers(users);
      setCurrentUid(id);
      return { status: 200, body: publicUser(user) };
    },

    "POST /api/user/login": function (body) {
      var username = normalizeUsername(body && body.username);
      var password = String((body && body.password) || "");
      var users = loadUsers();
      var user = Object.values(users).find(function (u) {
        return u.username === username && u.password === password;
      });
      if (!user) return { status: 401, body: { detail: "用户名或密码错误" } };
      setCurrentUid(user.uid);
      return { status: 200, body: publicUser(user) };
    },

    "POST /api/user/logout": function () {
      clearCurrentUid();
      return { status: 200, body: { ok: true } };
    },

    "GET /api/user/me": function () {
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      return { status: 200, body: publicUser(user) };
    },

    "POST /api/user/init": function () {
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      var proxies = loadProxies().filter(function (p) { return p.uid === user.uid && p.status !== "deleted"; });
      user.connection_count = proxies.length;
      return { status: 200, body: publicUser(user) };
    },

    "POST /api/user/recharge": function () {
      var users = loadUsers();
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      user.balance_mb += 100;
      user.total_recharged_mb += 100;
      users[user.uid] = user;
      saveUsers(users);
      return { status: 200, body: { balance_mb: user.balance_mb, total_recharged_mb: user.total_recharged_mb } };
    },

    "GET /api/proxies": function () {
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      refreshOnlineStatus();
      var proxies = loadProxies()
        .filter(function (p) { return p.uid === user.uid && p.status !== "deleted"; })
        .map(withPublicUrl);
      return { status: 200, body: { proxies: proxies } };
    },

    "POST /api/proxies": function (body) {
      var users = loadUsers();
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };

      var proxies = loadProxies();
      var mine = proxies.filter(function (p) { return p.uid === user.uid && p.status !== "deleted"; });
      var proxyType = (body.proxy_type || "tcp").toLowerCase();
      var name = String(body.name || "").trim();
      var localIp = String(body.local_ip || "127.0.0.1").trim();
      var localPort = Number(body.local_port || 9527);
      var visitorBindPort = Number(body.visitor_bind_port || 9001);
      var subdomain = String(body.subdomain || "").trim().toLowerCase();

      if (mine.length >= 3) return { status: 400, body: { detail: "超过最大连接数" } };
      if (body.traffic_mb > user.balance_mb) return { status: 400, body: { detail: "余额不足" } };
      if (!name) return { status: 400, body: { detail: "名称不能为空" } };
      if (mine.some(function (p) { return p.name === name; })) return { status: 400, body: { detail: "名称重复" } };
      if (!/^[A-Za-z0-9.-]{1,253}$/.test(localIp)) return { status: 400, body: { detail: "本地地址格式不合法" } };

      var port = null;
      var tcpPlan = null;
      if (proxyType === "http") {
        if (!localPort || localPort < 1 || localPort > 65535) return { status: 400, body: { detail: "请输入有效本地端口" } };
        if (!/^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$/.test(subdomain)) {
          return { status: 400, body: { detail: "子域名需为 3-63 位小写字母、数字或连字符" } };
        }
        if (proxies.some(function (p) { return p.status !== "deleted" && (p.proxy_type || "tcp") === "http" && p.subdomain === subdomain; })) {
          return { status: 400, body: { detail: "子域名已被占用" } };
        }
      } else if (proxyType === "xtcp") {
        if (!localPort || localPort < 1 || localPort > 65535) return { status: 400, body: { detail: "请输入有效本地端口" } };
        if (!visitorBindPort || visitorBindPort < 1 || visitorBindPort > 65535) return { status: 400, body: { detail: "请输入有效访问端监听端口" } };
      } else {
        proxyType = "tcp";
        tcpPlan = buildTcpPortPlan(body, localPort);
        if (tcpPlan.error) return { status: 400, body: { detail: tcpPlan.error } };
        port = tcpPlan.remote_ports[0];
        localPort = tcpPlan.local_ports[0];
      }

      if (proxyType !== "xtcp") user.balance_mb -= body.traffic_mb;
      users[user.uid] = user;
      saveUsers(users);

      var proxyId = Date.now();
      var frpsName = user.uid + "__" + proxyId;
      var mappings = tcpPlan ? tcpPlan.remote_ports.map(function (remotePort, index) {
        return {
          frps_name: index === 0 ? frpsName : frpsName + "__" + (index + 1),
          remote_port: remotePort,
          local_port: tcpPlan.local_ports[index],
          actual_local_port: tcpPlan.local_ports[index],
          is_online: false,
          current_speed_bps: 0
        };
      }) : [];

      var proxy = {
        id: proxyId,
        uid: user.uid,
        name: name,
        frps_name: frpsName,
        token: makeToken(),
        proxy_type: proxyType,
        frps_remote_port: port,
        local_ip: localIp,
        local_port: localPort,
        subdomain: proxyType === "http" ? subdomain : null,
        tcp_mappings: mappings,
        p2p_secret_key: proxyType === "xtcp" ? makeToken() : null,
        p2p_fallback_name: proxyType === "xtcp" ? frpsName + "__fallback" : null,
        visitor_bind_addr: "127.0.0.1",
        visitor_bind_port: proxyType === "xtcp" ? visitorBindPort : 9001,
        keep_tunnel_open: true,
        fallback_timeout_ms: 1000,
        p2p_xtcp_is_online: false,
        p2p_fallback_is_online: false,
        status: "active",
        is_online: false,
        actual_local_port: localPort,
        speed_limit_kbps: body.speed_limit_kbps || 1024,
        traffic_limit_mb: body.traffic_mb,
        traffic_used_bytes: 0,
        current_speed_bps: 0,
        created_at: new Date().toISOString(),
        last_seen_at: null
      };

      proxy = withPublicUrl(proxy);
      proxies.push(proxy);
      saveProxies(proxies);

      return {
        status: 200,
        body: {
          proxy: proxy,
          frpc_config: makeFrpcConfig(proxy),
          frpc_configs: makeFrpcConfigs(proxy),
          scripts: makeScripts(proxy)
        }
      };
    },

    "DELETE /api/proxies/": function (pathParts) {
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var idx = proxies.findIndex(function (p) { return String(p.id) === idStr && p.uid === user.uid; });
      if (idx === -1) return { status: 404, body: { detail: "Not found" } };
      proxies.splice(idx, 1);
      saveProxies(proxies);
      return { status: 200, body: { ok: true } };
    },

    "GET /api/proxies/": function (pathParts) {
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var proxy = proxies.find(function (p) { return String(p.id) === idStr && p.uid === user.uid; });
      if (!proxy) return { status: 404, body: { detail: "Not found" } };
      proxy = withPublicUrl(proxy);
      return {
        status: 200,
        body: {
          proxy: proxy,
          frpc_config: makeFrpcConfig(proxy),
          frpc_configs: makeFrpcConfigs(proxy),
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
      return { status: 200, body: { proxies: loadProxies().map(withPublicUrl) } };
    },

    "GET /api/admin/users": function () {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var users = loadUsers();
      var proxies = loadProxies();
      var arr = Object.values(users).map(function (u) {
        var count = proxies.filter(function (p) { return p.uid === u.uid && p.status !== "deleted"; }).length;
        return Object.assign(publicUser(u), { connection_count: count });
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

    "GET /api/admin/config": function () {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var proxies = loadProxies();
      var allocated = 0;
      proxies.filter(function (p) {
        return p.status !== "deleted" && (p.proxy_type || "tcp") === "tcp";
      }).forEach(function (p) {
        allocated += tcpMappings(p).length;
      });
      return {
        status: 200,
        body: {
          allocatable_port_range_start: mockAllocatableStart,
          allocatable_port_range_end: mockAllocatableEnd,
          available_port_count: (mockAllocatableEnd - mockAllocatableStart + 1) - allocated
        }
      };
    },

    "PUT /api/admin/config": function (body) {
      if (!adminSession) return { status: 401, body: { detail: "Unauthorized" } };
      var start = Number(body.start);
      var end = Number(body.end);
      if (start < 1 || end > 65535) return { status: 400, body: { detail: "端口范围必须在 1-65535 之间" } };
      if (start > end) return { status: 400, body: { detail: "起始端口不能大于结束端口" } };
      var proxies = loadProxies();
      for (var i = 0; i < proxies.length; i++) {
        var p = proxies[i];
        if (p.status !== "deleted" && (p.proxy_type || "tcp") === "tcp") {
          var outside = tcpMappings(p).map(function (m) { return Number(m.remote_port); }).filter(function (port) {
            return port < start || port > end;
          });
          if (outside.length) {
            return { status: 400, body: { detail: "新区间不覆盖已分配端口: [" + outside.join(", ") + "]" } };
          }
        }
      }
      mockAllocatableStart = start;
      mockAllocatableEnd = end;
      return { status: 200, body: { ok: true } };
    },

    "GET /api/show/online": function () {
      refreshOnlineStatus();
      var proxies = loadProxies().filter(function (p) {
        return p.is_online && p.status === "active";
      });
      var result = proxies.map(function (p) {
        p = withPublicUrl(p);
        return {
          id: p.id,
          name: p.name,
          proxy_type: p.proxy_type,
          remote_port: p.frps_remote_port,
          remote_ports: tcpMappings(p).map(function (m) { return m.remote_port; }),
          tcp_mappings: p.tcp_mappings || [],
          public_url: p.public_url,
          public_urls: p.public_urls || [],
          visitor_endpoint: p.visitor_endpoint || null
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

    if (method === "POST" && path === "/api/user/register") {
      return mockResponse(routes["POST /api/user/register"](body));
    }
    if (method === "POST" && path === "/api/user/login") {
      return mockResponse(routes["POST /api/user/login"](body));
    }
    if (method === "POST" && path === "/api/user/logout") {
      return mockResponse(routes["POST /api/user/logout"]());
    }
    if (method === "GET" && path === "/api/user/me") {
      return mockResponse(routes["GET /api/user/me"]());
    }
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
    if (method === "GET" && path === "/api/admin/config") {
      return mockResponse(routes["GET /api/admin/config"]());
    }
    if (method === "PUT" && path === "/api/admin/config") {
      return mockResponse(routes["PUT /api/admin/config"](body));
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
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () {
        window.toast("已复制到剪贴板");
      });
      return;
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;left:-9999px;top:-9999px;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      window.toast("已复制到剪贴板");
    } catch (e) {
      window.toast("复制失败，请手动复制");
    }
    document.body.removeChild(ta);
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
