# AGENTS.md — mars / Droidspaces 内核

给小米 11 Pro（mars, SM8350, MIUI14/Android13, 内核 `5.4.242-qgki-gbb70cde46897`）
自编 **Droidspaces 容器内核** 的真机调试 + GitHub Actions 编译工作区。

**先读** `VERSIONS.md`（权威：P1 里程碑 / 镜像血缘 / 根因表 / 配方）和 `TAKEOVER.md`
（实验流水）。`STATUS.md`/`HANDOVER.md`/`INDEX.md` 是早期存档，冲突时以 `VERSIONS.md` 为准。

## 当前基线（2026-10-19 ★ los104-apatch-bbr：APatch + BBR + IPv6 NAT + Docker/nested + USB WiFi）

- **手机当前跑的就是这一版**：内核 `5.4.242-qgki-gbb70cde46897` **#30**（`runner@`；槽 `_a`；
  APatch 11282 打补丁后已启动；`systemctl is-system-running=running`）。
- **Release/tag**：`los104-apatch-bbr`（净版 boot `09898855…` / Image `49439b2c…`），CI run `39189264577`，head `a5e4dd6`。
- **基线来源**：los103（APatch + BBR + IPv6 NAT + Docker/nested）+ **USB WiFi 驱动内建 + 固件内建**：
  `ath9k_htc`/`carl9170`（ath）、`rt2800usb`（`RT53XX`/`RT55XX`/`RT3573`/`RT33XX`/`RT35XX`/`UNKNOWN`）/`rt73usb`（ralink）、
  `rtl8187`/`rtl8xxxu`（realtek）、`mt7601u`（mediatek）。固件 `htc_7010-1.4.0.fw`、`htc_9271-1.4.0.fw`、
  `carl9170-1.fw`、`rt2870.bin`、`rt73.bin`、`rtlwifi/rtl8188efw.bin`、`rtlwifi/rtl8192cufw.bin`、`mt7601u.bin`
  已进 `EXTRA_FIRMWARE`（`gh/firmware/`）。
- **main 分支**：`los.yml` 已同时带 BBR 门控、IPv6 NAT/Docker/USB WiFi 断言与 `MARS-CLOSE-RANGE-436`；
  los104 发布 exact 构建 = tag `los104-apatch-bbr`（同配置，无 close-range）。
- **USB WiFi 实测**：`/sys/bus/usb/drivers/` 下 7 个驱动齐全，`dmesg` 有 `usbcore: registered new interface driver ...`；
  插上即用，**不需要 insmod、不需要 `/vendor/firmware`**。选型见 [`docs/USB-WIFI.md`](docs/USB-WIFI.md)
  （首选 AR9271、性价比 RT5370、要 5GHz 选 RT5572；RTL8812AU 是树外驱动别买）。
- **Docker/nested 实测**：容器内 `docker run --rm hello-world` ✅；
  `docker run --rm alpine` bridge `172.17.0.2` ping `1.1.1.1` 0% ✅；`systemctl is-system-running=running`。
- **root 方案**：默认 **APatch**（个人 superkey 不入库；`u:r:magisk:s0`、`apd`）；
  **KernelSU v0.9.5 仅历史/可选**，不再默认。
- **APatch 版本**：手机 **11282**；打补丁用同版本 App 的 `kptools`/`kpimg`
  （`work/apatch-payload-11282/`；旧 0.13.3 在 `work/apatch-payload-d03-backup/`）。
  11282 对 64MB boot 会提示 “no room for AVB footer”，但解锁 bootloader 下实测能启动。
- **nr436-shim（容器长期位）**：Droidspaces 7.0 会把 `/sbin/init` 重置成 systemd 符号链，
  所以 systemd 容器把 shim 放在 **`/lib/systemd/systemd`**，真 systemd 在 `/lib/systemd/systemd.real`，
  `/sbin/init.real -> /lib/systemd/systemd.real`；`/sbin/init -> /lib/systemd/systemd` 仍指向 shim。
  `patches/nr436-shim-install.sh` 已按这个方式更新；`patches/nr436-shim` 为预编译 arm64 静态二进制。
