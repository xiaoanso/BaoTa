#!/bin/bash
# 只同步隔离包 + 七牛插件，禁止覆盖官方三件套。
# 官方文件钩子请走 git 合并；本脚本不会 scp acme_v2.py / deployMod.py / renew_certificate.py
set -e
HOST="${1:-}"
PANEL_ROOT="${2:-/www/server/panel}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

echo "REPO_ROOT=$REPO_ROOT"
test -f "$REPO_ROOT/mod/project/ssl/ssl_ext/hooks.py"
test -f "$REPO_ROOT/script/ssl_le_toolkit.py"

if [ -z "$HOST" ]; then
  echo "usage: $0 <ssh-host> [panel_root]"
  echo "本脚本只拷隔离包，不会覆盖官方文件。"
  exit 1
fi

echo "==> sync isolated package only (no official overwrite)"
ssh "$HOST" "mkdir -p ${PANEL_ROOT}/mod/project/ssl/ssl_ext ${PANEL_ROOT}/mod/project/ssl/deploy_plugins/qiniu ${PANEL_ROOT}/script /www/server/deploy_plugin"
scp -q "$REPO_ROOT/mod/project/ssl/ssl_ext/"*.py "${HOST}:${PANEL_ROOT}/mod/project/ssl/ssl_ext/"
scp -q "$REPO_ROOT/script/ssl_le_toolkit.py" "${HOST}:${PANEL_ROOT}/script/ssl_le_toolkit.py"
scp -q "$REPO_ROOT/script/qiniu_le_pic_setup.py" "${HOST}:${PANEL_ROOT}/script/qiniu_le_pic_setup.py"
scp -q "$REPO_ROOT/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md" "${HOST}:${PANEL_ROOT}/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md"
scp -q "$SCRIPT_DIR/qiniu" "${HOST}:/www/server/deploy_plugin/qiniu"
ssh "$HOST" "chmod 755 /www/server/deploy_plugin/qiniu ${PANEL_ROOT}/script/ssl_le_toolkit.py ${PANEL_ROOT}/script/qiniu_le_pic_setup.py"

echo "==> verify qiniu metadata"
ssh "$HOST" '/www/server/deploy_plugin/qiniu <<EOF
{"action":"get_metadata","params":{}}
EOF'

echo "==> done (official files untouched)"
echo "文档: ${PANEL_ROOT}/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md"
