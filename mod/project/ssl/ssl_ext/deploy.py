# -*- coding: utf-8 -*-
"""导入官方 deployMod.main，续签后按 auto_deploy 目标推送。"""
from __future__ import annotations

import json
import time

from .util import domain_matched


def _official():
    from mod.project.ssl.deployMod import main
    return main()


def _notify_deploy(title: str, lines: list, success: bool = True):
    import public

    try:
        slist = [">结果：{}".format("成功" if success else "失败")] + [">" + str(x) for x in lines]
        msg = public.get_push_info(title, slist)
        for module in ("mail", "dingding", "weixin", "feishu", "wx_account"):
            try:
                public.push_msg(module, msg)
            except Exception:
                pass
        public.WriteLog("SSL授权部署", "{} | {}".format(title, "；".join(str(x) for x in lines)))
    except Exception as e:
        public.WriteLog("SSL授权部署", "通知发送失败: {} | {}".format(e, title))


def execute_target_by_id(target_id, ssl_hash=None, oid=None, cert=None, key=None, max_retry=3, retry_interval=10):
    import public

    m = _official()
    get = public.dict_obj()
    get.target_id = target_id
    if ssl_hash:
        get.ssl_hash = ssl_hash
    if oid:
        get.oid = oid
    if cert and key:
        get.cert = cert
        get.key = key
    last = None
    for i in range(max(1, int(max_retry))):
        last = m.execute_action(get)
        ok = False
        if isinstance(last, dict):
            if last.get("status") in ("success", True, 1, "1"):
                ok = True
            if last.get("status") == "error" or last.get("status") is False:
                ok = False
        if ok:
            return True, last
        if i + 1 < max_retry:
            time.sleep(retry_interval)
    return False, last


def extra_renew_hashes():
    """官方 renew_cert_v2 在站点证书之外，追加 auto_deploy 绑定的 hash。"""
    try:
        ensure = __import__("mod.project.ssl.ssl_ext.schema", fromlist=["ensure_target_columns"])
        ensure.ensure_target_columns()
    except Exception:
        pass
    added = []
    try:
        rows = _official().M("deploy_targets").where("auto_deploy=?", (1,)).select() or []
    except Exception:
        return added
    for r in rows:
        h = (r.get("ssl_hash") or "").strip()
        if h:
            added.append((h, r.get("name") or ""))
    return added


def auto_deploy_on_cert_change(new_ssl_hash, domains=None, old_ssl_hash=None, oid=None, notify_success=True):
    from .schema import ensure_target_columns

    ensure_target_columns()
    domains = domains or []
    if isinstance(domains, str):
        domains = [d.strip() for d in domains.split(",") if d.strip()]

    m = _official()
    if old_ssl_hash and new_ssl_hash and old_ssl_hash != new_ssl_hash:
        try:
            m.M("deploy_targets").where("ssl_hash=?", (old_ssl_hash,)).update(
                {"ssl_hash": new_ssl_hash, "update_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
            )
        except Exception:
            pass

    try:
        rows = m.M("deploy_targets").where("auto_deploy=?", (1,)).select()
    except Exception:
        rows = []
    if not rows:
        return {"status": True, "msg": "无自动部署目标", "deployed": []}

    results = []
    for t in rows:
        try:
            params = json.loads(t.get("params") or "{}")
        except Exception:
            params = {}
        target_domain = (params.get("domain") or "").strip()
        bound = (t.get("ssl_hash") or "") == (new_ssl_hash or "")
        by_domain = domain_matched(domains, target_domain) if target_domain else False
        if not bound and not by_domain:
            continue
        if by_domain and new_ssl_hash and (t.get("ssl_hash") or "") != new_ssl_hash:
            try:
                m.M("deploy_targets").where("id=?", (t["id"],)).update(
                    {"ssl_hash": new_ssl_hash, "update_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
                )
            except Exception:
                pass

        ok, resp = execute_target_by_id(t["id"], ssl_hash=new_ssl_hash, oid=oid, max_retry=3, retry_interval=10)
        msg = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or resp.get("msg") or ""
        results.append({"target_id": t["id"], "name": t.get("name"), "domain": target_domain, "ok": ok, "msg": msg})
        if ok and notify_success:
            _notify_deploy(
                "SSL授权部署成功",
                ["目标：{}".format(t.get("name")), "域名：{}".format(target_domain), "ssl_hash：{}".format(new_ssl_hash)],
                True,
            )
        if not ok:
            _notify_deploy(
                "SSL授权部署失败（证书已续签）",
                [
                    "目标：{}".format(t.get("name")),
                    "域名：{}".format(target_domain),
                    "ssl_hash：{}".format(new_ssl_hash),
                    "原因：{}".format(msg or resp),
                ],
                False,
            )
    return {"status": True, "msg": "完成", "deployed": results}