- **apt/Docker 源**：ubuntu 容器 apt 换 **阿里云 `ubuntu-ports`**（`/etc/apt/sources.list.bak-20261019-003757`）；
  Docker 镜像加速 `docker.1panel.live` + `docker.xuanyuan.me`（`/etc/docker/daemon.json`）。
- **BBR**：`CONFIG_TCP_CONG_BBR=y`、`DEFAULT_TCP_CONG="bbr"`、`NET_SCH_FQ=y`；真机 `bbr`。
- **IPv6 NAT**：`IP6_NF_NAT=y`、`IP6_NF_TARGET_MASQUERADE=y`（Droidspaces 7.0 检查 ✅）。
- **配方**：GOLD JSON + `mi_syms_audio=1` + `extra_config` 末尾 `BBR`，`los_commit=d42d2eb6c`；
  **不加 `KSU`**。Docker/IPv6/USB WiFi 配置已在 `configs/mars_factory.config` 基线，CI 断言。
- **验证**：进 MIUI ✅ / WiFi ✅ / 触屏/电池/相机 ✅ / 音频 ✅ / `droidspaces check` required 全过 ✅ /
  APatch root ✅ / BBR=bbr ✅ / IPv6 NAT ✅ / Docker+nested ✅ / USB WiFi 驱动注册 ✅。
- **WiFi**：原厂栈 + `/data/adb/service.d/99-wlan-mars.sh`（v6，md5 `6a5d5247…`）。
- **保留**：`work/keep-los131-apatch-bbr/`（Image / 净版 boot / modules / config / System.map / meta）；
  回退：los103 `work/keep-los129-apatch-bbr/`、los102 `work/keep-los128-apatch-bbr/`、
  los101 `work/keep-los126-apatch-bbr/`。发布包 `work/release-los103-apatch-bbr/`（los104 同名目录新建）。
- **救机**：`work/backups/boot_a-los102-apatch11282-backup-20261019.img`（md5 `99d81c33…`）、
  `boot_a-los101-backup-20261019.img`（`f48477ea…`）、KSU 备份 `a0ae428e…`；GOLD `8fcf3576…`。
  los104 回退 = 刷 `keep-los129-apatch-bbr/boot-Image-los103-apatch-bbr-APatch11282.img`（md5 `e3aac555…`）。
- 手机地址：USB `d6fba222`（缺节点跑 `scripts/usb-link-setup.sh`）；WiFi adb `adb -s 192.168.43.246:5555`。
- **绝不动一加手机**（`172.28.0.1:5555` 是宿主机！）。只操作 mars。

> 下面 P3/历史段落（2026-10-10）保留作背景；**最新配方/镜像以本节 + `VERSIONS.md` 文末 §los104 为准**。

## 硬约束

1. **只在 GitHub Actions 编译**。当前配方走 `gh/.github/workflows/los.yml`（LOS 5.4.242 基线），派发用：
   ```bash
   python3 /tmp/ghdisp2.py los.yml '{"config":"mars_factory.config","logdump":"1","wlanblock":"1",
     "ignore_vermagic":"1","mi_syms":"1","kabi":"1","allbuiltin":"1",
     "force_m":"CNSS2,CNSS_GENL,WCNSS_MEM_PRE_ALLOC","force_y":"CNSS_QCA6490",
     "hwid_deexport":"1","modules":"1","firmware_embed":"1","los_commit":"d42d2eb6c",
     "mi_syms_audio":"1",
     "extra_config":"-d PANIC_ON_OOPS,-d QCOM_FORCE_WDOG_BITE_ON_PANIC,-d PANIC_ON_SSR_NOTIF_TIMEOUT,-d DEBUG_POWER_MI,-e DETECT_HUNG_TASK,--set-val DEFAULT_HUNG_TASK_TIMEOUT 15,BBR"}'
   ```
   （`firmware_embed` 可选；**别加 `CNSS_UTILS`/`ICNSS2` 到 `force_m`**，见"关键配方"里的红字警告）
   `extra_config` 末尾的 **`BBR`** = 打开 BBR；去掉 = los96 原样。**不加 `KSU` = APatch 内核**（当前默认）。
   可复现脚本：`scripts/dispatch-los104.sh [ref]`（los104 GOLD + BBR + USB WiFi；IPv6 NAT/Docker/USB WiFi 已在基线 config）。`los_commit` 一定要钉死（否则跟随分支头）。
   ⚠️ 历史：MiCode `star-r-oss`(5.4.61) 老树已废弃（vendor 模块 ABI 对不上）。
