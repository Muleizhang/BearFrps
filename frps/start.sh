#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
VERSION="${FRPS_VERSION:-v0.58.1}"
VERSION_NOV="${VERSION#v}"
OS="$(uname | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ARCH=amd64;;
  aarch64|arm64) ARCH=arm64;;
  *) echo "Unsupported architecture: $ARCH"; exit 1;;
esac

if [ ! -x ./frps ]; then
  URL="https://github.com/fatedier/frp/releases/download/${VERSION}/frp_${VERSION_NOV}_${OS}_${ARCH}.tar.gz"
  echo "Downloading frps from $URL"
  curl -L -o frp.tar.gz "$URL"
  tar xzf frp.tar.gz --strip-components=1 --wildcards "*/frps"
  chmod +x frps
  rm -f frp.tar.gz
fi

exec ./frps -c frps.toml
