#!/usr/bin/env python3
"""@file frontend/dev_serve.py
@brief 本地开发时提供前端静态文件服务，并附加 CORS 与 no-store 响应头。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：Python 标准库 http.server、functools、sys、os。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和开发用途说明。
  该脚本只用于前端静态调试，正式运行由 FastAPI 挂载 frontend 目录。
  no-store 头避免浏览器缓存 mock_api.js，便于课堂演示时快速刷新状态。
  CORS 头允许前端页面在不同端口访问后端 API。
"""

import http.server
import functools
import sys
import os

PORT = 3000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    with http.server.HTTPServer(("", port), CORSHandler) as httpd:
        print(f"Dev server running at http://localhost:{port}/")
        print(f"Serving files from: {DIRECTORY}")
        print(f"Mock mode: ON (mock_api.js enabled)")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