2. **`fastboot boot` 不可用**。只用 `fastboot flash boot_a`。
3. **只改 `boot_a`**；活动槽必须 `_a`（**不要 `set_active b`**，会从错误槽启动）。
4. **刷完必须核对内核身份 + BBR**（防假阳性）：
   ```bash
   adb shell 'uname -a; zcat /proc/config.gz | grep -E "MODVERSIONS|TCP_CONG_BBR|DEFAULT_TCP_CONG"; \
              cat /proc/sys/net/ipv4/tcp_congestion_control; cat /proc/cmdline'
   ```
   自编：`runner@` + `2026` 年日期 + `# CONFIG_MODVERSIONS is not set`。
   原厂：`builder@pangu-build-component-vendor-…` + `Wed Dec 20 08:12:00 UTC 2023`。
   los104：`CONFIG_TCP_CONG_BBR=y`、`DEFAULT_TCP_CONG="bbr"`、`CONFIG_IP6_NF_NAT=y`、
   `CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y`、`CONFIG_IP_SET=y`、`CONFIG_NF_TABLES=y`、运行时 `bbr`；
   `CONFIG_ATH9K_HTC=y`、`CONFIG_RT2800USB=y`、`CONFIG_RT2800USB_RT53XX=y`、`CONFIG_MT7601U=y`。
5. 一次只改一项；证据分级 `[目]/[log]/[adb]/[?]`；失败立刻回滚（adb 能连就 GOLD 恢复脚本，否则 fastboot）。
6. `pkill -f` 会自杀 → 用 `ps | grep '[x]xx'`；`pkill -f` 的模式别出现在同一条命令行里。
7. 别碰 `typec/port0/data_role`；别对 dwc3 unbind。
8. **别启用 `/data/adb/service.d/mars-wlan-prep.sh`**（会用空 INI 盖掉原厂 WLAN 配置，见血泪坑）。

## 环境

- 工作机 = 一加 12 上的 aarch64 容器（本容器，编译派发/文档）；**mars 手机直插在一加上（USB 直连）**：
  `adb -s d6fba222` 直接可用（缺节点跑 `scripts/usb-link-setup.sh`）；WiFi 备用 `adb -s 192.168.43.246:5555`。
  （旧况：手机插在 149 x86_64 机器上、要 `ssh justin@192.168.1.149` 转发——2026-10-13 起作废。）
- 149 上的关键路径：`~/mars-build/`（`artifacts/`、`KEEP/`、`ref/`、`tools/make-bootimg.py`）、
  `~/mars/eng/builds/apatch-patched-boot-0.13.3.img`（GOLD）。
  149 侧所有工具脚本现在都在 `~/mars-keep/2026-10-10-tmp-archive/scripts-mars/`（`flash-local.sh` `gold-restore.sh`
  `acceptance2.sh` `los24-run.sh` `rescue-daemon.sh` `99-wlan-mars-v6.sh` `evening-los52.sh` `p4-verify.sh`
  `cleanup-mars-scripts.sh` `t.wav` …）。
