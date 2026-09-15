# SSL 自动续签 + 七牛授权部署（操作记录与复用指南）

> 环境：宝塔中国版 @ `yianso-ecs`  
> 日期：2026-09-15  
> 目标：Let's Encrypt 自动续签；CDN 域名可选自动推七牛。

---

## 1. 今日落地结果（yianso）

| 域名 | 证书 | 自动续签 | 推七牛 |
|------|------|----------|--------|
| `pic.yianso.cn` | LE（YR2） | 是（DNS） | **是**（`deploy_cdn_https`，`auto_deploy=1`） |
| `yianso.cn` | LE | 是（DNS，挂站点） | 否 |
| `mcp.yianso.cn` | LE | 是 | 否 |
| `shitu.yianso.cn` | LE | 是 | 否 |

配套能力：

- 插件：`/www/server/deploy_plugin/qiniu`（Python launcher，协议对齐阿里云 deploy_plugin）
- 面板：`deploy_targets.ssl_hash` / `auto_deploy`；`acme_v2` 续签成功钩子推授权目标；`renew_cert_v2` 纳入 `auto_deploy` 证书
- DNS：`ssl_domains.yianso.cn` → 阿里云 DNS API id
- 计划任务：每日 `acme_v2.py --renew_v2=1`

---

## 2. 架构结论（二次开发）

```
面板证书申请/续签 (acme_v2, DNS-01)
        │
        ├─ 挂站点 → 仅自动续签
        │
        └─ deploy_targets(auto_deploy=1, type=qiniu)
                 → execute_action → /www/server/deploy_plugin/qiniu
                 → 上传证书 + PUT /domain/{domain}/httpsconf
```

- **不要**把七牛 CDN 推送做成 `class/sslModel/*Model.py`（那是 DNS 提供商）。
- 授权部署走 `mod/project/ssl/deployMod.py` + `deploy_plugin`。
- CDN 域名（CNAME 到七牛）必须用 **DNS 验证**；本机 80 常被墙/超时，HTTP 验证易失败。
- 阿里云免费 DigiCert **不会**被 LE 续签任务续掉；统一改 LE。

---

## 3. 前置条件（新环境 / 新根域）

1. 安装七牛插件（本仓库）：
   ```bash
   bash mod/project/ssl/deploy_plugins/qiniu/install_to_host.sh <ssh-host>
   ```
2. 面板 **SSL → 部署授权** 添加「七牛云」AK/SK（若要推七牛）。
3. 面板 **SSL → DNS API** 添加阿里云/DNSPod；
请在阿里云 RAM 给这个 AccessKey 对应子用户授权：
  - 推荐：AliyunDNSFullAccess
  - 或最小权限：AddDomainRecord、DeleteDomainRecord、DescribeDomainRecords、DescribeDomains

RAM 至少：
   - `alidns:AddDomainRecord`
   - `alidns:DeleteDomainRecord`
   - `alidns:DescribeDomainRecords`
   - 或直接 `AliyunDNSFullAccess`
4. 根域名在「域名管理 / ssl_domains」绑定该 DNS API（工具会自动写）。
5. pyOpenSSL 过新时 `X509Req` 已移除：`acme_v2.send_csr` 需能回退 `create_csr_new`（本仓库已修）。

---

## 4. 可复用脚本

路径：`/www/server/panel/script/ssl_le_toolkit.py`（仓库：`script/ssl_le_toolkit.py`）

### 4.1 查看状态

```bash
btpython /www/server/panel/script/ssl_le_toolkit.py list-dns
btpython /www/server/panel/script/ssl_le_toolkit.py status
btpython /www/server/panel/script/ssl_le_toolkit.py status --domain pic.example.com
```

### 4.2 冷启动：七牛 CDN 域名（申请 + 推送 + 自动续签推送）

```bash
btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap \
  --root example.com \
  --domains pic.example.com,www.pic.example.com \
  --qiniu \
  --qiniu-action deploy_cdn_https
```

### 4.3 冷启动：面板站点（仅自动续签）

```bash
btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap \
  --root example.com \
  --domains app.example.com,www.app.example.com \
  --site app.example.com
```

### 4.4 已有 LE，只补七牛目标 / 再推一次

