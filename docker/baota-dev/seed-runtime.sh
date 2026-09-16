#!/bin/bash
# 从官方镜像拷出运行时（pyenv + 面板 data + 初始密码），供本地源码挂载后使用。
set -euo pipefail
if [ ! -x /out/pyenv/bin/python3 ]; then
  echo "seeding pyenv from official image"
  mkdir -p /out/pyenv
  cp -a /www/server/panel/pyenv/. /out/pyenv/
fi
if [ ! -f /out/data/port.pl ]; then
  echo "seeding panel data from official image"
  mkdir -p /out/data
  cp -a /www/server/panel/data/. /out/data/
fi
if [ -f /www/server/panel/default.pl ] && [ ! -f /out/data/_image_default.pl ]; then
  cp -a /www/server/panel/default.pl /out/data/_image_default.pl
fi
echo "seed ok"
ls -ld /out/pyenv/bin/python3 /out/data/port.pl
