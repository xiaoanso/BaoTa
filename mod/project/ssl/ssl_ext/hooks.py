# -*- coding: utf-8 -*-
"""官方文件只调用这里。业务通过 import 官方类再调用。"""
from __future__ import annotations

from .util import attach_target_fields as _attach_target_fields


def ensure_schema():
    from .schema import ensure_target_columns
    try:
        ensure_target_columns()
    except Exception as e:
        try:
            import public
            public.print_log("deploy_targets 字段迁移失败: {}".format(e))
        except Exception:
            pass


def attach_target_fields(get, data: dict) -> dict:
    return _attach_target_fields(get, data)


def build_csr(acme_obj, index):
    """官方 send_csr：优先官方 create_csr，X509Req 缺失时走官方 create_csr_new。"""
    try:
        return acme_obj.create_csr(index)
    except Exception as e:
        import OpenSSL
        if "X509Req" in str(e) or not hasattr(OpenSSL.crypto, "X509Req"):
            return acme_obj.create_csr_new(index)
        raise


def after_save_cert(acme_obj, cert, index, domain_name):
    try:
        _after_save_cert(acme_obj, cert, index, domain_name)
    except Exception as e:
        try:
            from acme_v2 import write_log
            write_log("|-授权部署自动推送跳过/失败: {}".format(e))
        except Exception:
            pass


def _after_save_cert(acme_obj, cert, index, domain_name):
    from hashlib import md5

    new_hash = md5((cert["cert"] + cert["root"]).encode("utf-8")).hexdigest()
    old_hash = None
    try:
        import json
        import public
        path_ex = "{}/data/exclude_hash.json".format(public.get_panel_path())
        ex = json.loads(public.readFile(path_ex) or "{}")
        stored = (ex.get("exclude_hash_let") or {}).get(index)
        if stored and stored != new_hash:
            old_hash = stored
    except Exception:
        pass
    domains = []
    try:
        domains = acme_obj._config.get("orders", {}).get(index, {}).get("domains") or [domain_name]
    except Exception:
        domains = [domain_name]
    from .deploy import auto_deploy_on_cert_change
    auto_deploy_on_cert_change(new_ssl_hash=new_hash, domains=domains, old_ssl_hash=old_hash)


def extra_renew_hashes(hash_list):
    from .deploy import extra_renew_hashes as _extra
    out = list(hash_list)
    for h, name in _extra():
        if h not in out:
            out.append(h)
            try:
                from acme_v2 import write_log
                write_log("|-追加授权部署自动续签证书: {} ({})".format(h, name))
            except Exception:
                pass
    return out


def after_commercial_redeploy(renew_obj, cert):
    domains = []
    if cert.get("domainName"):
        domains = [x.strip() for x in str(cert["domainName"]).replace(";", ",").split(",") if x.strip()]
    ssl_hash = ""
    try:
        import public
        from hashlib import md5
        get = public.dict_obj()
        get.oid = cert["oid"]
        rep = renew_obj.panelssl.get_order_find(get)
        full = (rep.get("certificate") or "") + "\n" + (rep.get("caCertificate") or "")
        ssl_hash = md5(full.encode("utf-8")).hexdigest()
    except Exception as e:
        print("**计算商业证书 hash 失败: {}".format(e))
    from .deploy import auto_deploy_on_cert_change
    res = auto_deploy_on_cert_change(new_ssl_hash=ssl_hash or "", domains=domains, oid=cert.get("oid"))
    print("**授权部署自动推送结果: {}".format(res))