- 本容器与 149 之间传文件用 `ssh 'cat > 远端' < 本地`（scp 在这条链路上不稳）；149 上跑后台任务要 `setsid nohup`。
- **连 149 的两条路**：① 同网段直连（手机在 149 附近时）；② **Tailscale 子网路由**：容器已开 `--accept-routes`
  （`tailscale debug prefs` 里 `RouteAll=True`），`192.168.1.0/24` 由节点 **`ziziclaw`(=家里 192.168.1.81 那台 Ubuntu)**
  宣告 ⇒ 直接 `ssh justin@192.168.1.149` 即可。
  ⚠️ **这条链路会时好时坏**（子网路由节点 ziziclaw 常年走 DERP 中继 hkg，RTT ~400-500ms）：
  2026-10-10 08:0x 时 `tailscale ping ziziclaw` 超时、家里所有设备 ping 都不通（但容器→ziziclaw 的 TCP 通），
  08:2x 又恢复（`pong ... via DERP(hkg) 517ms`，`ping 192.168.1.149` 0% 丢包）。
  ⇒ 判断"通不通"**优先用 TCP/ssh**（`ssh justin@192.168.1.149 true` 或
  `bash -c 'cat </dev/null >/dev/tcp/192.168.1.149/22'`）；ping 只能作参考。
  传大文件用 `ssh 'cat > 远端' < 本地`（高 RTT 下 scp 更慢）。
  ziziclaw 本身也可 SSH（`ssh justin@100.91.119.94`）去查子网路由（它 `AdvertiseRoutes=192.168.1.0/24`、`ip_forward=1`）。
- 手机 `/data/local/tmp/` 放脚本；`/data/adb/service.d/` 放开机脚本（APatch）。
- 推 GitHub 用 `scripts/ghpush.py <本地文件> <仓内路径> [msg]`（仓内路径不带 `gh/` 前缀，正好 2 个位置参数）。
- `workflow_dispatch` 不接受 commit sha → 用 `los_commit` 输入钉 LOS 提交（archive 方式取）。

## 目录

- `gh/` — CI 仓 `los.yml`（LOS 5.4.242 配方，唯一在用的 workflow）+ `patches/`：
  `container-opts.sh` `kabi-*.py` `ignore-vermagic.py` `mi_syms_los.c` `hwid-deexport.py` `wlan-block.py`
  `logdump.c` `moddbg.c` `cld-features.py`(CLO 特性集，附带) `wlan-profile.py` `wlan-debug.py`(诊断用)
- `work/keep-p3/` — **★ P3 保留镜像 + MANIFEST**（Image / boot img / modules / 开机 WLAN 脚本 / MD5SUMS；
  `MD5SUMS` 以 **149 KEEP 目录那份为准**，2026-10-10 曾发现仓库副本过期已同步；另有
  `99-wlan-mars-v7-candidate.sh` = v6 + 直接 insmod 原厂 `camera.ko`，待真机验证后启用）
- `work/p3-evidence/` — P3 验收证据（WiFi 截图、ds-check、final.log、wlan-boot.log）
- `work/compat-out/` — 离线符号兼容工具：`compat-matrix.py`（原始版）、**`device-gap.py`**（★ 只认真机
  `modules.load` + 自带 vermagic 归属校验，输出 missing / 与 vmlinux 撞名(致命) / 与我们 .ko 撞名(无害)）
- `docs/mars-handover-CHECKLIST.md` — 全部实验流水（§41.x 是 2026-10-09/10 的 WLAN 攻坚；§41.80~§41.82 是收尾）
- `scripts/` — 派发/推送/取证脚本；`scripts/149-*.sh` 是 149 侧工具的仓库留档副本
  （`149-post-recovery.sh`、`149-evening-run.sh`、`149-camera-try.sh`、`149-misc-diag.sh`、
  `149-stability-watch.sh`、`149-cleanup-mars-scripts.sh`、`149-restartpw.sh`）
- 149 上：`~/mars-keep/2026-10-10-tmp-archive/`（**所有 149 侧工具脚本**：`scripts-mars/`、`tools/`（`device-gap.py`
  + `Module.symvers-los52`）、日志 `logs-mars/`、证据 `evidence-mars/`、旧镜像 `images-old/`、另一台机 polaris 的
  `polaris/`、安装包 `apks/`）；`/tmp` 已清空（12K）

## 关键配方（当前 · 2026-10-19 · los104-apatch-bbr）

- **内核**：LineageOS `android_kernel_xiaomi_sm8350` `lineage-20`（5.4.242，tip `d42d2eb6c`）
  + 真机原厂 config `gh/configs/mars_factory.config` + 容器项（`container-opts.sh`）