```bash
btpython /www/server/panel/script/ssl_le_toolkit.py qiniu-ensure --domain pic.example.com
btpython /www/server/panel/script/ssl_le_toolkit.py qiniu-deploy --domain pic.example.com
```

### 4.5 兼容旧入口

`script/qiniu_le_pic_setup.py` 仍可用；新域名请优先用 `ssl_le_toolkit.py`。

---

## 5. 换域名检查清单

- [ ] DNS API 已配且 RAM 权限足够  
- [ ] `--root` 为注册根域（如 `example.com`）  
- [ ] `--domains` 含要上证书的主机名（含 www 则一并写上）  
- [ ] 要推七牛：面板已有七牛授权；域名已是七牛 CDN/可走 `httpsconf`  
- [ ] 要挂站：`--site` = 面板站点名，且 nginx `0.default` 证书存在（脚本会尽量补）  
- [ ] 跑完 `status --domain ...` 确认 issuer=Let's Encrypt、`auto_deploy=1`（若七牛）  

---

## 6. 关键文件

| 路径 | 作用 |
|------|------|
| `mod/project/ssl/deploy_plugins/qiniu/qiniu` | 七牛 deploy_plugin |
| `mod/project/ssl/deploy_plugins/qiniu/install_to_host.sh` | 同步插件+面板补丁到主机 |
| `mod/project/ssl/deployMod.py` | 授权部署 + auto_deploy 钩子 |
| `class/acme_v2.py` | LE 申请/续签 + CSR 回退 + 续签后推送 |
| `script/renew_certificate.py` | 商业证续签后推送（DigiCert/商业路径） |
| `script/ssl_le_toolkit.py` | **日常复用入口** |

---

## 7. 排障速查

| 现象 | 处理 |
|------|------|
| `Forbidden.RAM` / `AddDomainRecord` | 给 AccessKey 对应 RAM 加 DNS 权限 |
| `X509Req` 不存在 | 确认已同步含 `create_csr_new` 回退的 `acme_v2.py` |
| HTTP 验证 Timeout | CDN/防火墙挡 80 → 改 DNS 验证（默认 bootstrap） |
| 七牛绑定失败但证书已上传 | 源站域名可能无 API；`pic` 类 CDN 用 `deploy_cdn_https` |
| 续签不推七牛 | 查 `auto_deploy=1`、`ssl_hash`、目标 `params.domain` 是否匹配证书 SAN |
| nginx reload 报 `0.default` 缺证书 | `ssl_le_toolkit` 会补；或手动从任一站点证书复制 |

---

## 8. 本日踩坑摘要

1. 原阿里云免费 DigiCert ≠ LE，面板续签任务无效。  
2. `pic.yianso.cn` DNS 指向七牛 CDN，HTTP 验证不可用。  
3. DNS API 空、再 RAM 无解析权限，先后挡住申请。  
4. 系统 pyOpenSSL 26.x 无 `X509Req`，需 cryptography CSR。  
5. `SetCertToSite` 需 `certName`；挂站用 `panelSite.SetSSL(key/csr)` 更直接。  
6. nginx 缺省站证书缺失会导致 `nginx -t` 失败。  


------


已整理并同步到仓库和 `yianso-ecs`。

### 文档
[mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md](mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md)  
（ECS：`/www/server/panel/mod/project/ssl/deploy_plugins/qiniu/RUNBOOK.md`）

内容含：今日结果、架构、前置条件、换域名清单、排障。

### 复用脚本
`script/ssl_le_toolkit.py`（已装到面板 `script/`）

**新七牛 CDN 域名冷启动：**
```bash
btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap \
  --root example.com \
  --domains pic.example.com,www.pic.example.com \
  --qiniu
```

**新站点仅自动续签：**
```bash
btpython /www/server/panel/script/ssl_le_toolkit.py bootstrap \
  --root example.com \
  --domains app.example.com,www.app.example.com \
  --site app.example.com
```

**查看状态：**
```bash
btpython /www/server/panel/script/ssl_le_toolkit.py status --domain pic.example.com
```

同步到其他机器仍用：`bash mod/project/ssl/deploy_plugins/qiniu/install_to_host.sh <ssh-host>`