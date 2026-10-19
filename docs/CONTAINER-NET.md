# Droidspaces 容器网络(NAT)与 nr436-shim —— ★新装容器必读

> **los101 起默认 APatch**（BBR 基线），所以这份 shim 仍是容器 NAT 的必需项；
> KernelSU v0.9.5 线仅历史/可选（KSU 内核走 `MARS-CLOSE-RANGE-436`，容器免 shim）。

> TL;DR: **每新装/新导入一个容器 rootfs，都要装一次 `nr436-shim`**（它在 init 前装 seccomp 过滤器）。
> 不装 ⇒ 现代 systemd/glibc 发行版(Ubuntu/Debian/Fedora…)的服务**全部起不来**
> ⇒ 没有 DHCP ⇒ "NAT 模式网络不通"。busybox 系(alpine/openwrt)当前不装也能联网，
> 但建议统一装上（容器内一旦跑 glibc 2.34+ 程序就会踩雷）。

> **2026-10-19（Droidspaces 7.0）**：App 会在容器启动时把 `/sbin/init` 重置回 systemd 符号链，
> 旧的“直接替换 `/sbin/init`”会被还原。systemd 容器现在用**持久位**：
> `/lib/systemd/systemd` = shim，`/lib/systemd/systemd.real` = 真 systemd，
> `/sbin/init.real -> /lib/systemd/systemd.real`；`/sbin/init -> /lib/systemd/systemd` 仍指向 shim。
> `patches/nr436-shim-install.sh` 已自动按这个方式安装；`patches/nr436-shim` 是预编译 arm64 静态二进制。
>
> **Docker**：los103 已打开 `BRIDGE_NETFILTER`/`IP_SET*`/`NETFILTER_XT_MATCH_ADDRTYPE`/`NF_TABLES` 等，
> `docker run --rm hello-world` 与 `alpine` bridge（172.17.0.2 → ping 1.1.1.1 0%）实测通过。

> **systemd ≥ 260 的镜像在 5.4 内核上起不来**（实测 Kali 2026.3 = systemd 262）：
> systemd 260 起用 `STATX_ATTR_MOUNT_ROOT`（内核 6.8+）判断挂载点，5.4 没有该属性 ⇒
> `Failed to mount API filesystems` → `Exiting PID 1` ⇒ 容器启动约 0.3s 后退出。
> 这不是 436/shim 的问题，**shim 修不了**。请用 systemd ≤259 的镜像（Kali 2025.x、Ubuntu 24.04、
> Debian 13 等），或 `--init=/bin/bash` 临时进容器（网络需手动 `ip addr add 172.28.1.x/16 ...`）。

## 1. 为什么要装(根因,30 秒版)

- 手机是 **APatch root**：刷机时 KernelPatch(bmax121) 往内核注入隐藏系统调用 **supercall**，
  它占用了 **436 号**系统调用槽（KernelPatch 自带 unistd.h 即 `#define __NR_close_range 436`）；
  非法调用一律返回 `EINVAL`。
- 而现代 glibc(2.34+) 把 **436 号当作 `close_range`**；systemd 249 的 `close_all_fds()` 调
  `close_range(3,-1,0)` 收到 `EINVAL` 后**不回退**（只认 ENOSYS/EPERM/EACCES）
  ⇒ **每个服务 spawn 都死在 FDS 步** ⇒ networkd/sshd/docker 全灭 ⇒ 没 DHCP ⇒ "NAT 不通"。
- 这**不是 Droidspaces/NAT 的 bug**，是 KernelPatch 隐藏系统调用与 glibc 编号相撞。
  内核级修法无效（kpatch 在刷机时覆写表项），**用户态 seccomp 适配层即正解**。

## 2. shim 干了什么

`patches/nr436-shim.c` → 编译出的静态二进制（arm64），装为容器 `/sbin/init`
（原 init 移存 `/sbin/init.real`，符号链原样）：

1. 装一个 seccomp 过滤器：**436 号调用里带 KernelPatch supercall 魔数(0x1158)的放行**
   （保 APatch 的 IPC），其余一律改成返回 **ENOSYS**；
