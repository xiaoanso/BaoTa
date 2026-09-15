import json
import os
import time

import public
import requests

from mod.project.ssl import plugin

class main:
    def __init__(self):
        if not os.path.exists("/www/server/deploy_plugin"):
            os.makedirs("/www/server/deploy_plugin")

        # 部署授权表
        self.M("").execute("""create table if not exists deploy_auths
(
    `id`          integer not null
        constraint deploy_auths_pk
            primary key autoincrement,
    `name`        TEXT    not null,
    `config`      TEXT    not null,
    `type`        TEXT    not null,
    `create_time` TEXT,
    `update_time` TEXT
);""", ())

        # 部署目标表
        self.M("").execute("""create table if not exists deploy_targets
(
    `id`          integer not null
        constraint deploy_targets_pk
            primary key autoincrement,
    `auth_id`    integer not null,
    `name`        TEXT    not null,
    `action`      TEXT    not null,
    `params`      TEXT    not null,
    `type`        TEXT    not null,
    `create_time` TEXT,
    `update_time` TEXT
);""",())
        self._ensure_target_columns()

    def _ensure_target_columns(self):
        """二次开发：证书绑定与自动部署字段"""
        try:
            import sqlite3
            db_file = public.get_panel_path() + '/data/db/ssl_data.db'
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(deploy_targets)")
            names = {row[1] for row in cur.fetchall()}
            if "ssl_hash" not in names:
                cur.execute("ALTER TABLE deploy_targets ADD COLUMN ssl_hash TEXT DEFAULT ''")
            if "auto_deploy" not in names:
                cur.execute("ALTER TABLE deploy_targets ADD COLUMN auto_deploy INTEGER DEFAULT 0")
            conn.commit()
            conn.close()
        except Exception as e:
            public.print_log("deploy_targets 字段迁移失败: {}".format(e))

    def M(self, table_name):
        import db
        sql = db.Sql()
        sql._Sql__DB_FILE = public.get_panel_path() + '/data/db/ssl_data.db'
        sql._Sql__encrypt_keys = []
        return sql.table(table_name)

    def get_plugins(self, get):
        try:
            cloud_plugins = requests.get("{}/thirdparty_deploy/deploy_plugins.json".format(public.get_url()), timeout=10).json()
            if type(cloud_plugins) != list:
                cloud_plugins = []
        except:
            cloud_plugins = []
        local_plugins = plugin.get_plugins()
        plugins = []
        for cp in cloud_plugins:
            cp['install'] = True
            cp['update'] = False

            for lp in local_plugins:
                if cp['name'] == lp['name']:
                    cp['install'] = False
                    cp.update(lp)
                    if cp['version'] != lp['version']:
                        cp['update'] = True
                    break
            plugins.append(cp)
        for lp in local_plugins:
            exist = False
            for cp in cloud_plugins:
                if cp['name'] == lp['name']:
                    exist = True
                    break
            if not exist:
                lp['install'] = False
                lp['update'] = False
                plugins.append(lp)
        # 排序：已安装的在前，未安装的在后；btpanel插件排第一
        plugins.sort(key=lambda x: (x['install']))

        return plugins

    def install_plugin(self, get):
        if 'plugin_name' not in get or not get.plugin_name:
            return {'status': False, 'msg': '缺少参数plugin_name'}
        name = get.plugin_name

        if os.path.exists("/tmp/deploy_plugin_{}.log".format(name)):
            return public.returnMsg(False, '已有相同安装任务在队列中，请稍后再试')
        else:
            # 判断系统架构
            arch = public.ExecShell("uname -m")[0].strip()
            if arch == 'x86_64':
                get.plugin_name += '-x86_64'
            elif arch in ['aarch64']:
                get.plugin_name += '-aarch64'
            else:
                return public.returnMsg(False, '不支持当前系统架构：{}'.format(arch))

            public.ExecShell("(wget -O /www/server/deploy_plugin/{} {}/thirdparty_deploy/deploy_plugin/{} -T 10 && chmod 755 /www/server/deploy_plugin/{}) >> /tmp/deploy_plugin_{}.log 2>&1".format(
                name, public.get_url(), get.plugin_name, name, name))
            public.ExecShell("rm -f /tmp/deploy_plugin_{}.log".format(name))

            if not os.path.exists("/www/server/deploy_plugin/{}".format(name)):
                return public.returnMsg(False, '插件下载安装失败，请稍后重试')

            return public.returnMsg(True, '安装完成')

    def uninstall_plugin(self, get):
        if 'plugin_name' not in get or not get.plugin_name:
            return {'status': False, 'msg': '缺少参数plugin_name'}
        local_plugins = plugin.get_plugins()
        for lp in local_plugins:
            if lp['name'] == get.plugin_name:
                if self.M('deploy_auths').where("type=?", (get.plugin_name,)).count() > 0:
                    return {'status': False, 'msg': '请先删除该插件相关的授权配置'}
                try:
                    os.remove(lp['path'])
                    return {'status': True, 'msg': '卸载成功'}
                except Exception as e:
                    return {'status': False, 'msg': '卸载失败：{}'.format(str(e))}
        return {'status': False, 'msg': '插件未安装'}

    # 新增授权
    def add_deploy_auth(self, get):
        if 'name' not in get or not get.name:
            return {'status': False, 'msg': '缺少参数name'}
        if 'config' not in get or not get.config:
            return {'status': False, 'msg': '缺少参数config'}
        if 'type' not in get or not get.type:
            return {'status': False, 'msg': '缺少参数type'}
        # 获取插件配置
        local_plugins = plugin.get_plugins()
        plugin_config = None
        for lp in local_plugins:
            if lp['name'] == get.type:
                plugin_config = lp['config']
                break
        if not plugin_config:
            return {'status': False, 'msg': '未知的授权类型'}
        # 检查config
        try:
            config = json.loads(get.config)
        except Exception as e:
            return {'status': False, 'msg': '参数config格式错误，必须为JSON格式'}
        for key in plugin_config:
            if key["name"] not in config and key['required']:
                return {'status': False, 'msg': '参数config缺少字段{}'.format(key["name"])}

        # 检查同名授权是否存在
        exist = self.M('deploy_auths').where('name=?', (get.name,)).count()
        if exist > 0:
            return {'status': False, 'msg': '同名授权已存在'}

        data = {
            'name': get.name,
            'config': get.config,
            'type': get.type,
            'create_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            'update_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        }
        self.M('deploy_auths').insert(data)
        return {'status': True, 'msg': '添加成功'}

    # 修改授权
    def edit_deploy_auth(self, get):
        if 'auth_id' not in get or not get.auth_id:
            return {'status': False, 'msg': '缺少参数id'}
        if 'name' not in get or not get.name:
            return {'status': False, 'msg': '缺少参数name'}
        if 'config' not in get or not get.config:
            return {'status': False, 'msg': '缺少参数config'}
        if 'type' not in get or not get.type:
            return {'status': False, 'msg': '缺少参数type'}
        # 获取插件配置
        local_plugins = plugin.get_plugins()
        plugin_config = None
        for lp in local_plugins:
            if lp['name'] == get.type:
                plugin_config = lp['config']
                break
        if not plugin_config:
            return {'status': False, 'msg': '未知的授权类型'}
        # 检查config
        try:
            config = json.loads(get.config)
        except Exception as e:
            return {'status': False, 'msg': '参数config格式错误，必须为JSON格式'}
        for key in plugin_config:
            if key["name"] not in config and key['required']:
                return {'status': False, 'msg': '参数config缺少字段{}'.format(key["name"])}

        # 检查同名授权是否存在
        exist = self.M('deploy_auths').where('name=? AND id!=?', (get.name, get.auth_id)).count()
        if exist > 0:
            return {'status': False, 'msg': '同名授权已存在'}

        data = {
            'name': get.name,
            'config': get.config,
            'type': get.type,
            'update_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        }
        self.M('deploy_auths').where('id=?', (get.auth_id,)).update(data)
        return {'status': True, 'msg': '修改成功'}

    # 删除授权
    def delete_deploy_auth(self, get):
        if 'auth_id' not in get or not get.auth_id:
            return {'status': False, 'msg': '缺少参数id'}

        if self.M('deploy_targets').where('auth_id=?', (get.auth_id,)).count() > 0:
            return {'status': False, 'msg': '请先删除该授权相关的部署目标'}

        self.M('deploy_auths').where('id=?', (get.auth_id,)).delete()
        return {'status': True, 'msg': '删除成功'}

    # 获取授权列表
    def get_deploy_auths(self, get):
        w_sql = ""
        if "search" in get and get.search:
            w_sql += " and name like'%{}%'".format(get.search)
        local_plugins = plugin.get_plugins()
        plugin_name_dic = {lp['name']: lp["description"] for lp in local_plugins}
        w_sql += " and type in ('{}')".format("','".join(plugin_name_dic.keys()))

        p = 1
        if "p" in get and get.p:
            p = int(get.p)
        limit = 10
        if "limit" in get and get.limit:
            limit = int(get.limit)
        if p == -1:
            data = self.M("deploy_auths").where("1=1 {}".format(w_sql), ()).order('create_time desc').select()
        else:
            data = self.M("deploy_auths").where("1=1 {}".format(w_sql), ()).order('create_time desc').limit('{},{}'.format((p - 1) * limit, limit)).select()
        count = self.M("deploy_auths").where("1=1 {}".format(w_sql), ()).count()
        for d in data:
            try:
                d['config'] = json.loads(d['config'])
            except:
                d['config'] = {}
            d["description"] = plugin_name_dic[d["type"]]
        return {'data': data, 'count': count}

    # 新增部署目标
    def add_deploy_target(self, get):
        if 'auth_id' not in get or not get.auth_id:
            return {'status': False, 'msg': '缺少参数auth_id'}
        if 'name' not in get or not get.name:
            return {'status': False, 'msg': '缺少参数name'}
        if 'method' not in get or not get.method:
            return {'status': False, 'msg': '缺少参数method'}
        if 'params' not in get or not get.params:
            return {'status': False, 'msg': '缺少参数params'}
        if 'type' not in get or not get.type:
            return {'status': False, 'msg': '缺少参数type'}

        # 检查同名目标是否存在
        exist = self.M('deploy_targets').where('name=?', (get.name,)).count()
        if exist > 0:
            return {'status': False, 'msg': '同名部署目标已存在'}
        # 检查授权是否存在
        auth = self.M('deploy_auths').where('id=? and type=?', (get.auth_id, get.type)).find()
        if not auth:
            return {'status': False, 'msg': '授权不存在'}
        # 检查插件和部署方法是否存在
        local_plugins = plugin.get_plugins()
        plugin_found = False
        for lp in local_plugins:
            if lp['name'] == get.type:
                plugin_found = True
                action_found = False
                for action in lp['actions']:
                    if action['name'] == get.method.strip():
                        action_found = True
                        # 检查params格式
                        if action['params'] is None:
                            if get.params.strip() != '{}' and get.params.strip() != '':
                                return {'status': False, 'msg': '参数params格式错误，该方法不需要参数'}
                            break
                        try:
                            params = json.loads(get.params)
                        except Exception as e:
                            return {'status': False, 'msg': '参数params格式错误，必须为JSON格式'}
                        for key in action['params']:
                            if key["name"] not in params and key['required']:
                                return {'status': False, 'msg': '参数params缺少字段{}'.format(key["name"])}
                        break
                if not action_found:
                    return {'status': False, 'msg': '部署方法不存在'}
                break
        if not plugin_found:
            return {'status': False, 'msg': '插件不存在'}

        data = {
            'auth_id': get.auth_id,
            'name': get.name,
            'action': get.method,
            'params': get.params,
            'type': get.type,
            'ssl_hash': getattr(get, 'ssl_hash', '') or '',
            'auto_deploy': 1 if str(getattr(get, 'auto_deploy', 0) or 0) in ('1', 'true', 'True') else 0,
            'create_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            'update_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        }
        self.M('deploy_targets').insert(data)
        return {'status': True, 'msg': '添加成功'}

    # 修改部署目标
    def edit_deploy_target(self, get):
        if 'target_id' not in get or not get.target_id:
            return {'status': False, 'msg': '缺少参数id'}
        if 'auth_id' not in get or not get.auth_id:
            return {'status': False, 'msg': '缺少参数auth_id'}
        if 'name' not in get or not get.name:
            return {'status': False, 'msg': '缺少参数name'}
        if 'method' not in get or not get.method:
            return {'status': False, 'msg': '缺少参数method'}
        if 'params' not in get or not get.params:
            return {'status': False, 'msg': '缺少参数params'}
        if 'type' not in get or not get.type:
            return {'status': False, 'msg': '缺少参数type'}

        # 检查同名目标是否存在
        exist = self.M('deploy_targets').where('name=? AND id!=?', (get.name, get.target_id)).count()
        if exist > 0:
            return {'status': False, 'msg': '同名部署目标已存在'}
        # 检查授权是否存在
        auth = self.M('deploy_auths').where('id=? and type=?', (get.auth_id, get.type)).find()
        if not auth:
            return {'status': False, 'msg': '授权不存在'}
        # 检查插件和部署方法是否存在
        local_plugins = plugin.get_plugins()
        plugin_found = False
        for lp in local_plugins:
            if lp['name'] == get.type:
                plugin_found = True
                action_found = False
                for action in lp['actions']:
                    if action['name'] == get.method:
                        action_found = True
                        # 检查params格式
                        if action['params'] is None:
                            if get.params.strip() != '{}' and get.params.strip() != '':
                                return {'status': False, 'msg': '参数params格式错误，该方法不需要参数'}
                            break
                        try:
                            params = json.loads(get.params)
                        except Exception as e:
                            return {'status': False, 'msg': '参数params格式错误，必须为JSON格式'}
                        for key in action['params']:
                            if key["name"] not in params and key['required']:
                                return {'status': False, 'msg': '参数params缺少字段{}'.format(key["name"])}
                        break
                if not action_found:
                    return {'status': False, 'msg': '部署方法不存在'}
                break
        if not plugin_found:
            return {'status': False, 'msg': '插件不存在'}
        data = {
            'auth_id': get.auth_id,
            'name': get.name,
            'action': get.method,
            'params': get.params,
            'type': get.type,
            'update_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        }
        if hasattr(get, 'ssl_hash'):
            data['ssl_hash'] = get.ssl_hash or ''
        if hasattr(get, 'auto_deploy'):
            data['auto_deploy'] = 1 if str(get.auto_deploy) in ('1', 'true', 'True') else 0
        self.M('deploy_targets').where('id=?', (get.target_id,)).update(data)
        return {'status': True, 'msg': '修改成功'}

    # 删除部署目标
    def delete_deploy_target(self, get):
        if 'target_id' not in get or not get.target_id:
            return {'status': False, 'msg': '缺少参数id'}
        self.M('deploy_targets').where('id=?', (get.target_id,)).delete()
        return {'status': True, 'msg': '删除成功'}

    # 获取部署目标列表
    def get_deploy_targets(self, get):
        w_sql = ""
        if "search" in get and get.search:
            w_sql += " and name like'%{}%'".format(get.search)
        if "type" in get and get.type:
            w_sql += " and type='{}'".format(get.type)
        local_plugins = plugin.get_plugins()
        plugin_name_dic = {lp['name']: {"description": lp["description"], "actions": { a["name"]: a["description"] for a in lp["actions"]}} for lp in local_plugins}
        w_sql += " and type in ('{}')".format("','".join(plugin_name_dic.keys()))

        p = 1
        if "p" in get and get.p:
            p = int(get.p)
        limit = 10
        if "limit" in get and get.limit:
            limit = int(get.limit)
        if p == -1:
            data = self.M("deploy_targets").where("1=1 {}".format(w_sql), ()).order('create_time desc').select()
        else:
            data = self.M("deploy_targets").where("1=1 {}".format(w_sql), ()).limit('{},{}'.format((p - 1) * limit, limit)).order('create_time desc').select()
        count = self.M("deploy_targets").where("1=1 {}".format(w_sql), ()).count()
        for d in data:
            try:
                d['params'] = json.loads(d['params'])
            except:
                d['params'] = {}

            auth_name = self.M('deploy_auths').where('id=?', (d['auth_id'],)).getField('name')
            if auth_name:
                d["description"] = auth_name+" - "+plugin_name_dic[d["type"]]["description"]
            else:
                d["description"] = plugin_name_dic[d["type"]]["description"]
            d["action_description"] = plugin_name_dic[d["type"]]["actions"].get(d["action"], "")
        return {'data': data, 'count': count}

    def get_actions(self, get):
        if 'plugin_name' not in get or not get.plugin_name:
            return {'status': False, 'msg': '缺少参数plugin_name'}
        return plugin.get_actions(get.plugin_name)

    def execute_action(self, get):
        # 获取证书来源
        if "cert" in get and get.cert and "key" in get and get.key:
            cert = get.cert
            key = get.key
        elif "oid" in get and get.oid:
            import panelSSL
            ssl_obj = panelSSL.panelSSL()
            rep = ssl_obj.get_order_find(get)
            cert = rep['certificate']+"\n"+rep['caCertificate']
            key = rep['privateKey']
        elif ("ssl_hash" in get and get.ssl_hash) or ("index" in get and get.index):
            from sslModel import certModel
            cert_obj = certModel.main()
            cert_info = cert_obj.GetCert(get)
            if 'privkey' not in cert_info or not cert_info['privkey']:
                return {'status': False, 'msg': '证书私钥不存在'}
            cert = cert_info['fullchain']
            key = cert_info['privkey']
        else:
            return {'status': False, 'msg': '缺少证书参数'}
        if "target_id" not in get or not get.target_id:
            return {'status': False, 'msg': '缺少参数target_id'}
        # 获取部署目标
        target = self.M('deploy_targets').where('id=?', (get.target_id,)).find()
        if not target:
            return {'status': False, 'msg': '部署目标不存在'}
        # 获取授权
        auth = self.M('deploy_auths').where('id=?', (target['auth_id'],)).find()
        if not auth:
            return {'status': False, 'msg': '部署授权不存在'}
        # 组装参数
        try:
            params = json.loads(target['params'])
            config = json.loads(auth['config'])
        except Exception as e:
            return {'status': False, 'msg': '部署目标参数格式错误'}
        params.update(config)
        params["cert"] = cert
        params["key"] = key

        return plugin.call_plugin(auth["type"], target["action"], params)

    @staticmethod
    def _domain_matched(cert_domains, target_domain: str) -> bool:
        if not target_domain or not cert_domains:
            return False
        td = target_domain.strip().lower().lstrip("*.")
        for d in cert_domains:
            if not d:
                continue
            dd = str(d).strip().lower()
            if dd == target_domain.strip().lower():
                return True
            if dd.startswith("*.") and (td == dd[2:] or td.endswith("." + dd[2:])):
                return True
            if td == dd.lstrip("*."):
                return True
        return False

    def _notify_deploy(self, title: str, lines: list, success: bool = True):
        """到期提醒通道：复用面板告警（邮件/钉钉等已配置的通道）"""
        try:
            slist = [">结果：{}".format("成功" if success else "失败")] + [">" + str(x) for x in lines]
            msg = public.get_push_info(title, slist)
            # 尝试各通道；未配置则仅写日志
            for module in ("mail", "dingding", "weixin", "feishu", "wx_account"):
                try:
                    public.push_msg(module, msg)
                except Exception:
                    pass
            public.WriteLog("SSL授权部署", "{} | {}".format(title, "；".join(str(x) for x in lines)))
        except Exception as e:
            public.WriteLog("SSL授权部署", "通知发送失败: {} | {}".format(e, title))

    def execute_target_by_id(self, target_id, ssl_hash=None, oid=None, cert=None, key=None, max_retry=3, retry_interval=10):
        """执行单个部署目标，失败有限重试"""
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
            last = self.execute_action(get)
            ok = False
            if isinstance(last, dict):
                # 插件协议 success / 面板 False
                if last.get("status") in ("success", True, 1, "1"):
                    ok = True
                if last.get("status") is True or last.get("status") == "success":
                    ok = True
                # call_plugin 返回 status=success|error
                if last.get("status") == "error":
                    ok = False
                if last.get("status") is False:
                    ok = False
            if ok:
                return True, last
            if i + 1 < max_retry:
                time.sleep(retry_interval)
        return False, last

    def auto_deploy_on_cert_change(self, new_ssl_hash, domains=None, old_ssl_hash=None, oid=None, notify_success=True):
        """
        证书申请/续签成功后：按 ssl_hash 或域名匹配 auto_deploy 目标并推送。
        续签后 hash 会变，需把旧 hash 目标迁到新 hash。
        """
        self._ensure_target_columns()
        domains = domains or []
        if isinstance(domains, str):
            domains = [d.strip() for d in domains.split(",") if d.strip()]

        if old_ssl_hash and new_ssl_hash and old_ssl_hash != new_ssl_hash:
            try:
                self.M("deploy_targets").where("ssl_hash=?", (old_ssl_hash,)).update(
                    {"ssl_hash": new_ssl_hash, "update_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
                )
            except Exception:
                pass

        try:
            rows = self.M("deploy_targets").where("auto_deploy=?", (1,)).select()
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
            by_domain = self._domain_matched(domains, target_domain) if target_domain else False
            if not bound and not by_domain:
                continue
            if by_domain and new_ssl_hash and (t.get("ssl_hash") or "") != new_ssl_hash:
                try:
                    self.M("deploy_targets").where("id=?", (t["id"],)).update(
                        {"ssl_hash": new_ssl_hash, "update_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}
                    )
                except Exception:
                    pass

            ok, resp = self.execute_target_by_id(
                t["id"], ssl_hash=new_ssl_hash, oid=oid, max_retry=3, retry_interval=10
            )
            msg = ""
            if isinstance(resp, dict):
                msg = resp.get("message") or resp.get("msg") or ""
            item = {"target_id": t["id"], "name": t.get("name"), "domain": target_domain, "ok": ok, "msg": msg}
            results.append(item)
            if ok and notify_success:
                self._notify_deploy(
                    "SSL授权部署成功",
                    ["目标：{}".format(t.get("name")), "域名：{}".format(target_domain), "ssl_hash：{}".format(new_ssl_hash)],
                    True,
                )
            if not ok:
                self._notify_deploy(
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