- **必备开关**：`allbuiltin=1`（原厂 `=m` 全内建，USB/触屏/电池链才起得来）、
  `force_m=CNSS2,CNSS_GENL,WCNSS_MEM_PRE_ALLOC`、`force_y=CNSS_QCA6490`、
  `kabi=1`、`ignore_vermagic=1`、`mi_syms=1`、`hwid_deexport=1`、`logdump=1`、`wlanblock=1`、
  `mi_syms_audio=1`
- **BBR**：`extra_config` 末尾加 `BBR`（= `TCP_CONG_ADVANCED/BBR/FQ` + 默认 bbr）；不加则 los96 原样。
  断言：`CONFIG_TCP_CONG_BBR=y`、`CONFIG_DEFAULT_TCP_CONG="bbr"`、`CONFIG_NET_SCH_FQ=y`。
- **IPv6 NAT**：`CONFIG_IP6_NF_NAT=y` + `CONFIG_IP6_NF_TARGET_MASQUERADE=y`（Droidspaces 7.0 检查 ✅）。
- **Docker/nested**：`BRIDGE_NETFILTER`、`IP_SET/HASH_IP/HASH_NET`、`NETFILTER_XT_MATCH_ADDRTYPE/RECENT`、
  `NETFILTER_XT_SET`、`NETFILTER_XT_TARGET_LOG`、`NF_TABLES`、`TMPFS_XATTR/POSIX_ACL`、`CGROUP_NET_PRIO`，
  CI 断言。**Macvlan / CFS_BANDWIDTH 按用户要求不开**。
- **USB WiFi**：`WLAN_VENDOR_ATH/RALINK/REALTEK/MEDIATEK=y` +
  `ATH9K_HTC`/`CARL9170`/`RT2X00`+`RT2800USB`(含 `RT33XX/RT35XX/RT3573/RT53XX/RT55XX/UNKNOWN`)/`RT73USB`/
  `RTL8187`/`RTL8XXXU`(+`UNTESTED`)/`MT7601U`，`EEPROM_93CX6`/`CRC_ITU_T`；
  固件在 `gh/firmware/` 由 workflow `cp -a firmware/. kernel/firmware/` + `EXTRA_FIRMWARE` 内建。
  **RT5370 必须 `RT2800USB_RT53XX=y`**（漏了就只有 802.11b/g 之外的怪问题）。
- **root**：不加 `KSU` 标记 = APatch（当前默认）；`KSU` 标记 = 历史 v0.9.5 线，非默认。
- ⚠️ **千万别把 `CNSS_UTILS`/`ICNSS2` 塞进 `force_m`**（2026-10-10 §41.85 实测）：工厂表里它们是 `=y`、
  真机内核也是内建、`/vendor` 里那份 `5.4-gki/cnss_utils.ko` 在 P3 上 insmod 报 `invalid module format`，
  一旦变成 `=m` 就没有 `cnss_utils` 符号 ⇒ 原厂 `cnss2.ko` 装不上 ⇒ **WiFi 直接挂**。
  （历史 P3 之所以能用，是"缓存毒化"让它保持了 `=y`；曾因此产出 los52/54/55/56/57 五个带风险的候选，已降级/取消。）
- **候选增强（蓝牙，产物层已验证，待真机确认）**：`force_m` 再追加
  `SLIMBUS,SLIMBUS_MSM_NGD,BTFM_SLIM,MSM_BT_POWER`（工厂表里它们本是 `=m`，被 allbuiltin 翻成 `=y`
  ⇒ 真机 `slimbus.ko` 与 vmlinux 撞 44 个符号被拒、`bt_fm_slim.ko` 注册 `-16`）。
  当前有效候选：**los58**（P3 实际配置 + 固件内建，run `38012926791`）、
  **los59**（los58 + 蓝牙四项，run `38012935558`）。
  ⚠️ los52/los54/los55 因为 `CNSS_UTILS=m` **有 WiFi 风险，只作存档，别刷**（los56/los57 已 cancel）。
