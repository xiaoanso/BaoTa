#!/www/server/panel/pyenv/bin/python3
# -*- coding: utf-8 -*-
"""兼容入口：转发到 ssl_le_toolkit（默认操作 pic.yianso.cn）。

新域名请直接使用:
  btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap --help
文档:
  mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md
"""
from __future__ import annotations

import argparse
import os
import sys

os.chdir("/www/server/panel")
sys.path.insert(0, "/www/server/panel/class")
sys.path.insert(0, "/www/server/panel")
sys.path.insert(0, "/www/server/panel/script")

# 以子进程方式调用，避免重复维护
import subprocess

PANEL_PY = "/www/server/panel/pyenv/bin/python3"
TOOL = "/www/server/panel/script/ssl_le_toolkit.py"
DEFAULT_DOMAIN = "pic.yianso.cn"
DEFAULT_ROOT = "yianso.cn"


def main():
    ap = argparse.ArgumentParser(description="兼容旧 qiniu_le_pic_setup；请优先用 ssl_le_toolkit")
    ap.add_argument("--dns_id", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--list-dns", action="store_true")
    args = ap.parse_args()

    if args.list_dns:
        cmd = [PANEL_PY, TOOL, "list-dns"]
        raise SystemExit(subprocess.call(cmd))

    if args.apply or args.deploy:
        if args.apply and args.deploy:
            cmd = [
                PANEL_PY, TOOL, "bootstrap",
                "--root", DEFAULT_ROOT,
                "--domains", "{},www.{}".format(DEFAULT_DOMAIN, DEFAULT_DOMAIN),
                "--qiniu",
            ]
            if args.dns_id:
                cmd += ["--dns_id", args.dns_id]
        elif args.apply:
            cmd = [
                PANEL_PY, TOOL, "apply",
                "--root", DEFAULT_ROOT,
                "--domains", "{},www.{}".format(DEFAULT_DOMAIN, DEFAULT_DOMAIN),
            ]
            if args.dns_id:
                cmd += ["--dns_id", args.dns_id]
        else:
            cmd = [PANEL_PY, TOOL, "qiniu-deploy", "--domain", DEFAULT_DOMAIN]
        raise SystemExit(subprocess.call(cmd))

    # 默认：确保目标
    cmd = [PANEL_PY, TOOL, "qiniu-ensure", "--domain", DEFAULT_DOMAIN]
    if args.dns_id:
        # ensure 不需要 dns_id；打印提示
        pass
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
