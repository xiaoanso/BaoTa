# -*- coding: utf-8 -*-
"""无面板依赖的纯函数，供 CI 与 hooks 共用。"""


def domain_matched(cert_domains, target_domain: str) -> bool:
    if not target_domain or not cert_domains:
        return False
    td = target_domain.strip().lower().lstrip("*.")
    want = target_domain.strip().lower()
    for d in cert_domains:
        if not d:
            continue
        dd = str(d).strip().lower()
        if dd == want:
            return True
        if dd.startswith("*.") and (td == dd[2:] or td.endswith("." + dd[2:])):
            return True
        if td == dd.lstrip("*."):
            return True
    return False


def parse_auto_deploy_flag(value) -> int:
    return 1 if str(value or 0) in ("1", "true", "True") else 0


def attach_target_fields(get, data: dict) -> dict:
    """往官方 deploy_targets 写入前，附加隔离字段。"""
    if hasattr(get, "ssl_hash"):
        data["ssl_hash"] = get.ssl_hash or ""
    else:
        data.setdefault("ssl_hash", getattr(get, "ssl_hash", "") or "")
    if hasattr(get, "auto_deploy"):
        data["auto_deploy"] = parse_auto_deploy_flag(get.auto_deploy)
    elif "auto_deploy" not in data:
        data["auto_deploy"] = 0
    return data
