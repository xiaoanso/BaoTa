# 本机 macOS 用 Docker 跑 Linux 宝塔（二次开发）

面板**源码用本仓库**。官方 `install_panel.sh` / `btpanel/baota:slim` 里的面板代码不作为开发源：安装脚本会从 `download.bt.cn` 拉官网包，不会读你这份 git。

镜像只提供 Linux 运行时：`pyenv`、系统包、`/bt.sh`。容器启动时把本仓库挂到 `/www/server/panel`，再用独立 volume 盖住 `pyenv` / `data` / `logs`，避免把运行时写进 git。

```bash
cd docker/baota-dev
docker compose up -d
```

浏览器打开（安全入口，User-Agent 太短会被面板当成爬虫 404）：

`http://127.0.0.1:8888/btpanel`

账号密码以容器内 `bt default` 为准。curl 验证时要用完整浏览器 UA。

```bash
docker compose exec panel bt default
docker compose exec panel /www/server/panel/pyenv/bin/python3 \
  /www/server/panel/mod/project/ssl/ssl_ext/verify.py
printf '%s\n' '{"action":"get_metadata","params":{}}' \
  | docker compose exec -T panel /www/server/deploy_plugin/qiniu
```

改仓库里的 Python 即改容器内面板源码；`BT-Panel` 进程一般要重启才加载：

```bash
docker compose exec panel bash -lc '/etc/init.d/bt restart'
```

七牛插件已 bind-mount 到官方扫描目录 `/www/server/deploy_plugin/qiniu`。

---

## 为什么不能「在 Mac 上跑 install_panel.sh 装本地源码」

脚本硬性条件：Linux、root、内存 ≥ 450MB、装到 `/www`。Darwin 直接退出。`btg26` 只是 `IDC_CODE`，不是安装包名。非交互要加 `-y`。即便在容器里跑这条命令，装上的仍是官网 tarball，不是本仓库。

---

## 和 yianso-ecs 的差异

| | 本机 Docker | yianso-ecs |
|--|-------------|------------|
| 面板代码 | 本仓库 bind-mount | 机器上的 `/www/server/panel` |
| 架构 | 默认 arm64（Apple Silicon） | x86_64 |
| 七牛插件 | Python，两边都能跑 | 同左 |
| 要贴近 ECS | compose 里加 `platform: linux/amd64`（慢，用 qemu） | — |

日常二次开发用 arm64 即可。
