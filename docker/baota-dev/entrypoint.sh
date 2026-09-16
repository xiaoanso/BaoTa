#!/bin/bash
# 以本仓库为面板源码启动：保留镜像 pyenv/data，落地七牛插件，再交给官方 /bt.sh。
set -euo pipefail
PANEL=/www/server/panel
chmod +x "$PANEL/BT-Panel" "$PANEL/BT-Task" "$PANEL/init.sh" "$PANEL/tools.py" 2>/dev/null || true
if [ ! -s "$PANEL/default.pl" ] && [ -f "$PANEL/data/_image_default.pl" ]; then
  cp -a "$PANEL/data/_image_default.pl" "$PANEL/default.pl"
fi
# 镜像 default.pl 与 users 表经常不一致，启动时按 default.pl 重写库密码
if [ -s "$PANEL/default.pl" ]; then
  (cd "$PANEL" && "$PANEL/pyenv/bin/python3" - <<'PY'
import os, sys
os.chdir("/www/server/panel")
sys.path.insert(0, "class/")
import public
pwd = public.readFile("/www/server/panel/default.pl").strip()
row = public.M("users").where("id=?", (1,)).field("id,username,salt").find()
if not row or isinstance(row, str):
    raise SystemExit("users row missing: {}".format(row))
if not row.get("salt"):
    public.M("users").where("id=?", (1,)).setField("salt", public.GetRandomString(12))
hashed = public.password_salt(public.md5(pwd), uid=1)
public.M("users").where("id=?", (1,)).setField("password", hashed)
print("synced panel password for", row.get("username"))
PY
  )
fi
mkdir -p /www/server/deploy_plugin
PLUGIN_SRC="$PANEL/mod/project/ssl/deploy_plugins/qiniu/qiniu"
PLUGIN_DST=/www/server/deploy_plugin/qiniu
if [ -f "$PLUGIN_SRC" ] && [ ! -e "$PLUGIN_DST" ]; then
  cp -f "$PLUGIN_SRC" "$PLUGIN_DST"
fi
if [ -e "$PLUGIN_DST" ]; then
  chmod 755 "$PLUGIN_DST" || true
fi
exec /bt.sh