- **boot 打包**：原厂 `ref/boot-header.bin` + **无 recovery ramdisk**（本地
  `work/oneplus-kit/boot-ramdisk-norec.gz`，20,352,914 B；仓库 `ref/boot-ramdisk.gz` 是含 recovery 的版本）+ Image
  → `tools/make-bootimg.py`；刷机走 `flash-local.sh`（APatch kptools + dd 活动槽 + 回读校验）；
  通用刷机+计时+验收：`scripts-mars/flash-tag.sh <tag>`。
  los104 现成净版 boot 在 Release `los104-apatch-bbr` 与本地 `work/keep-los131-apatch-bbr/`；
  已打 APatch 11282 的版本刷机时现打（superkey 不入库）。
- **WLAN（关键）**：用**原厂** `cnss2.ko` + `qca_cld3_wlan.ko`，顺序见血泪坑；不要用我们自编的那套

## 手机侧开机脚本（★ 唯一一个，必须保留）

| 文件 | 作用 | 位置 |
|---|---|---|
| **`99-wlan-mars.sh` v6** | 开机后：去谷歌化 + 清 NO_INTERNET 永久禁用 + 按 CBC 顺序装**原厂 WLAN 栈** + 开 WiFi 等 IP；末尾附声卡体检 | 手机 `/data/adb/service.d/99-wlan-mars.sh`（755）；随镜像一起放在 `work/keep-p3/` 与 149 `KEEP/2026-10-10-P3-wifi-OK/` |
| `mars-wlan-prep.sh` | **早期实验遗留：用空 INI 盖住 `/vendor/firmware/wlan/qca_cld/wlan/`** | 已 `chmod -x` 禁用；**永远别再启用**（见 §3.3 of `docs/mars-wifi-epic.md`） |
| `post-fs-data.d/{01-mars-wifi-autoconnect,02-mars-nogoogle,99-mars-modules}.sh` | 2026-10-06/07 的实验遗留，功能已并入 v6 | 清理脚本 `~/mars-keep/2026-10-10-tmp-archive/scripts-mars/cleanup-mars-scripts.sh [--apply]`：移到手机 `/data/local/tmp/mars-old-scripts/`（**移动，不删除**；副本另存 `work/phone-scripts-backup/`） |

**清理的三条铁律**（脚本里已硬编码）：
1. `/data/adb/modules/**`（APatch 模块，**含 droidspaces**）绝对不碰；
2. 任何内容里出现 `droidspaces` 的脚本一律跳过；
3. 只处理点名的白名单文件，且是"移出装载路径"而非删除。

⇒ **换手机/重刷后唯一要做的事**：把 `work/keep-p3/99-wlan-mars.sh` 放到
`/data/adb/service.d/` 并 `chmod 755`。没有它 ⇒ 没有 WiFi（内核门禁挡住原厂栈、且必须等 CBC 后才能装）。

## 血泪坑

- **WLAN 总开关是 INI**：`/vendor/firmware/wlan/qca_cld/wlan/` 一旦被脚本用 tmpfs + 空白 ini 盖住
  ⇒ 原厂驱动 probe 必失败（曾误判成 "ABI 不兼容"，浪费两天）。**别启用 `mars-wlan-prep.sh`**。
- **CBC 顺序**：`qca_cld3_wlan.ko` 必须在 `fs_ready`→`Calibration completed successfully` 之后 insmod，
  否则原厂 cnss2 直接 `-EPERM`（"Reject WLAN Driver insmod before CBC"）。
- **service.d 里的 `svc`** 是 APatch BusyBox 的 runsv 命令 ⇒ 开 WiFi 必须写 `/system/bin/svc wifi enable`。
- **qcacld 日志不进 console**（QDF 日志），排查要自己插 `pr_err`（见 `patches/wlan-debug.py`）；
  `qdf_status_to_os_return()` 对未映射状态一律返回 `-EPERM`（所以 `err = -1` 不代表真是权限问题）。
