#!/bin/bash
# 将七牛授权部署插件与面板补丁同步到宝塔中国版机器
set -e
HOST="${1:-yianso-ecs}"
PANEL_ROOT="${2:-/www/server/panel}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# .../mod/project/ssl/deploy_plugins/qiniu -> repo root = 5 levels up
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

echo "REPO_ROOT=$REPO_ROOT"
test -f "$REPO_ROOT/mod/project/ssl/deployMod.py"
test -f "$REPO_ROOT/script/ssl_le_toolkit.py"

echo "==> sync panel hooks to ${HOST}:${PANEL_ROOT}"
scp -q "$REPO_ROOT/mod/project/ssl/deployMod.py" "${HOST}:${PANEL_ROOT}/mod/project/ssl/deployMod.py"
scp -q "$REPO_ROOT/class/acme_v2.py" "${HOST}:${PANEL_ROOT}/class/acme_v2.py"
scp -q "$REPO_ROOT/script/renew_certificate.py" "${HOST}:${PANEL_ROOT}/script/renew_certificate.py"
scp -q "$REPO_ROOT/script/ssl_le_toolkit.py" "${HOST}:${PANEL_ROOT}/script/ssl_le_toolkit.py"
scp -q "$REPO_ROOT/script/qiniu_le_pic_setup.py" "${HOST}:${PANEL_ROOT}/script/qiniu_le_pic_setup.py"
ssh "$HOST" "mkdir -p ${PANEL_ROOT}/mod/project/ssl/deploy_plugins/qiniu /www/server/deploy_plugin"
scp -q "$REPO_ROOT/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md" "${HOST}:${PANEL_ROOT}/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md"

echo "==> install qiniu deploy_plugin"
scp -q "$SCRIPT_DIR/qiniu" "${HOST}:/www/server/deploy_plugin/qiniu"
ssh "$HOST" "chmod 755 /www/server/deploy_plugin/qiniu ${PANEL_ROOT}/script/ssl_le_toolkit.py ${PANEL_ROOT}/script/qiniu_le_pic_setup.py"

echo "==> verify metadata"
ssh "$HOST" '/www/server/deploy_plugin/qiniu <<EOF
{"action":"get_metadata","params":{}}
EOF'

echo "==> toolkit help"
ssh "$HOST" "btpython ${PANEL_ROOT}/script/ssl_le_toolkit.py -h | head -25"

echo "==> done."
echo "文档: ${PANEL_ROOT}/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md"
echo "冷启动示例见 RUNBOOK §4"
