#!/bin/bash
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
