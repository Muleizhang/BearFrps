/*
  @file frontend/mock_api.js
  @brief 为前端页面提供浏览器内 mock API，便于无后端时进行页面演示和交互验证。
  @author BearFrps课程设计小组
  @course 武汉大学开源软件与技术课程 2026
  @date 2026-06-10
  @version 1.0
  @copyright Apache-2.0
  @details
    依赖关系：浏览器 localStorage、Fetch API、Blob、URL。
    修改记录：2026-06-10，补充 Doxygen 风格文件头、mock 数据边界和接口说明。
    本文件直接打开 HTML 时默认 USE_MOCK=true。
    通过 FastAPI /mock_api.js 加载时，后端会把 USE_MOCK 改为 false。
    USE_MOCK=false 时不会拦截 fetch，页面直接访问真实后端 API。

    mock 用户、代理、端口池和 session 存在 localStorage。
    mock 数据只用于前端演示，不代表服务端真实权限。
    clearCurrentUid 仅清理浏览器模拟 session，不影响真实后端 cookie。

    /api/user/register、/login、/logout、/me。
    /api/user/frpc-token、/rotate、/recharge。
    /api/proxies 创建、列表、删除和脚本获取。
    /api/admin/login、/logout、/config、/proxies、/users。
    /api/show/online 展示在线代理。

    makeFrpcConfig 与后端 script_renderer 保持字段语义一致。
    TCP 多端口映射和端口池冲突按前端可演示的方式近似模拟。
    tokenForProxy 兼容旧代理 token 和新用户级 frpc token。
    statusBadge/statusClass 与真实页面状态文案保持一致。

    mock token 不具备真实安全性，不可作为生产认证方案。
    正式运行时后端覆盖 USE_MOCK=false，避免浏览器本地数据绕过真实 API。

    mock_users 保存用户资料、余额、密码和 frpc token。
    mock_proxies 保存代理列表和脚本生成需要的字段。
    mock_uid 兼容旧匿名用户。
    mock_user_session_uid 表示当前浏览器模拟登录用户。
    mock_admin_session 表示管理员模拟登录状态。

    requireUser 先确认当前模拟用户存在。
    检查余额、名称、连接数和代理类型。
    TCP 代理通过 allocateTcpPlan 生成远程端口映射。
    HTTP 代理生成 subdomain 和 public_url。
    XTCP 代理生成 xtcp 服务端配置、stcp fallback 配置和 visitor 配置。
    创建成功后扣减用户余额，并把 proxy 写入 localStorage。

    makeFrpcConfig 输出服务端代理配置。
    makeVisitorConfig 输出 XTCP visitor 和 stcp fallback visitor 配置。
    makeFrpcConfigs 把 server/visitor 两类配置聚合。
    makeScripts 输出 Linux、macOS 和 Windows 脚本。
    demo 脚本内嵌简化版留言板服务，便于离线演示。

    mockAllocatableStart/mockAllocatableEnd 模拟管理员端口池配置。
    auto 模式寻找连续端口。
    single 模式直接校验指定端口。
    range 模式校验指定连续范围。
    allocatedRemotePorts 汇总当前未删除代理占用端口。
    HTTP 代理不占用 TCP remotePort。

    refreshOnlineStatus 周期性随机改变在线状态和速度。
    statusClass/cardStatusClass/statusBadge 与真实后端 DTO 字段兼容。
    show/online 只返回 active 且 is_online 的代理。
    deleted 代理保留在 localStorage 中，但普通列表会过滤。

    tcpMappings 同时读取 tcp_mappings 和旧版 frps_remote_port/local_port。
    withPublicUrl 为旧数据补齐 public_url 和 public_urls。
    normalizeAdvancedConfig 兼容缺失的高级配置字段。
    tokenForProxy 优先用户级 token，缺失时回退代理 token。

    mockError 返回与 FastAPI detail 类似的结构。
    fetch 拦截器把错误包装成 Response，便于页面统一处理。
    未匹配路由返回 404，避免静默成功掩盖页面调用错误。
    JSON 解析失败会让调用方看到异常，便于开发阶段定位问题。

    makeUid 生成模拟用户 uid。
    legacyUid 读取旧版匿名 uid。
    currentUid 读取当前模拟登录用户。
    setCurrentUid 写入当前模拟登录用户。
    clearCurrentUid 清除当前模拟登录用户。
    loadUsers 读取 localStorage 中的用户表。
    saveUsers 写回用户表。
    loadProxies 读取代理列表。
    saveProxies 写回代理列表。
    normalizeUsername 统一用户名格式。
    makeUserToken 生成模拟用户 frpc token。
    tokenForProxy 兼容用户级 token 和代理级 token。
    tcpMappings 统一读取 TCP 映射。
    proxyPorts 返回代理占用的远程端口。
    allocatedRemotePorts 统计当前已占用端口集合。
    findAvailablePorts 查找连续可用端口。
    allocateTcpPlan 按端口模式生成远程端口计划。
    normalizeAdvancedConfig 过滤和规范化高级配置。
    normalizeHttpLocations 解析 HTTP 路径列表。
    normalizeHostHeader 校验 Host header rewrite。
    withPublicUrl 补齐公开访问 URL。
    tomlBool 输出 TOML 布尔值。
    tomlString 输出 TOML 字符串。
    tomlArray 输出 TOML 数组。
    pushTransportLines 输出传输高级配置。
    pushHttpAdvancedLines 输出 HTTP 高级配置。
    makeFrpcConfig 输出服务端 frpc 配置。
    makeVisitorConfig 输出 visitor 配置。
    makeFrpcConfigs 聚合配置对象。
    makeScripts 输出三平台启动脚本。
    randomTraffic 生成模拟流量。
    refreshOnlineStatus 模拟在线状态变化。
    statusClass 输出表格状态类。
    cardStatusClass 输出卡片状态类。
    statusBadge 输出状态文案。
    mockResponse 构造 Response 对象。
    apiError 构造页面可读错误。
    fallbackCopy 处理剪贴板回退。
    downloadText 下载脚本文本。

    POST /api/user/register 创建模拟用户。
    POST /api/user/login 登录模拟用户。
    POST /api/user/logout 清除模拟会话。
    GET /api/user/me 返回当前模拟用户。
    GET /api/user/frpc-token 返回用户级 token。
    POST /api/user/frpc-token/rotate 轮换用户级 token。
    POST /api/user/recharge 增加模拟余额。
    GET /api/proxies 返回当前用户代理。
    POST /api/proxies 创建模拟代理。
    GET /api/proxies/{id}/scripts 返回配置和脚本。
    DELETE /api/proxies/{id} 删除当前用户代理。
    POST /api/admin/login 创建模拟管理员会话。
    POST /api/admin/logout 清除模拟管理员会话。
    GET /api/admin/config 返回端口池范围。
    POST /api/admin/config 更新端口池范围。
    GET /api/admin/proxies 返回所有代理。
    POST /api/admin/proxies/{id}/stop 停用代理。
    POST /api/admin/proxies/{id}/start 恢复代理。
    DELETE /api/admin/proxies/{id} 删除代理。
    GET /api/admin/users 返回用户列表。
    GET /api/show/online 返回在线展示列表。

    mock 密码以明文保存在 localStorage，只用于离线演示。
    mock 在线状态随机变化，不代表真实 frps 连接。
    mock 流量随机增长，不代表真实流量计费。
    mock 管理员认证只检查固定用户名和密码。
    mock 不启动 frps，也不验证真实端口是否被本机占用。
    mock 不执行脚本，只返回脚本文本。
    mock 的错误信息尽量贴近后端 detail，但不是后端完整校验。
    mock 的 token 轮换会同步代理兼容字段，便于页面继续展示。

    后端新增字段时，先更新 DTO 兼容函数，再更新页面展示。
    后端新增代理类型时，需要补充创建 payload、配置生成和路由模拟。
    修改脚本模板字段时，应同步 script_renderer 和 mock_api。
    localStorage 数据结构变更时，应保留旧字段兼容，避免刷新后页面崩溃。
    真实运行时 USE_MOCK=false，不能依赖 mock 独有行为。

    mock 支持用户注册。
    mock 支持用户登录。
    mock 支持用户退出。
    mock 支持免费充值。
    mock 支持 frpc token 查询。
    mock 支持 frpc token 轮换。
    mock 支持 TCP 代理创建。
    mock 支持 HTTP 代理创建。
    mock 支持 XTCP 代理创建。
    mock 支持管理员登录。
    mock 支持端口池配置。
    mock 支持代理停用。
    mock 支持代理恢复。
    mock 支持代理删除。
    mock 支持展示页在线列表。
    mock 支持脚本复制和下载辅助函数。
    mock 支持旧字段兼容。
    mock 支持流量和速度模拟。
    mock 支持错误响应统一结构。

    README 的本地预览可以直接使用 mock。
    测试计划中的手工验收可用 mock 做前端预演。
    开源合规文档不把 mock 视作第三方组件。
    注释规范要求的业务逻辑说明集中写在本文件头。
    真实后端 API 变化时，本文件应同步更新以保持文档一致。

    mock 用户表对应课程需求中的 User。
    mock 代理表对应课程需求中的 Proxy。
    mock 余额字段对应充值和流量扣减要求。
    mock 端口池对应公网 remote_port_pool。
    mock scripts 返回值对应配置与脚本模态框。
    mock show/online 对应公网展示聚合页。
    mock admin/config 对应管理员端口池调整。
    mock token 轮换对应多用户令牌隔离。
    mock TCP mappings 对应多端口 TCP 代理。
    mock visitor 配置对应 XTCP 和 stcp fallback 访问者脚本。

    mock 不替代 pytest 自动化测试。
    mock 不替代 frps/frpc 真实连通性测试。
    mock 不保存敏感生产数据。
    mock 不参与后端权限判断。
    mock 仅用于前端离线演示和课程答辩预览。

    新增真实后端 API 时必须补 mock 路由。
    新增 DTO 字段时必须补 withPublicUrl 或兼容函数。
    新增脚本占位符时必须补 makeScripts。
    新增代理状态时必须补 statusBadge。
    修改 localStorage 结构时必须保留迁移兼容。
    修改管理员接口时必须同步 admin.html。
    提交前必须通过 node --check。

    改动用户数据结构时记录迁移策略。
    改动代理数据结构时记录旧字段兼容方式。
    改动脚本生成时记录和后端 renderer 的一致性。
    改动状态模拟时记录对展示页的影响。
    改动错误响应时记录页面 apiError 是否仍可解析。

    mock 用于前端离线演示。
    mock 不替代真实 frps 联调。
    mock 数据存放在浏览器本地。
    mock 关闭后页面访问真实后端。
    mock 帮助说明前后端接口契约。
  @section mock_doxygen Doxygen 注释约束
    mock API 是接口契约示例，路由新增必须补充 @section。
    端口、token、脚本和权限相关逻辑必须说明与真实后端的差异。
    大段内嵌脚本文本不逐行注释，避免破坏脚本原文。
    修改 localStorage schema 时需要说明迁移或兼容策略。
    mock 逻辑不作为安全实现，注释中必须保留此边界。
  @section mock_submission 平时作业提交检查
    mock 必须支持用户端无后端预览。
    mock 必须支持管理端无后端预览。
    mock 必须支持展示页无后端预览。
    mock 必须保持主要 API 路径与后端一致。
    mock 必须保持错误响应 detail 字段。
    mock 必须能通过 node --check。
  @section mock_traceability 可追踪性
    用户数据对应 backend.models.User。
    代理数据对应 backend.models.Proxy。
    TCP 映射对应 backend.models.TcpMapping。
    token 轮换对应用户级 frpc_token_version。
    show online 对应 backend.routes.show_api。
    admin config 对应 backend.routes.admin_api。
    proxy scripts 对应 backend.script_renderer。
  @section mock_security_boundary 安全边界
    mock 中的密码不是安全存储。
    mock 中的 token 不是安全随机令牌。
    mock 中的在线状态不是 frps 实际状态。
    mock 中的流量不是实际网络流量。
    mock 只用于 UI 和接口契约演示。
    生产运行必须依赖真实 FastAPI 后端。
  @section mock_demo 演示流程映射
    mock 可以演示用户注册。
    mock 可以演示用户登录。
    mock 可以演示充值。
    mock 可以演示代理创建。
    mock 可以演示脚本弹窗。
    mock 可以演示管理员登录。
    mock 可以演示代理停用。
    mock 可以演示展示页在线列表。
    mock 可以在没有 frps 时预演口头报告。
  @section mock_validation 输入校验边界
    用户名会统一小写。
    密码只做演示级长度检查。
    代理名不能为空。
    traffic_mb 必须能转成数字。
    TCP remotePort 必须在 mock 端口池中。
    HTTP subdomain 会做简单规范化。
    高级配置只做前端演示级校验。
  @section mock_runtime 运行时约束
    fetch 拦截只在 USE_MOCK=true 时生效。
    mockResponse 模拟浏览器 Response。
    localStorage 读写可能被浏览器隐私设置限制。
    随机在线状态只用于视觉演示。
    mock 不启动本地 demo 服务。
    mock 不下载 frpc 二进制。
    mock 不写入后端 config 目录。
  @section mock_license 许可证和来源
    本文件属于 BearFrps 根项目。
    根项目许可证为 Apache-2.0。
    前端第三方依赖见 SBOM.json。
    开源声明见 NOTICE。
    Git 仓库地址见 README。
*/

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
    ensureFrpcToken(user);
    return {
      uid: user.uid,
      username: user.username,
      created_at: user.created_at,
      frpc_token_version: user.frpc_token_version,
      frpc_token_rotated_at: user.frpc_token_rotated_at,
      balance_mb: user.balance_mb || 0,
      total_recharged_mb: user.total_recharged_mb || 0,
      connection_count: user.connection_count || 0
    };
  }

  function ensureFrpcToken(user) {
    if (!user.frpc_token) user.frpc_token = makeToken();
    if (!user.frpc_token_version) user.frpc_token_version = 1;
    if (!user.frpc_token_rotated_at) user.frpc_token_rotated_at = user.created_at || new Date().toISOString();
    return user;
  }

  function frpcTokenBody(user) {
    ensureFrpcToken(user);
    return {
      token: user.frpc_token,
      version: user.frpc_token_version,
      rotated_at: user.frpc_token_rotated_at
    };
  }

  function tokenForProxy(proxy) {
    var users = loadUsers();
    var user = proxy && proxy.uid ? users[proxy.uid] : null;
    if (user) {
      ensureFrpcToken(user);
      users[user.uid] = user;
      saveUsers(users);
      return user.frpc_token;
    }
    return (proxy && proxy.token) || makeToken();
  }

  function syncProxyTokens(uid, token) {
    var proxies = loadProxies();
    proxies.forEach(function (proxy) {
      if (proxy.uid === uid && proxy.status !== "deleted") proxy.token = token;
    });
    saveProxies(proxies);
  }

  function requireUser() {
    let id = currentUid();
    if (!id) return null;
    let users = loadUsers();
    let user = users[id];
    if (!user || !user.username) return null;
    ensureFrpcToken(user);
    users[id] = user;
    saveUsers(users);
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
    var mappingMode = cfg.mapping_mode === "many-to-many" ? "many-to-many" : "many-to-one";
    if (!validPort(remoteStart) || !validPort(remoteEnd)) return { error: "请输入有效公网端口段" };
    if (!validPort(rangeLocalStart)) return { error: mappingMode === "many-to-many" ? "请输入有效本地起始端口" : "请输入有效本地端口" };
    if (remoteStart > remoteEnd) return { error: "公网起始端口不能大于结束端口" };
    var rangeCount = remoteEnd - remoteStart + 1;
    if (rangeCount > 10) return { error: "单个 TCP 配置最多 10 个端口" };
    var rangeLocalPlan = mappingMode === "many-to-many"
      ? localPortsFromStart(rangeLocalStart, rangeCount)
      : { ports: Array(rangeCount).fill(rangeLocalStart) };
    if (rangeLocalPlan.error) return rangeLocalPlan;
    var requested = [];
    for (var j = 0; j < rangeCount; j++) requested.push(remoteStart + j);
    var blocked = unavailablePorts(requested);
    if (blocked.length) return { error: "公网端口不可用: [" + blocked.join(", ") + "]" };
    return { remote_ports: requested, local_ports: rangeLocalPlan.ports };
  }

  function cleanOptional(value) {
    var text = String(value || "").trim();
    return text || null;
  }

  function normalizeHttpLocations(values) {
    var locations = Array.isArray(values) ? values : [];
    var normalized = [];
    for (var i = 0; i < locations.length; i++) {
      var location = String(locations[i] || "").trim();
      if (!location) continue;
      if (location.charAt(0) !== "/") return { error: "HTTP 路径必须以 / 开头" };
      if (/\s/.test(location)) return { error: "HTTP 路径不能包含空白字符" };
      normalized.push(location);
    }
    if (normalized.length > 10) return { error: "HTTP 路径最多 10 条" };
    return { locations: normalized };
  }

  function normalizeHostHeader(value) {
    var host = cleanOptional(value);
    if (!host) return { host: null };
    if (!/^[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?$/.test(host)) {
      return { error: "Host 改写格式不合法" };
    }
    var parts = host.split(":");
    if (parts.length === 2) {
      var port = Number(parts[1]);
      if (!port || port < 1 || port > 65535) return { error: "Host 改写端口不合法" };
    }
    var hostname = parts[0];
    if (hostname.indexOf("..") !== -1 || hostname.charAt(0) === "." || hostname.charAt(hostname.length - 1) === ".") {
      return { error: "Host 改写格式不合法" };
    }
    return { host: host };
  }

  function normalizeAdvancedConfig(config, proxyType) {
    config = config || {};
    var mode = config.bandwidth_limit_mode === "client" ? "client" : "server";
    var httpUser = cleanOptional(config.http_user);
    var httpPassword = cleanOptional(config.http_password);
    if (!!httpUser !== !!httpPassword) {
      return { error: "HTTP 认证用户名和密码需同时填写" };
    }
    var result = {
      use_encryption: !!config.use_encryption,
      use_compression: !!config.use_compression,
      bandwidth_limit_mode: mode,
      http_user: null,
      http_password: null,
      http_locations: [],
      host_header_rewrite: null,
      keep_tunnel_open: config.keep_tunnel_open == null ? true : !!config.keep_tunnel_open,
      fallback_timeout_ms: config.fallback_timeout_ms == null ? 1000 : Number(config.fallback_timeout_ms)
    };
    if (!result.fallback_timeout_ms || result.fallback_timeout_ms < 100 || result.fallback_timeout_ms > 10000) {
      return { error: "fallback 超时需在 100-10000 ms 之间" };
    }
    if (proxyType === "http") {
      var locations = normalizeHttpLocations(config.http_locations);
      if (locations.error) return locations;
      var hostHeader = normalizeHostHeader(config.host_header_rewrite);
      if (hostHeader.error) return hostHeader;
      result.http_user = httpUser;
      result.http_password = httpPassword;
      result.http_locations = locations.locations;
      result.host_header_rewrite = hostHeader.host;
    }
    return result;
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
      p.public_url = p.subdomain ? "http://" + p.subdomain + "." + window.MOCK_SUBDOMAIN_HOST + "/" : null;
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

  function tomlBool(value) {
    return value ? "true" : "false";
  }

  function tomlString(value) {
    return String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function tomlArray(values) {
    return "[" + values.map(function (value) {
      return '"' + tomlString(value) + '"';
    }).join(", ") + "]";
  }

  function pushTransportLines(lines, proxy) {
    lines.push('transport.bandwidthLimit = "' + (proxy.speed_limit_kbps || 1024) + 'KB"');
    lines.push('transport.bandwidthLimitMode = "' + (proxy.bandwidth_limit_mode || "server") + '"');
    lines.push('transport.useEncryption = ' + tomlBool(!!proxy.use_encryption));
    lines.push('transport.useCompression = ' + tomlBool(!!proxy.use_compression));
  }

  function pushHttpAdvancedLines(lines, proxy) {
    if (proxy.http_user && proxy.http_password) {
      lines.push('httpUser = "' + tomlString(proxy.http_user) + '"');
      lines.push('httpPassword = "' + tomlString(proxy.http_password) + '"');
    }
    if (Array.isArray(proxy.http_locations) && proxy.http_locations.length) {
      lines.push("locations = " + tomlArray(proxy.http_locations));
    }
    if (proxy.host_header_rewrite) {
      lines.push('hostHeaderRewrite = "' + tomlString(proxy.host_header_rewrite) + '"');
    }
  }

  function makeFrpcConfig(proxy) {
    proxy = withPublicUrl(proxy);
    var token = tokenForProxy(proxy);
    var lines = [
      'serverAddr = "' + window.MOCK_SERVER_HOST + '"',
      'serverPort = 7000',
      '',
      'auth.method = "token"',
      'auth.token = "bearfrps-internal"',
      'metadatas.token = "' + tomlString(token) + '"',
      'metadatas.uid = "' + tomlString(proxy.uid || "") + '"',
      ''
    ];
    if (proxy.proxy_type === "http") {
      lines.push('[[proxies]]');
      lines.push('name = "' + (proxy.frps_name || proxy.name) + '"');
      lines.push('type = "http"');
      lines.push('localIP = "' + proxy.local_ip + '"');
      lines.push('localPort = ' + proxy.local_port);
      lines.push('subdomain = "' + proxy.subdomain + '"');
      pushHttpAdvancedLines(lines, proxy);
      pushTransportLines(lines, proxy);
      lines.push('');
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
        pushTransportLines(lines, proxy);
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
        pushTransportLines(lines, proxy);
        lines.push('');
      });
      return lines.join("\n");
    }
    return lines.join("\n");
  }

  function makeVisitorConfig(proxy) {
    proxy = withPublicUrl(proxy);
    if (proxy.proxy_type !== "xtcp") return makeFrpcConfig(proxy);
    var token = tokenForProxy(proxy);
    var secret = proxy.p2p_secret_key || token;
    var fallbackName = proxy.p2p_fallback_name || ((proxy.frps_name || proxy.name) + "__fallback");
    var visitorName = (proxy.frps_name || proxy.name) + "__visitor";
    var fallbackVisitorName = fallbackName + "__visitor";
    return [
      'serverAddr = "' + window.MOCK_SERVER_HOST + '"',
      'serverPort = 7000',
      '',
      'auth.method = "token"',
      'auth.token = "bearfrps-internal"',
      'metadatas.token = "' + tomlString(token) + '"',
      'metadatas.uid = "' + tomlString(proxy.uid || "") + '"',
      '',
      '[[visitors]]',
      'name = "' + visitorName + '"',
      'type = "xtcp"',
      'serverName = "' + (proxy.frps_name || proxy.name) + '"',
      'secretKey = "' + secret + '"',
      'bindAddr = "' + (proxy.visitor_bind_addr || "127.0.0.1") + '"',
      'bindPort = ' + (proxy.visitor_bind_port || 9001),
      'keepTunnelOpen = ' + tomlBool(proxy.keep_tunnel_open !== false),
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
      ensureFrpcToken(user);
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

    "GET /api/user/frpc-token": function () {
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      return { status: 200, body: frpcTokenBody(user) };
    },

    "POST /api/user/frpc-token/rotate": function () {
      var users = loadUsers();
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      user.frpc_token = makeToken();
      user.frpc_token_version = Number(user.frpc_token_version || 1) + 1;
      user.frpc_token_rotated_at = new Date().toISOString();
      users[user.uid] = user;
      saveUsers(users);
      syncProxyTokens(user.uid, user.frpc_token);
      return { status: 200, body: frpcTokenBody(user) };
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
      ensureFrpcToken(user);
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
      var advanced = normalizeAdvancedConfig(body.advanced_config, proxyType);
      if (advanced.error) return { status: 400, body: { detail: advanced.error } };

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
        token: user.frpc_token,
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
        keep_tunnel_open: advanced.keep_tunnel_open,
        fallback_timeout_ms: advanced.fallback_timeout_ms,
        use_encryption: advanced.use_encryption,
        use_compression: advanced.use_compression,
        bandwidth_limit_mode: advanced.bandwidth_limit_mode,
        http_user: advanced.http_user,
        http_password: advanced.http_password,
        http_locations: advanced.http_locations,
        host_header_rewrite: advanced.host_header_rewrite,
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

    "PATCH /api/proxies/": function (pathParts, body) {
      var users = loadUsers();
      var user = requireUser();
      if (!user) return { status: 401, body: { detail: "user login required" } };
      var idStr = pathParts[0];
      var proxies = loadProxies();
      var proxy = proxies.find(function (p) { return String(p.id) === idStr && p.uid === user.uid && p.status !== "deleted"; });
      if (!proxy) return { status: 404, body: { detail: "Not found" } };

      var name = body.name == null ? null : String(body.name || "").trim();
      if (name != null) {
        if (!name) return { status: 400, body: { detail: "名称不能为空" } };
        if (proxies.some(function (p) { return p.uid === user.uid && p.status !== "deleted" && String(p.id) !== idStr && p.name === name; })) {
          return { status: 400, body: { detail: "名称重复" } };
        }
        proxy.name = name;
      }
      if (body.local_ip != null) {
        var localIp = String(body.local_ip || "127.0.0.1").trim();
        if (!/^[A-Za-z0-9.-]{1,253}$/.test(localIp)) return { status: 400, body: { detail: "本地地址格式不合法" } };
        proxy.local_ip = localIp;
      }
      if (body.local_port != null) {
        var localPort = Number(body.local_port);
        if (!localPort || localPort < 1 || localPort > 65535) return { status: 400, body: { detail: "请输入有效本地端口" } };
        if ((proxy.proxy_type || "tcp") === "tcp" && proxy.tcp_mappings && proxy.tcp_mappings.length) {
          var offset = localPort - Number(proxy.tcp_mappings[0].local_port);
          for (var i = 0; i < proxy.tcp_mappings.length; i++) {
            var nextPort = Number(proxy.tcp_mappings[i].local_port) + offset;
            if (nextPort < 1 || nextPort > 65535) return { status: 400, body: { detail: "本地端口段必须在 1-65535 之间" } };
            proxy.tcp_mappings[i].local_port = nextPort;
            proxy.tcp_mappings[i].actual_local_port = nextPort;
          }
          proxy.local_port = proxy.tcp_mappings[0].local_port;
          proxy.actual_local_port = proxy.tcp_mappings[0].actual_local_port;
        } else {
          proxy.local_port = localPort;
          proxy.actual_local_port = localPort;
        }
      }
      if (body.speed_limit_kbps != null) proxy.speed_limit_kbps = Number(body.speed_limit_kbps);
      if (body.traffic_mb != null) {
        var trafficMb = Number(body.traffic_mb);
        if (!trafficMb || trafficMb < 1) return { status: 400, body: { detail: "请输入流量额度" } };
        if (trafficMb * 1024 * 1024 < Number(proxy.traffic_used_bytes || 0)) return { status: 400, body: { detail: "分配流量不能小于已用流量" } };
        if ((proxy.proxy_type || "tcp") !== "xtcp" && trafficMb > proxy.traffic_limit_mb) {
          var extra = trafficMb - proxy.traffic_limit_mb;
          if (extra > user.balance_mb) return { status: 400, body: { detail: "余额不足" } };
          user.balance_mb -= extra;
          users[user.uid] = user;
          saveUsers(users);
        }
        proxy.traffic_limit_mb = trafficMb;
      }
      if ((proxy.proxy_type || "tcp") === "http" && body.subdomain != null) {
        var subdomain = String(body.subdomain || "").trim().toLowerCase();
        if (!/^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$/.test(subdomain)) {
          return { status: 400, body: { detail: "子域名需为 3-63 位小写字母、数字或连字符" } };
        }
        if (proxies.some(function (p) { return p.status !== "deleted" && (p.proxy_type || "tcp") === "http" && String(p.id) !== idStr && p.subdomain === subdomain; })) {
          return { status: 400, body: { detail: "子域名已被占用" } };
        }
        proxy.subdomain = subdomain;
      }
      if ((proxy.proxy_type || "tcp") === "xtcp" && body.visitor_bind_port != null) {
        var visitorPort = Number(body.visitor_bind_port);
        if (!visitorPort || visitorPort < 1 || visitorPort > 65535) return { status: 400, body: { detail: "请输入有效访问端监听端口" } };
        proxy.visitor_bind_port = visitorPort;
      }
      if (body.advanced_config) {
        var advanced = normalizeAdvancedConfig(body.advanced_config, proxy.proxy_type || "tcp");
        if (advanced.error) return { status: 400, body: { detail: advanced.error } };
        proxy.use_encryption = advanced.use_encryption;
        proxy.use_compression = advanced.use_compression;
        proxy.bandwidth_limit_mode = advanced.bandwidth_limit_mode;
        proxy.http_user = advanced.http_user;
        proxy.http_password = advanced.http_password;
        proxy.http_locations = advanced.http_locations;
        proxy.host_header_rewrite = advanced.host_header_rewrite;
        if ((proxy.proxy_type || "tcp") === "xtcp") {
          proxy.keep_tunnel_open = advanced.keep_tunnel_open;
          proxy.fallback_timeout_ms = advanced.fallback_timeout_ms;
        }
      }
      proxy = withPublicUrl(proxy);
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
    if (method === "GET" && path === "/api/user/frpc-token") {
      return mockResponse(routes["GET /api/user/frpc-token"]());
    }
    if (method === "POST" && path === "/api/user/frpc-token/rotate") {
      return mockResponse(routes["POST /api/user/frpc-token/rotate"]());
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
    if (method === "PATCH" && path.match(/^\/api\/proxies\/\d+$/)) {
      var idPart6 = path.replace("/api/proxies/", "");
      return mockResponse(routes["PATCH /api/proxies/"]([idPart6], body));
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
