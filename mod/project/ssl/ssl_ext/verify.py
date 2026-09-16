#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并官方更新后的隔离完整性检查（无面板依赖）。"""
from __future__ import annotations

import ast
import os
import re
import sys

BEGIN = re.compile(r"^[ \t]*# >>> BT_EXT:([A-Za-z0-9_]+)\s*$")
END = re.compile(r"^[ \t]*# <<< BT_EXT:([A-Za-z0-9_]+)\s*$")

REQUIRED = {
    "class/acme_v2.py": ["ssl_csr", "ssl_deploy", "ssl_renew_hashes"],
    "mod/project/ssl/deployMod.py": ["ssl_schema", "ssl_target_fields"],
    "script/renew_certificate.py": ["ssl_commercial"],
}

FORBIDDEN_OUTSIDE = (
    "auto_deploy_on_cert_change",
    "execute_target_by_id",
    "_ensure_target_columns",
    "after_save_cert",
    "after_commercial_redeploy",
)

FORBIDDEN_INSTALL = (
    "acme_v2.py",
    "deployMod.py",
    "renew_certificate.py",
)


def repo_root() -> str:
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    return here


def parse_markers(text: str):
    stack = []
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        m = BEGIN.match(line)
        if m:
            stack.append((m.group(1), i))
            continue
        m = END.match(line)
        if m:
            if not stack:
                raise ValueError("line {}: closing marker without open: {}".format(i, m.group(1)))
            name, start = stack.pop()
            if name != m.group(1):
                raise ValueError("line {}: expected close {}, got {}".format(i, name, m.group(1)))
            found.append((name, start, i))
    if stack:
        raise ValueError("unclosed marker: {}".format(stack[-1]))
    return found


def outside_spans(text: str, blocks):
    lines = text.splitlines()
    blocked = set()
    for _, a, b in blocks:
        for n in range(a, b + 1):
            blocked.add(n)
    out = []
    for i, line in enumerate(lines, 1):
        if i not in blocked:
            out.append((i, line))
    return out


def check_file(root: str, rel: str, required_ids):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        raise FileNotFoundError(rel)
    text = open(path, encoding="utf-8").read()
    blocks = parse_markers(text)
    names = {n for n, _, _ in blocks}
    missing = [x for x in required_ids if x not in names]
    if missing:
        raise SystemExit("{} missing BT_EXT markers: {}".format(rel, missing))
    for i, line in outside_spans(text, blocks):
        for bad in FORBIDDEN_OUTSIDE:
            if bad in line:
                raise SystemExit("{}:{} business '{}' leaked outside BT_EXT".format(rel, i, bad))
    return blocks


def check_install_script(root: str):
    path = os.path.join(root, "mod/project/ssl/deploy_plugins/qiniu/install_to_host.sh")
    text = open(path, encoding="utf-8").read()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if not s.startswith("scp"):
            continue
        for name in FORBIDDEN_INSTALL:
            if name in s:
                raise SystemExit("install_to_host.sh must not scp official file {}".format(name))


def compile_isolated(root: str):
    files = [
        "mod/project/ssl/ssl_ext/util.py",
        "mod/project/ssl/ssl_ext/verify.py",
        "script/ssl_le_toolkit.py",
        "mod/project/ssl/deploy_plugins/qiniu/qiniu",
    ]
    for rel in files:
        src = open(os.path.join(root, rel), encoding="utf-8").read()
        ast.parse(src, filename=rel)


def self_test_util():
    sys.path.insert(0, os.path.join(repo_root(), "mod/project/ssl"))
    from ssl_ext.util import attach_target_fields, domain_matched

    assert domain_matched(["pic.yianso.cn", "www.pic.yianso.cn"], "pic.yianso.cn")
    assert domain_matched(["*.yianso.cn"], "pic.yianso.cn")
    assert not domain_matched(["mcp.yianso.cn"], "pic.yianso.cn")

    class G:
        ssl_hash = "abc"
        auto_deploy = "1"

    data = {"name": "t"}
    attach_target_fields(G(), data)
    assert data["ssl_hash"] == "abc" and data["auto_deploy"] == 1


def main():
    root = repo_root()
    os.chdir(root)
    for rel, ids in REQUIRED.items():
        blocks = check_file(root, rel, ids)
        print("[ok] {} markers={}".format(rel, sorted({n for n, _, _ in blocks})))
    check_install_script(root)
    print("[ok] install_to_host.sh does not overwrite official files")
    compile_isolated(root)
    print("[ok] isolated sources parse")
    self_test_util()
    print("[ok] ssl_ext.util self-test")
    print("verify_ssl_ext: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[error]", e)
        sys.exit(1)
