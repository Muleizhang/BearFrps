#!/usr/bin/env bash
## @file tools/generate_doxygen.sh
## @brief Generate optional Doxygen HTML documentation for BearFrps.
## @author BearFrps课程设计小组
## @course 武汉大学开源软件与技术课程 2026
## @date 2026-06-20
## @version 1.0
## @copyright Apache-2.0
## @details
##   依赖关系：bash、doxygen、graphviz dot。
##   本脚本只生成 docs/doxygen/html，不修改源码或运行服务。
##   生成目录已加入 .gitignore，不作为课程源码提交内容。
##   若本机未安装 doxygen 或 dot，脚本返回 127 并提示安装依赖。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v doxygen >/dev/null 2>&1; then
  echo "doxygen is not installed. Install Doxygen, then rerun this script." >&2
  exit 127
fi

if ! command -v dot >/dev/null 2>&1; then
  echo "Graphviz dot is not installed. Install Graphviz, then rerun this script." >&2
  exit 127
fi

cd "$ROOT_DIR"
doxygen Doxyfile
echo "Generated docs/doxygen/html/index.html"