- 白名单过严会拦 `dwc3`/`phy_msm_ssusb_qmp` ⇒ USB gadget `-19`，无 adb
- `get_hw_*` 去导出后内建 hwid 占名但不给符号 ⇒ fts_touch 拿不到 `get_hw_id_value` ⇒ 无触屏
- 电池 probe 比原厂晚 ~6s ⇒ 必须 dummy-psy 兜底 init 的 5s wait
- `set_active b` 会从错误槽启动（我们镜像在 `boot_a`）
- `fastboot flash` 报 `waiting for any device` = **没刷上**，别当成功
- `screencap` 全黑不可信；判进系统用 `boot_completed=1` + 核对 `/proc/version`
- 门禁打开 + MIUI 早期装原厂栈 = 大概率开不了机（要人工进 fastboot）；日常用 `wlanblock=1` + 开机脚本。
  **2026-10-10 实证**：los48（`wlanblock=0` + `firmware_embed=1` + 音频桩）刷入后手机从 USB/WiFi/fastboot
  全部消失（卡死），要用户手动进 fastboot 才救得回来 ⇒ **不要再尝试去门禁**（除非做二分且用户在场）。
- 卡死救援（149 上常驻）：`~/mars-keep/2026-10-10-tmp-archive/scripts-mars/rescue-daemon.sh` 一见 fastboot 就自动刷回 P3 已验证镜像
  (md5 `663ce79e…`) 并装 v6 开机脚本(`99-wlan-mars.sh`)；日志同目录 `logs-mars/rescue-p3.log`。
  （2026-10-10 已把 149 的 `/tmp` 清空: 全部工具/日志/证据归档到 `~/mars-keep/2026-10-10-tmp-archive/`, 见其 `scripts-mars/`。）
- **判"这套 .ko 是不是真机的"只看 vermagic**：真机 = `5.4.233-qgki-gbb70cde46897`（main）/ `5.4.233-gbb70cde46897`（5.4-gki）。
  `work/repack/rootfs/vendor/lib/modules` 与 `work/vb/rootfs/lib/modules` 里**混着 `5.4.233-qgki`（无哈希）的非真机模块**
  （`camera.ko` 就在里面，它引用 8 个 `debugfs_*`，而真机核 DEBUG_FS=n）⇒ 2026-10-10 用错集合差点得出"缺 debugfs"的错误结论。
  真机反证：`work/baseline-stock/dmesg.txt` 有 `CAM_WARN: … DebugFS not enabled in kernel!`，而 `lsmod.txt` 里 `camera`(被 27 个模块依赖)/
  `mbhc_dlkm`/`swr_ctrl_dlkm`/`wcd938x_slave_dlkm` **全都装载成功**；真机 main 目录模块在我们核上 `insmod rc=0`。
  ⇒ **做"我方缺哪些符号"的分析前先验 vermagic**，或只用 `adb pull` 自真机 + 真机 `lsmod` 记录过的模块集。
- **晚间/远程自动化（149 上已挂好）**：`scripts-mars/post-recovery.sh`（等 adb 上线 ≤24h：拉**真机** `/vendor/lib/modules`+md5 存档、
  电话体检、声卡/WiFi/容器体检、缺符号速览）、`scripts-mars/evening-run.sh [--no-flash] [--cleanup-apply]`
  （刷 **los58**/`--tag los59` + 音频/声卡核对 + 相机尝试 + 蓝牙 + 其它项 + 清理 + 模块缺口/差集 + 自动判定；证据落 `evidence-mars/<ts>-evening/`）。
  ⚠️ 在 149 上 `pkill -f 某个 .sh` 时，**同一条命令行里不要再出现该 .sh 的明文路径**（会连自己一起杀）→ 用独立小脚本（如 `restartpw.sh`）。


## ⚠️ 槽位陷阱（2026-10-04 血泪教训）

**手机活动槽常为 `_b`，但 `flash-any.sh`/`tight-flash.sh` 历史写的是 `boot_a`！**
这导致「刷了自编内核却一直跑原厂」的假阳性，浪费多轮。

