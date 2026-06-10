#!/bin/bash
## @file demo-server/build.sh
#  @brief 构建 demo 留言板 Go 兜底二进制，并同步 Python 版到 static 目录。
#  @author BearFrps课程设计小组
#  @course 武汉大学开源软件与技术课程 2026
#  @date 2026-06-10
#  @version 1.0
#  @copyright Apache-2.0
#  @details
#   依赖关系：bash、Go 工具链、demo-server/main.go、demo_server.py。
#   修改记录：2026-06-10，补充 Doxygen 风格文件头和构建产物说明。
#   Python 版作为首选 demo 服务，方便用户查看源码。
#   Go 版用于没有 Python 环境的用户，按 linux/darwin/windows 输出二进制。
#   生成文件放入 static/demo-server-bin，供后端静态服务下载。
#   该脚本会覆盖同名构建产物，不修改用户配置或代理数据。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
OUT_DIR="$REPO_ROOT/static/demo-server-bin"

mkdir -p "$OUT_DIR"
cp "$SCRIPT_DIR/demo_server.py" "$OUT_DIR/demo_server.py"

build() {
  local goos="$1"
  local goarch="$2"
  local suffix="$3"
  local output="$OUT_DIR/demo-server-${goos}-${goarch}${suffix}"
  echo "构建 $output"
  GOOS="$goos" GOARCH="$goarch" CGO_ENABLED=0 go build -o "$output" "$SCRIPT_DIR/main.go"
}

build linux amd64 ""
build darwin amd64 ""
build darwin arm64 ""
build windows amd64 ".exe"

echo "完成，产物位于 $OUT_DIR"
