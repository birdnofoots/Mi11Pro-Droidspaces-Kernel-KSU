# mars（小米11 Pro）ubuntu 容器 DSH 部署 — 交付说明（2026-10-13）

目标：mars 的 Droidspaces **ubuntu 容器**里跑 DeepSeek Harness Web，局域网访问、模型可配置、
Agent 预设无报错，拓扑与一加工作区一致。**已重启自愈验收全过。**

## 访问方式（局域网）

- **地址**：`http://<mars 的 WiFi IP>:3080/`（当前 `http://192.168.43.246:3080/`；IP 随网络变化，
  每次开机后 `dsh-url-lan.txt` 会带最新 IP）
- **Basic Auth**：`admin` / `PiTqoTJ37PO1nvUy`
- **首次**要带 token 换 cookie：手机存储 **`/sdcard/dsh-url-lan.txt`** 里的完整 URL（每次开机自动更新）。
  浏览器换过一次 cookie 后长期有效（实测重启后旧 cookie 依然 200），之后直接开 `http://<IP>:3080/` 即可。

## 架构（与一加工作区同构）

```
浏览器 → mars:3080 (iptables DNAT, 开机脚本) → ubuntu 容器 172.28.1.2:8080 (nginx BasicAuth)
       → 127.0.0.1:3080 (dsh web, 只绑 loopback —— 0.0.0.0 被 dsh 安全策略拒绝)
```

- nginx 与一加蓝本逐字一致（Host 骗术 + `window.__DSH_TRANSPORT__` 解锁注入 + WebSocket + 300m 上传）。
- dsh web 由 **systemd** `dsh-web.service` 托管（Restart=always，开机自启）；
  wrapper `/usr/local/bin/dsh-web.sh` 启动后把 token URL 写到手机 `/sdcard/dsh-url.txt`。
- **dsh-motrix 插件**（工作区自研，`/root/mars/work/dsh-motrix`，profile 软链同路径）：
  `/motrix` 命令集 + Xvfb(:99) + Motrix 无头引擎（`apt install xvfb` + `/opt/Motrix` 211MB arm64 + Electron 依赖库）。

## 组件清单（ubuntu 容器内）

| 组件 | 位置 |
|---|---|
| node v22.18.0 | `/opt/nodejs`（`/usr/local/bin/node` 软链） |
| dsh 0.1.5-rc.3 | `/usr/lib/node_modules/@deepseek-ai/dsh`（`/usr/bin/dsh` 软链） |
| dsh 配置 | `/root/.dsh/`（settings.yaml 模型/凭证/profiles，自一加原样复制） |
| dsh-motrix 插件 | `/root/mars/work/dsh-motrix`（同路径 ⇒ profile 软链直接生效） |
| nginx 1.18 | 站点 `/etc/nginx/sites-enabled/dsh`；认证 `/etc/nginx/dsh.htpasswd`（$6$ 格式） |
| Motrix + Xvfb | `/opt/Motrix/motrix`、`/usr/bin/Xvfb` |

## mars 侧（Android root）

- **开机脚本** `/data/adb/service.d/99-dsh-fwd.sh`（ksud 执行）：
  ① `droidspaces start -n ubuntu` ② ip_forward + iptables DNAT 3080→172.28.1.2:8080 + FORWARD ACCEPT
  ③ 发布 `/sdcard/dsh-url-lan.txt`。
- 容器固定 IP：`/data/local/Droidspaces/Containers/ubuntu/container.config` 加了 `static_nat_ip=172.28.1.2`。

## 运维速查

```bash
# 进容器（adb 走 USB: adb -s d6fba222；WiFi: adb -s <IP>:5555）
adb -s d6fba222 shell "su -c '/data/local/tmp/droidspaces --name=ubuntu run /bin/sh'"

# 服务
systemctl status dsh-web nginx | less
journalctl -u dsh-web -n 30 --no-pager

# 当前访问 URL
cat /sdcard/dsh-url-lan.txt     # 局域网(带 token)
cat /sdcard/dsh-url.txt         # 容器内 loopback 形式
```

## 验收记录（2026-10-13）

- 无认证 401 / 带 Basic Auth + token 303→Set-Cookie / cookie 访问 200 ✓
- `/api/*` 经 cookie 认证可达（404-not-found 是路由不存在，非 401）✓
- web 日志零 error；`/motrix` 插件加载 ✓；Xvfb + Motrix 引擎进程在跑 ✓
- **整机重启自愈**：容器自动拉起、dsh-web/nginx active、DNAT 规则自动装、LAN URL 自动更新 ✓
- 重启后旧浏览器 cookie 仍 200（签发密钥随 `.credentials.yaml` 持久化）✓

## 已知事项

- 一加工作区 `dsh_nginx_auth.txt` 便签里的密码已过期（本机 nginx 也 401）；mars 实例按便签密码重置为
  `admin/PiTqoTJ37PO1nvUy`（$6$ hash）。一加那套未动。
- dsh 每次启动打印的 token 会变，但浏览器 cookie 长期有效；丢了就看 `/sdcard/dsh-url-lan.txt`。
- dsh 安全策略不许绑 0.0.0.0，外露永远要经 nginx 反代（勿改直绑，会拒启）。