**每次刷机后必须核对**：
```bash
adb shell 'getprop ro.boot.slot_suffix; cat /proc/version'
```
- 原厂：`builder@pangu-build-component-vendor-...` + `Wed Dec 20 08:12:00 UTC 2023`
- 自编：`runner@runnervma...` + `2026` 年日期

**刷法**：
- 刷到**活动槽**（当前 `_a`），或
- `set_active` 切到你刷的那个槽
- **救机**：stock 已在 `boot_a` 时，只需 `fastboot set_active a` + reboot，**不用重刷**

**镜像**（当前）：
- **los104 基线**：`work/keep-los131-apatch-bbr/boot-Image-los104-apatch-bbr.img`
 （净版，md5 `09898855…`；当前手机用 APatch 11282 打补丁后运行 #30）
- **los103 回退（已打 APatch 11282）**：`work/keep-los129-apatch-bbr/boot-Image-los103-apatch-bbr-APatch11282.img`（md5 `e3aac555…`；AVB footer warning，但实测启动）
- **los103 净版**：`work/keep-los129-apatch-bbr/boot-Image-los103-apatch-bbr.img`（md5 `c4b8171d…`）
- **los102 回退**：`work/keep-los128-apatch-bbr/boot-Image-los102-apatch-bbr.img`（md5 `85ab08c3…`）
- **los101 回退**：`work/keep-los126-apatch-bbr/boot-Image-los126-apatch-bbr-APatch.img`（md5 `a43083b5…`）
- **los102 刷前备份**：`work/backups/boot_a-los102-apatch11282-backup-20261019.img`（192MB，md5 `99d81c33…`）
- **los101 刷前备份**：`work/backups/boot_a-los101-backup-20261019.img`（192MB，md5 `f48477ea…`）
- **KSU 备份**：`work/backups/boot_a-los100-ksu-backup-20261019.img`（192MB，md5 `a0ae428e…`）
- 原厂 GOLD：`~/mars/eng/builds/apatch-patched-boot-0.13.3.img`（md5 `8fcf3576…`）/
  `work/boot_a-stock-69m.img`（md5 `58916775…`，分区前 72MB）

## 常用命令（当前流程：mars 直插一加 USB，本容器直连）

```bash
# 0) USB 直连(缺节点先跑 usb-link-setup.sh; WiFi 备用 adb -s 192.168.43.246:5555)
bash scripts/usb-link-setup.sh
A='adb -s d6fba222'
$A shell "getprop sys.boot_completed; cat /proc/version"

# 旧流程(2026-10-13 前, 手机在 149 上) — 保留备查: 所有手机操作都经 149
S='ssh -o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=no \
   -o UserKnownHostsFile=/dev/null justin@192.168.1.149'

# 1) 看手机状态
$S 'adb devices -l; adb shell "getprop sys.boot_completed; cat /proc/version; ip addr show wlan0 | grep inet"'

# 2) 刷自编/保留镜像（149 上；自动 APatch + dd 活动槽 + 回读校验 + reboot）
$S 'bash ~/mars-keep/2026-10-10-tmp-archive/scripts-mars/flash-local.sh \
     /home/justin/mars-build/KEEP/2026-10-10-P3-wifi-OK/boot-Image-mars-P3-5.4.242.img 663ce79ea3aa5e308d4b4b026730b0fb'

# 3) 救机（手机进 fastboot 后）
$S 'fastboot flash boot_a /home/justin/mars/eng/builds/apatch-patched-boot-0.13.3.img && fastboot reboot'

# 4) 验收
$S 'bash ~/mars-keep/2026-10-10-tmp-archive/scripts-mars/acceptance2.sh'   # 身份/WiFi/触屏/容器项/ds-check/容器 + 截图
$S 'adb shell "su -c /data/local/tmp/droidspaces check"'

# 5) 派发新编译（本容器）
scripts/dispatch-los104.sh main        # 或 apatch-bbr（los104 源码分支）
nohup bash /tmp/losw/dl-run-all.sh <run_id> <tag> > /tmp/dl-<tag>.log 2>&1 &   # 产物拉取(临时脚本, 可选)
```