2. 再 exec 真 init（argv[0] 保留原名 —— busybox 靠 argv[0] 选 applet）。

⇒ systemd 收到 ENOSYS 走 /proc 逐个关闭的回退路径 ⇒ 服务全部复活 ⇒
networkd 自动拿 DHCP ⇒ NAT 全自动通。

## 3. ★新装容器必做清单

```bash
# 0) 把两样东西推到手机(149 上执行)
adb push nr436-shim        /sdcard/nr436-shim       # 本文件同目录产物, 或本地编译(见 §5)
adb push nr436-shim-install.sh /sdcard/

# 1) 一键安装(自动识别镜像型/目录型 rootfs, 幂等, 可重复跑)
adb shell 'su -c sh /sdcard/nr436-shim-install.sh <容器名>'

# 2) 验证(容器内)
adb shell 'su -c "droidspaces --name=<容器名> run /bin/sh -c \"\
  ls -la /sbin/init /sbin/init.real; \
  [ \"\$(readlink /sbin/init.real 2>/dev/null)\" ] && echo init.real=符号链✓\""'
# 期望: /sbin/init = 655800B 可执行(shim), /sbin/init.real = 原 init
# systemd 系再看: systemctl is-system-running  → degraded/running(而不是全红)
```

**什么时候必须装**：
| 场景 | 要装? |
|---|---|
| 新下载/新导入 rootfs(Ubuntu/Debian/Arch/Fedora…) | ✅ 必装 |
| 新建容器后第一次启动前/后 | ✅ 必装(装完重启容器生效) |
| alpine/openwrt 等 busybox 系 | 建议装(当前不装也能联网) |
| 容器 rootfs 重新解包/重置/换镜像 | ✅ 重装(init 又是原版了) |
| 只是重启容器/重启手机 | ❌ 不用(rootfs 里已持久) |

## 4. 安装失败/边角情况

- **容器里看不到 `/storage/emulated/0/`**（openwrt 默认 `enable_android_storage=0`）：
  两种解法任选：① container.config 里 `enable_android_storage=1` 后重启容器再装；
  ② 用 stdin 灌二进制：`adb shell "su -c 'droidspaces --name=X run /bin/sh -c \"cat > /sbin/nr436-shim\"'" < nr436-shim`。
- **容器已经起不来（比如 shim 半装状态）**：`nr436-shim-install.sh` 现在会自动走**离线模式**
  （停容器 → loop 挂载 `rootfs.img` → 装 shim → 卸载），不需要容器能跑；
  也可用 `--init` 覆盖救活再修：
  `droidspaces --name=X --init=/sbin/init.real start`（或 `--init=/bin/busybox`），
  进去把 `/sbin/init` 补好，再正常重启。
- **卸载**：容器内 `mv /sbin/init.real /sbin/init` 即还原。
- **千万别**在容器运行时手动 `mount -o loop rootfs.img` 去改文件 —— 实测 2/2 触发手机
  异常重启（详见 VERSIONS.md §O7; RescuePartyPlus 会弹"设备内部出现问题"）。
  改 rootfs 一律走"容器内操作"或停容器后再用 droidspaces 自己挂载的路径。
- droidspaces 给 init 传的是内核式参数(如 `systemd.unified_cgroup_hierarchy=1`)，
  shim v3 已正确透传；**别手工把参数当程序名 exec**。

## 5. 源码与编译

```bash
# 源码: patches/nr436-shim.c (无第三方依赖, 只用 Linux seccomp BPF)
gcc -static -O2 -o nr436-shim patches/nr436-shim.c     # aarch64 交叉/本机皆可
```

过滤器逻辑（v3）：
- `nr != 436` → ALLOW；
- `nr == 436` 且 `args[1] & 0xFFFF0000 == 0x11580000`(supercall 魔数) → ALLOW；
- 其余 436 → `SECCOMP_RET_ERRNO(ENOSYS)`。
- 不设 `PR_SET_NO_NEW_PRIVS`（避免干扰 binfmt_misc 跨架构执行链；容器 init 有 CAP_SYS_ADMIN）。
