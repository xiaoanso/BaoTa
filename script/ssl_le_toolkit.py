#!/www/server/panel/pyenv/bin/python3
# -*- coding: utf-8 -*-
"""
SSL Let's Encrypt +（可选）七牛授权部署 可复用工具

典型冷启动（CDN/七牛域名，仅推七牛、可不挂站点）:
  btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap \\
    --root yianso.cn \\
    --domains pic.yianso.cn,www.pic.yianso.cn \\
    --qiniu --qiniu-action deploy_cdn_https

典型冷启动（面板站点，仅自动续签）:
  btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap \\
    --root yianso.cn \\
    --domains shitu.yianso.cn,www.shitu.yianso.cn \\
    --site shitu.yianso.cn

子命令见 --help / 各子命令 -h
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

os.chdir("/www/server/panel")
sys.path.insert(0, "/www/server/panel/class")
sys.path.insert(0, "/www/server/panel")

import public


def list_dns() -> Dict:
    from sslModel.base import sslBase
    return sslBase().get_dns_data(None) or {}


def pick_dns_id(dns_id: str = "") -> str:
    dns = list_dns()
    if not dns:
        raise RuntimeError(
            "未配置 DNS API。请到面板 SSL → DNS API 添加阿里云/DNSPod，"
            "并给 RAM 授权 alidns:AddDomainRecord 等解析权限。"
        )
    if dns_id:
        if dns_id not in dns:
            raise RuntimeError("dns_id 无效: {}".format(dns_id))
        return dns_id
    return list(dns.keys())[0]


def bind_root(root: str, dns_id: str) -> None:
    root = root.strip().lstrip("*.")
    row = public.M("ssl_domains").where("domain=?", (root,)).find()
    if row:
        if str(row.get("dns_id") or "") != str(dns_id):
            public.M("ssl_domains").where("domain=?", (root,)).update({"dns_id": dns_id})
            print("[ok] 更新 ssl_domains {} -> {}".format(root, dns_id))
        else:
            print("[ok] ssl_domains 已绑定 {} -> {}".format(root, dns_id))
    else:
        public.M("ssl_domains").add("domain,dns_id,type_id,endtime,ps", (root, dns_id, 0, 0, ""))
        print("[ok] 写入 ssl_domains {} -> {}".format(root, dns_id))


def parse_domains(s: str) -> List[str]:
    return [x.strip() for x in (s or "").replace(";", ",").split(",") if x.strip()]


def apply_le(domains: List[str], auth: str = "dns") -> dict:
    from acme_v2 import acme_v2

    if not domains:
        raise RuntimeError("domains 为空")
    p = acme_v2()
    if auth == "http":
        raise RuntimeError("请使用子命令 apply-http 并指定 --webroot")
    print("[..] 申请 LE (dns-api): {}".format(",".join(domains)))
    res = p.apply_cert(domains, auth_type="dns", auth_to="dns-api")
    ok = isinstance(res, dict) and res.get("status")
    print("[..] 结果: {} {}".format(ok, (res.get("msg") if isinstance(res, dict) else res)))
    if not ok:
        raise RuntimeError("申请失败: {}".format(res))
    return res


def apply_le_http(domains: List[str], webroot: str) -> dict:
    from acme_v2 import acme_v2

    if not os.path.isdir(webroot):
        raise RuntimeError("webroot 不存在: {}".format(webroot))
    print("[..] 申请 LE (http): {} -> {}".format(",".join(domains), webroot))
    res = acme_v2().apply_cert(domains, auth_type="http", auth_to=webroot)
    ok = isinstance(res, dict) and res.get("status")
    print("[..] 结果: {} {}".format(ok, (res.get("msg") if isinstance(res, dict) else res)))
    if not ok:
        raise RuntimeError("申请失败: {}".format(res))
    return res


def ensure_default_cert(key: str, pem: str) -> None:
    dd = "/www/server/panel/vhost/cert/0.default"
    os.makedirs(dd, exist_ok=True)
    if not os.path.isfile(dd + "/fullchain.pem"):
        public.writeFile(dd + "/fullchain.pem", pem)
        public.writeFile(dd + "/privkey.pem", key)
        print("[ok] 补齐 nginx 0.default 证书，避免 reload 失败")


def install_site(site: str, key: str, pem: str) -> None:
    import panelSite

    ensure_default_cert(key, pem)
    get = public.dict_obj()
    get.siteName = site
    get.key = key
    get.csr = pem
    r = panelSite.panelSite().SetSSL(get)
    print("[..] SetSSL {}: {}".format(site, r))
    if isinstance(r, dict) and not r.get("status"):
        # 常见：nginx 测试失败但文件已写；再尝试 reload
        public.ExecShell("/etc/init.d/nginx reload")
        raise RuntimeError("挂站点失败: {}".format(r.get("msg")))
    public.ExecShell("/etc/init.d/nginx reload")
    print("[ok] 已部署到站点 {}".format(site))


def cert_files_from_apply(res: dict, primary: str):
    save = res.get("save_path") or ("vhost/letsencrypt/" + primary)
    if not save.startswith("/"):
        save = os.path.join(public.get_panel_path(), save)
    key = public.readFile(save + "/privkey.pem") or res.get("private_key")
    pem = public.readFile(save + "/fullchain.pem")
    if not pem:
        pem = (res.get("cert") or "") + (res.get("root") or "")
        if key and pem:
            os.makedirs(save, exist_ok=True)
            public.writeFile(save + "/privkey.pem", key)
            public.writeFile(save + "/fullchain.pem", pem)
    if not key or not pem:
        raise RuntimeError("未找到证书文件: {}".format(save))
    if isinstance(key, bytes):
        key = key.decode()
    if isinstance(pem, bytes):
        pem = pem.decode()
    return save, key, pem


def find_ssl_hash(domain: str, prefer_le: bool = True) -> str:
    path = "/www/server/panel/vhost/ssl_saved"
    candidates = []
    for h in os.listdir(path) if os.path.isdir(path) else []:
        pem_path = os.path.join(path, h, "fullchain.pem")
        if not os.path.isfile(pem_path):
            continue
        data = public.readFile(pem_path) or ""
        if domain not in data:
            continue
        is_le = any(x in data for x in ("Let's Encrypt", "ISRG Root", "YR1", "YR2", "R3", "R10", "R11"))
        candidates.append((1 if (prefer_le and is_le) else 0, os.path.getmtime(pem_path), h))
    candidates.sort(reverse=True)
    return candidates[0][2] if candidates else ""


def qiniu_ensure_target(domain: str, action: str = "deploy_cdn_https", ssl_hash: str = "", auto_deploy: bool = True) -> int:
    from mod.project.ssl.deployMod import main as deploy_main

    m = deploy_main()
    params = json.dumps(
        {
            "domain": domain,
            "force_https": "false",
            "http2_enable": "true",
            "cleanup": "false",
            "old_cert_id": "",
        },
        ensure_ascii=False,
    )
    rows = m.M("deploy_targets").where("type=?", ("qiniu",)).select() or []
    for r in rows:
        try:
            p = json.loads(r.get("params") or "{}")
        except Exception:
            p = {}
        if (p.get("domain") or "") == domain or r.get("name") == "七牛 {}".format(domain):
            m.M("deploy_targets").where("id=?", (r["id"],)).update(
                {
                    "name": "七牛 {}".format(domain),
                    "action": action,
                    "params": params,
                    "auto_deploy": 1 if auto_deploy else 0,
                    "ssl_hash": ssl_hash or r.get("ssl_hash") or "",
                    "update_time": public.format_date(),
                }
            )
            print("[ok] 更新七牛目标 id={} domain={} auto_deploy={}".format(r["id"], domain, auto_deploy))
            return int(r["id"])

    auths = m.M("deploy_auths").where("type=?", ("qiniu",)).select() or []
    if not auths:
        raise RuntimeError("请先在面板「SSL → 部署授权」添加类型=七牛云 的授权（AK/SK）")
    tid = m.M("deploy_targets").insert(
        {
            "auth_id": auths[0]["id"],
            "name": "七牛 {}".format(domain),
            "action": action,
            "params": params,
            "type": "qiniu",
            "ssl_hash": ssl_hash or "",
            "auto_deploy": 1 if auto_deploy else 0,
            "create_time": public.format_date(),
            "update_time": public.format_date(),
        }
    )
    print("[ok] 新建七牛目标 id={} domain={}".format(tid, domain))
    return int(tid)


def qiniu_deploy(domain: str, ssl_hash: str = "") -> None:
    from mod.project.ssl.deployMod import main as deploy_main

    m = deploy_main()
    ssl_hash = ssl_hash or find_ssl_hash(domain)
    if not ssl_hash:
        raise RuntimeError("未找到域名 {} 的本地证书 hash".format(domain))
    tid = qiniu_ensure_target(domain, ssl_hash=ssl_hash, auto_deploy=True)
    ok, resp = m.execute_target_by_id(tid, ssl_hash=ssl_hash, max_retry=3, retry_interval=5)
    print("[..] 七牛部署 ok={} resp={}".format(ok, resp))
    if not ok:
        raise RuntimeError("七牛部署失败")


def cmd_list_dns(_args):
    dns = list_dns()
    print("DNS API 数量: {}".format(len(dns)))
    for k, v in dns.items():
        print("  id={} type={} name={} ps={}".format(k, v.get("dns_type"), v.get("dns_name"), v.get("ps")))


def cmd_status(args):
    domain = (args.domain or "").strip()
    print("=== DNS API ===")
    cmd_list_dns(args)
    print("=== ssl_domains ===")
    try:
        rows = public.M("ssl_domains").field("domain,dns_id,ps").select() or []
        for r in rows:
            print("  {} -> {}".format(r.get("domain"), r.get("dns_id")))
    except Exception as e:
        print("  (read fail: {})".format(e))
    print("=== deploy_targets(qiniu) ===")
    try:
        from mod.project.ssl.deployMod import main as deploy_main
        rows = deploy_main().M("deploy_targets").where("type=?", ("qiniu",)).select() or []
        for r in rows:
            print("  id={} name={} action={} auto_deploy={} ssl_hash={} params={}".format(
                r.get("id"), r.get("name"), r.get("action"), r.get("auto_deploy"), r.get("ssl_hash"), r.get("params")))
    except Exception as e:
        print("  (read fail: {})".format(e))
    if domain:
        h = find_ssl_hash(domain)
        print("=== cert for {} ssl_hash={} ===".format(domain, h or "(none)"))
        for base in (
            "/www/server/panel/vhost/cert/{}".format(domain),
            "/www/server/panel/vhost/letsencrypt/{}".format(domain),
            "/www/server/panel/vhost/ssl_saved/{}".format(h) if h else "",
        ):
            if not base:
                continue
            pem = os.path.join(base, "fullchain.pem")
            if os.path.isfile(pem):
                print("  file", pem)
                public.ExecShell("openssl x509 -in {} -noout -issuer -subject -enddate".format(pem))


def cmd_bootstrap(args):
    domains = parse_domains(args.domains)
    if not domains:
        raise RuntimeError("--domains 必填")
    primary = domains[0]
    root = (args.root or "").strip()
    if not root:
        # 粗略取根：去掉一级子域
        parts = primary.split(".")
        root = ".".join(parts[-2:]) if len(parts) >= 2 else primary

    dns_id = pick_dns_id(args.dns_id or "")
    bind_root(root, dns_id)

    if args.http and args.webroot:
        res = apply_le_http(domains, args.webroot)
    else:
        res = apply_le(domains, auth="dns")

    save, key, pem = cert_files_from_apply(res, primary)
    ssl_hash = find_ssl_hash(primary) or ""
    print("[ok] 证书目录 {} ssl_hash={}".format(save, ssl_hash))

    if args.site:
        install_site(args.site, key, pem)
        ssl_hash = find_ssl_hash(primary) or ssl_hash

    if args.qiniu:
        qiniu_ensure_target(
            primary,
            action=args.qiniu_action or "deploy_cdn_https",
            ssl_hash=ssl_hash,
            auto_deploy=not args.no_auto_deploy,
        )
        if not args.skip_deploy:
            qiniu_deploy(primary, ssl_hash=ssl_hash)

    print("[done] bootstrap {}".format(primary))


def cmd_apply(args):
    domains = parse_domains(args.domains)
    dns_id = pick_dns_id(args.dns_id or "")
    if args.root:
        bind_root(args.root, dns_id)
    if args.http:
        res = apply_le_http(domains, args.webroot)
    else:
        res = apply_le(domains)
    primary = domains[0]
    save, key, pem = cert_files_from_apply(res, primary)
    if args.site:
        install_site(args.site, key, pem)
    print("[done] apply", save)


def cmd_qiniu_ensure(args):
    h = args.ssl_hash or find_ssl_hash(args.domain)
    qiniu_ensure_target(args.domain, action=args.action or "deploy_cdn_https", ssl_hash=h, auto_deploy=not args.no_auto_deploy)


def cmd_qiniu_deploy(args):
    qiniu_deploy(args.domain, ssl_hash=args.ssl_hash or "")


def build_parser():
    ap = argparse.ArgumentParser(description="SSL LE + 七牛授权部署工具包")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-dns", help="列出面板 DNS API")
    p.set_defaults(func=cmd_list_dns)

    p = sub.add_parser("status", help="查看 DNS/目标/证书状态")
    p.add_argument("--domain", default="")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("bootstrap", help="冷启动：绑根域+申请LE+可选挂站/推七牛")
    p.add_argument("--root", default="", help="根域名，如 yianso.cn")
    p.add_argument("--domains", required=True, help="证书域名，逗号分隔，首个为主域名")
    p.add_argument("--dns_id", default="")
    p.add_argument("--site", default="", help="挂到面板站点名（与主域名常相同）")
    p.add_argument("--qiniu", action="store_true", help="创建/更新七牛部署目标并推送")
    p.add_argument("--qiniu-action", default="deploy_cdn_https", choices=["deploy_cdn_https", "deploy_oss_domain_https", "replace_and_cleanup"])
    p.add_argument("--no-auto-deploy", action="store_true")
    p.add_argument("--skip-deploy", action="store_true", help="只建目标不立即推送")
    p.add_argument("--http", action="store_true", help="用 HTTP 验证（需 80 对公网开放）")
    p.add_argument("--webroot", default="")
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser("apply", help="仅申请 LE（可选挂站）")
    p.add_argument("--root", default="")
    p.add_argument("--domains", required=True)
    p.add_argument("--dns_id", default="")
    p.add_argument("--site", default="")
    p.add_argument("--http", action="store_true")
    p.add_argument("--webroot", default="")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("qiniu-ensure", help="确保七牛部署目标存在")
    p.add_argument("--domain", required=True)
    p.add_argument("--action", default="deploy_cdn_https")
    p.add_argument("--ssl_hash", default="")
    p.add_argument("--no-auto-deploy", action="store_true")
    p.set_defaults(func=cmd_qiniu_ensure)

    p = sub.add_parser("qiniu-deploy", help="立即把证书推到七牛")
    p.add_argument("--domain", required=True)
    p.add_argument("--ssl_hash", default="")
    p.set_defaults(func=cmd_qiniu_deploy)

    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print("[error]", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
