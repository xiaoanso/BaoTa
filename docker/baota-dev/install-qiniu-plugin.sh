#!/bin/bash
# 把二次开发七牛插件落到官方扫描目录（与 ECS /www/server/deploy_plugin 一致）
set -euo pipefail
SRC="${1:-/www/server/panel/mod/project/ssl/deploy_plugins/qiniu/qiniu}"
DST="${2:-/www/server/deploy_plugin/qiniu}"
mkdir -p "$(dirname "$DST")"
cp -f "$SRC" "$DST"
chmod 755 "$DST"
echo "installed $DST"
printf '%s\n' '{"action":"get_metadata","params":{}}' | "$DST"
