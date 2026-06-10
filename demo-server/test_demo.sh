#!/bin/bash
## @file demo-server/test_demo.sh
#  @brief 自测 Python 版 demo 留言板的首页、提交留言和消息 API。
#  @author BearFrps课程设计小组
#  @course 武汉大学开源软件与技术课程 2026
#  @date 2026-06-10
#  @version 1.0
#  @copyright Apache-2.0
#  @details
#   依赖关系：bash、python3、curl、临时文件。
#   修改记录：2026-06-10，补充 Doxygen 风格文件头和测试说明。
#   在本机临时端口启动 demo_server.py。
#   轮询首页直到服务可访问。
#   向 /api/messages 提交一条留言。
#   再读取消息列表，确认服务端保存了内容。
#   cleanup 会停止后台进程并删除临时文件。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PORT=3527
LOG_FILE=$(mktemp)
INDEX_FILE=$(mktemp)
POST_FILE=$(mktemp)
MESSAGES_FILE=$(mktemp)

cleanup() {
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID"
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$LOG_FILE" "$INDEX_FILE" "$POST_FILE" "$MESSAGES_FILE"
}
trap cleanup EXIT

python3 "$SCRIPT_DIR/demo_server.py" --port "$PORT" >"$LOG_FILE" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/" >"$INDEX_FILE"; then
    break
  fi
  sleep 0.2
done

curl -fsS "http://127.0.0.1:$PORT/" >"$INDEX_FILE"
grep -q "留言板 #$PORT" "$INDEX_FILE"

curl -fsS -X POST "http://127.0.0.1:$PORT/api/messages"   -H "Content-Type: application/json"   --data '{"nickname":"测试用户","content":"你好，Python"}' >"$POST_FILE"
grep -q '"ok"' "$POST_FILE"

curl -fsS "http://127.0.0.1:$PORT/api/messages" >"$MESSAGES_FILE"
grep -q '"nickname": "测试用户"' "$MESSAGES_FILE"
grep -q '"content": "你好，Python"' "$MESSAGES_FILE"
grep -q '"timestamp"' "$MESSAGES_FILE"

echo "Python demo 测试通过"
