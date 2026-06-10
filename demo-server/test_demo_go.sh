#!/bin/bash
## @file demo-server/test_demo_go.sh
#  @brief 自测 Go 版 demo 留言板的构建、首页、提交留言和消息 API。
#  @author BearFrps课程设计小组
#  @course 武汉大学开源软件与技术课程 2026
#  @date 2026-06-10
#  @version 1.0
#  @copyright Apache-2.0
#  @details
#   依赖关系：bash、Go 工具链、curl、临时文件。
#   修改记录：2026-06-10，补充 Doxygen 风格文件头和测试说明。
#   先把 main.go 构建成临时二进制。
#   在本机临时端口启动该二进制。
#   轮询首页并提交留言。
#   检查 /api/messages 返回内容。
#   cleanup 会停止后台进程并删除临时文件和测试二进制。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PORT=3528
BIN_FILE=$(mktemp "$SCRIPT_DIR/demo-server-go-test.XXXXXX")
LOG_FILE=$(mktemp)
INDEX_FILE=$(mktemp)
POST_FILE=$(mktemp)
MESSAGES_FILE=$(mktemp)

cleanup() {
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID"
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$BIN_FILE" "$LOG_FILE" "$INDEX_FILE" "$POST_FILE" "$MESSAGES_FILE"
}
trap cleanup EXIT

go build -o "$BIN_FILE" "$SCRIPT_DIR/main.go"
"$BIN_FILE" --port "$PORT" >"$LOG_FILE" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/" >"$INDEX_FILE"; then
    break
  fi
  sleep 0.2
done

curl -fsS "http://127.0.0.1:$PORT/" >"$INDEX_FILE"
grep -q "留言板 #$PORT" "$INDEX_FILE"

curl -fsS -X POST "http://127.0.0.1:$PORT/api/messages"   -H "Content-Type: application/json"   --data '{"nickname":"测试用户","content":"你好，Go"}' >"$POST_FILE"
grep -q '"ok"' "$POST_FILE"

curl -fsS "http://127.0.0.1:$PORT/api/messages" >"$MESSAGES_FILE"
grep -q '"nickname":"测试用户"\|"nickname": "测试用户"' "$MESSAGES_FILE"
grep -q '"content":"你好，Go"\|"content": "你好，Go"' "$MESSAGES_FILE"
grep -q '"timestamp"' "$MESSAGES_FILE"

echo "Go demo 测试通过"
