> 🚩 **接手收尾工作请先读 [`docs/mars-NEXT-HANDOVER.md`](docs/mars-NEXT-HANDOVER.md)**（2026-10-10 10:30 交接快照：目标/现状/镜像矩阵/一条命令流程/已证伪假设/判据）。

# VERSIONS.md —— 自编内核镜像「血缘表」

> **权威文档**。每刷一个镜像加一行。证据等级：`[目]` 目视 / `[log]` logdump / `[adb]` / `[?]` 推断。

---

## ★★★★ 2026-10-04 P1 里程碑：**首次进入 MIUI**（后续一切工作的基线）

### 基线镜像（保留，勿覆盖）

| 镜像 | md5 | 说明 |
|---|---|---|
| **`work/repack/boot-p1-allowlist.img`** | `e640d079…` | **★ 进 MIUI 基线**：dummy-psy + 模块白名单(仅 msm_drm+触屏链) + FTS=mod + hwid 去导出 + fw-timeout 1s |
| `work/repack/boot-p1-usb-touch.img` | `c73a1feb…` | 待验证：白名单改为**只拦 WLAN** + 恢复 `get_hw_*` 导出 + cmdline `androidboot.usb.config=adb` |
| `work/boot_a-stock-69m.img` | `58916775…` | 原厂+APatch root，救机（~4s 刷完） |

### 进 MIUI 时的实测状态

| 项 | 状态 | 证据 |
|---|---|---|
| 启动到 MIUI 桌面 | ✅ | `[目]` 用户确认 |
| 电量显示 80% | ✅（dummy-psy 占位） | `[目]` |
| 触屏 | ❌ 无效 | `[目]`（fts_touch_spi_k2 未 probe 成功） |
| WiFi | ❌ | 白名单拦了 WLAN |
| USB adb | ❌ | `configfs-gadget ... failed to start g1: -19` |
| root | ✅ APatch | `[adb]` |

### 从 MIUI 版深挖出的三个根因（都已修在 usb-touch 版里）

1. **USB gadget -19**：白名单把 `dwc3`/`phy_msm_ssusb_qmp`/`xhci_hcd` 也拦了 ⇒ UDC 未就绪
2. **触屏无事件**：`get_hw_*` 去导出后，内建 hwid 占名但不给符号 ⇒ fts 拿不到 `get_hw_id_value`
3. **假阳性误判**：`fastboot flash` 失败后 reboot 仍是原厂，脚本 `boot_completed=1` 不代表刷成功
   → **必须核对 `/proc/version` 编译时间 + `CONFIG_MODVERSIONS` + cmdline**

### P1 累计已解决（不要重做）

| 根因 | 修法 | 落点 |
|---|---|---|
| FTS 内建在 kernel_init 等固件 60s | 保持 `=m` | `m2y.py` KEEP |
| `hwid` 9 个 `get_hw_*` 与内核导出撞名 | 去导出（后又恢复，见上） | `build.yml` NAMES |
| 电池 probe 晚于 init 5s wait | **dummy-psy** 早期注册 power_supply | `patches/dummy-psy.c` |
| vendor_modprobe exec 挂 52s | **模块黑名单/白名单** + fw-timeout 1s | `patches/mod-blacklist.py` + `fw-timeout.py` |
| struct module ABI 偏移 | `-d DYNAMIC_FTRACE -d FTRACE_MCOUNT_RECORD` | 已有 |
| 43 符号撞名 msm_drm | 去导出 | 已有 |


### 2026-10-04 补充：usb-touch 版实测

`boot-p1-usb-touch.img`（`c73a1feb…`）刷入后 **112s 进 fastboot**，未到桌面。
（白名单只拦 WLAN + get_hw 导出恢复 + usb cmdline 都已含，但仍失败。）
**手机已刷回原厂+root。**

→ 下一步深挖：读该版 logdump（`work/p1-logs/`），对照 MIUI 基线（`e640d079`）的差异
  （恢复 get_hw 导出 / 放行更多模块 是否引入新死锁）。


### 2026-10-04 log diff：usb-touch 失败根因 + 触屏撞名

**usb-touch 版仍 `skip dwc3/phy_msm_ssusb_qmp/xhci_hcd`** ⇒ 旧「白名单」逻辑残留
（`mars_mod_allow` 为空 ⇒ 无差别拒绝一切）⇒ USB gadget -19。已重写为**只拦 WLAN**。

**触屏撞名（allowlist 基线 log p1m32）**：
```
xiaomi_touch: exports duplicate symbol copy_touch_rawdata (owned by kernel)
mi_thermal_interface: Unknown symbol thermal_class / thermal_message_dev
```
⇒ `xiaomi_touch.ko` 被拒装 ⇒ 无触屏。与 `get_hw_*`/`msm_drm` 43 符号同类问题。
下一增量：去导出 `copy_touch_rawdata`（及 thermal_class 等）。


### 2026-10-04 补充2：wlanblock 版（只拦 WLAN）仍 104s 进 fastboot

`boot-p1-wlanblock.img`（`a020bce3…`）= 修复黑名单函数（只拦 WLAN）+ get_hw 导出恢复 + usb cmdline。
仍未到桌面。手机已刷回原厂。

**已排除**：黑名单无差别拒绝一切（已修）、FTS kernel_init 挂死（已修）、hwid 撞名（部分）。

**待查**：与 MIUI 基线（`e640d079`，只放行 msm_drm+触屏）的剩余差异 ——
可能「放行太多模块」本身就会挂（vendor_modprobe exec 被某个新放入的模块拖住）。

**下一步建议**：回到 MIUI 基线配方，**只加一项**：
1. 先只加 `get_hw_*` 导出恢复（为触屏），不动模块集合
2. 再加 USB 相关模块放行（dwc3 等）
3. 再加 xiaomi_touch 的 `copy_touch_rawdata` 去导出


### 2026-10-04 inc2 log 结论 + inc3 修正

inc2（copy_touch_rawdata 去导出）仍无触屏。log 实锤：
```
hwid: exports duplicate symbol get_hw_build_adc (owned by kernel)   ← hwid.ko 被拒
fts_touch 全程 0 次出现                                              ← 依赖 hwid，装不上
xiaomi_touch_probe 成功 + 大量 ioctl                                 ← 框架在，硬件不在
touch_avddsource_vreg: disabling (31.7s)                             ← 触摸供电被关
```

**inc1「恢复 get_hw 导出」是反效果**：内核导出 get_hw_* ⇒ 与 hwid.ko 撞名 ⇒ hwid 装不上 ⇒ fts 无符号。

**inc3 修正**：get_hw_* 重新去导出 + 保留 copy_touch_rawdata 去导出 = MIUI 基线 + 仅多一项触屏撞名修复。


### 2026-10-04 touch-diag 实锤：xiaomi_touch 撞名 5 个符号

诊断（`/data/local/tmp/touch-diag/`）两份对比：
- 早期：`xiaomi_touch: exports duplicate symbol get_xiaomi_touch_class (owned by kernel)`
  + fts 缺 `last_touch_events_collect/update_fod_press_status/copy_touch_rawdata/product_name_get/get_hw_version_*`
- 后期：fts/hwid/xiaomi_touch **全部装载成功**（event0–4 有），但太晚/不稳

**内核与 xiaomi_touch.ko 撞名 5 个**：`get_xiaomi_touch_class` `update_clicktouch_raw`
`update_touch_rawdata` `get_xiaomi_touch_dev` `xiaomitouch_register_modedata`

**inc4**：全部去导出（+ 已有 get_hw_* / copy_touch_rawdata 去导出）。

**日志保存方法**：进系统无触屏 → **立刻关机**，保 32MB 冷拷贝；诊断写 `/data/local/tmp` 不受 dmesg 覆盖。


### 2026-10-04 touch-diag 终极发现：xiaomi_touch 还有 3 个撞名

诊断实锤（`/data/local/tmp/touch-diag/`）：
```
xiaomi_touch: exports duplicate symbol update_palm_sensor_value (owned by kernel)
```
fts 因此缺 `copy_touch_rawdata/get_xiaomi_touch_class/update_*` 等 10 个符号。

**内核与 xiaomi_touch.ko 全部撞名清单（8 个）**：
get_xiaomi_touch_class, update_clicktouch_raw, update_touch_rawdata,
get_xiaomi_touch_dev, xiaomitouch_register_modedata,
**update_palm_sensor_value, update_prox_sensor_value, xiaomi_touch_set_suspend_state**

前 5 个已去导出（inc4/5）；后 3 个 inc6 处理。

**关键**：15:25 日志显示模块**最终能装上**且 `/dev/input/event4: fts` 存在！
⇒ 触屏设备已注册，可能是首次失败后重试成功，或 probe 后无中断。

**USB**：UDC `a600000.dwc3` 在但 `state=not attached` ⇒ gadget 未绑定（独立问题）。


### ⚠️ 2026-10-04 事故记录：原厂镜像也启动失败

- `boot_a-stock-69m.img`（md5 `58916775…` 校验正确）刷入后**反复重启**，最终进 recovery
- 尝试：192MB `boot_a-stock-safe.img` 刷双槽（**该文件疑为整分区 dump，非合法 boot.img**）+ 69MB 干净 erase 后刷 → 仍未启动
- **数据不重要**（只有照片）→ recovery 清数据 / 官方线刷包恢复
- **教训**：
  1. `boot_a-stock-safe.img`（192MB）**不要用 fastboot flash boot**——只用 69MB 版
  2. 双槽都刷 / 频繁 set_active 可能与 ABL 状态冲突
  3. 原厂救机镜像在**多次使用后仍可能失效**，需准备官方线刷包兜底


### 2026-10-04 救回后：新 IP + 用户要求

- 手机经官方线刷救回，**数据已清**
- 新 WiFi IP：**`192.168.1.4:5555`**（已入 dev-pick.sh）
- MIUI 要求登录小米账号 + 插 SIM 才允许 USB 安装 ⇒ 用户烦躁
- **用户要求 root 后**：
  1. 关掉 USB 安装限制 / MIUI 优化 / 账号强制
  2. 精简系统应用（广告、账号、预装）
- 下一步：装 APatch → 继续触屏/USB 内核


### 2026-10-04 备份对比 + 系统状态

- 手机经用户线刷+清数据救回，当前内核 = **完整 boot 分区 dump**
  `boot-current-clean.img`（201MB, md5 `b56303df…`）= `boot_a-stock-safe.img`
- **前 72MB 与 `boot_a-stock-69m.img` 逐字节一致** ⇒ 同一内核，69m 可继续用于 tight-flash
- **原厂已有 root + APatch**（`/data/adb/ap`）
- **MIUI 精简已完成**：20+ 系统应用卸载/禁用，安装限制关闭
- 新 IP：`192.168.1.4:5555`

### 下一步（基于 usb-touch 版继续）

1. 刷 `boot-p1-usb-touch.img`，核对内核身份三项
2. 验 USB adb / 触屏 getevent
3. 若 USB 仍 -19：查 `phy_msm_ssusb_qmp`/`dwc3` 是否真的加载（白名单已放行）
4. 若触屏仍无效：查 fts_probe 是否成功、固件是否缺失
5. 稳定后放行 WLAN（cnss2/qca_cld3_wlan）→ Droidspaces 验收（USER_NS 等）

---

## ★★★ 2026-10-04 P1 第四轮：电池已通，新卡点 = vendor_modprobe exec 被固件请求挂死 52s

**已解决**（hwid 去导出 + FTS 不内建）：
- `hwid`/`qti_battery_charger_main`/`fts_touch`/`xiaomi_touch` 全部装载成功
- `power_supply` = battery/usb/wireless，`healthd: battery l=74` 正常读数
- pmic_glink 子设备（battery_charger/altmode/ucsi）在 ~16s 创建并绑定

**新根因**（logdump p1e-full.bin）：
```
54.84s  init: Exec service is hung? Waited 52.5764 without SIGCHLD
```
`init.target.rc` 里 `exec vendor_modprobe.sh` / `exec modprobe 音频模块` 在 ~2s 启动后
被某模块的 `request_firmware` 用户态回退（60s 超时）挂住 ⇒ init 等 52s ⇒ 关机。
（FTS 改 =m 只是把固件死等从 kernel_init 挪到了 vendor_modprobe exec。）

**修法（已派发）**：`fw-timeout.py` 固件回退超时 60→**2 秒**（GPU 固件已 EXTRA_FIRMWARE 内嵌，
不走回退）。CI 步骤改为应用该补丁并断言 =2s。

## ★★★ 2026-10-03 P1 第三轮：hwid 装载失败根因 = `get_hw_*` 导出撞名

**实锤**（`/data/local/tmp/hwid-diag/boot-*.log`，自编内核 post-fs-data）：
```
hwid: exports duplicate symbol get_hw_build_adc (owned by kernel)
Failed to load module hwid
Failed to load module qti_battery_charger_main
Failed to load module fts_touch_spi_k2
```
`verify_exported_symbols()` 拒装 —— 与 msm_drm 的 43 符号撞名**同一类问题**。

**撞名集合**（hwid.ko 的导出 ∩ 内核导出，共 9 个）：
`get_hw_build_adc` `get_hw_id_value` `get_hw_country_version` `get_hw_project_adc`
`get_hw_version_build` `get_hw_version_major` `get_hw_version_minor` `get_hw_version_platform`
`product_name_get`

内核（MiCode 树）自带这些符号的导出；hwid.ko 也导出它们 ⇒ 被拒。
下游：`qti_battery_charger_main`（依赖 hwid+msm_drm）、`fts_touch_spi_k2`/`xiaomi_touch`/`cyttsp5*`
（依赖 hwid+msm_drm）全部装不上 ⇒ 无电池/触摸 ⇒ healthd 无电池 ⇒ 约 15s 关机。

**修法（已派发 CI 37135790347）**：`build.yml` 去导出名单加入这 9 个符号（43+9）。

**顺带结论**：
- APatch/Zygisk 在自编内核上正常（KP/apd/zn-daemon 均有日志）✓
- mars-nowlan overlay **未生效**（`no overlay mounts`）—— 与 stock vendor_modprobe 相同；
  但本阶段先修撞名，overlay 可后置
- 诊断脚本必须用文件推送写入，不能在 `adb shell '...'` 里带 `$`（会被外层展开）

## ★★★ 2026-10-03 P1 第二轮：FTS 已修，新卡点 = 电池模块未加载 → healthd 无电池 → 约 15s 关机

**已验证修复**：FTS 保持 `=m` 后，内核 initcall 不再卡死；系统进 init/服务/compositor
（msm_drm 已 Live，`mi_disp` 事件、亮度设置均出现 `[msm_drm]`）。

**新现场**（`work/p1-logs/p1b-head.bin`）：
```
11.7s  healthd: No battery devices found / battery none
12.9s  init: wait /sys/class/power_supply/usb/type timed out (init.mi_thermald.rc)
12.9s  android.hardware.health@2.1 not found
15.1s  composer lastclose + modem SSR → Received stop shutdown interrupt from modem
17s    init Unmounting /data → 21s sysrq Kill All Tasks
```
`Modules linked in` 有 `msm_drm`，但 **没有** `hwid` / `qti_battery_charger_main` /
`fts_touch_spi_k2` / `xiaomi_touch`（它们都依赖 msm_drm，见 `modules.dep`）。
原厂上 `modprobe hwid` 可正常装入（带 `hwid_value=...` 参数）。

**待查/下一增量**：
1. 为何 `hwid.ko` / `qti_battery_charger_main.ko` 在自编内核上没装上（符号? vermagic? 依赖时序? probe?）；
2. 次要：`ipa_fmwk`/`qmi_helpers` vermagic 少 `qgki-` 前缀被拒（5.4-gki 系）；
3. 兜底：若电池短时间装不上，需阻止「无电池 → 关机」路径。

**本轮镜像**：`work/repack/boot-p1-ftsmod.img`（md5 `256410e9…`）= CI run 37131577741 + APatch kptools。
手机已刷回原厂+root（`work/boot_a-stock-69m.img`）。

## ★★★ 2026-10-03 P1 根因（sde59 logdump 实锤）：内建 FTS 触摸在 kernel_init 里等固件

**现场**（`work/p1-logs/ld-head.bin`，uptime 77~84s，swapper/0 = kernel_init）：
```
fts_driver_init → fts_probe → fts_fw_update → getFWdata
  → request_firmware → firmware_fallback_sysfs
  → wait_for_completion_killable_timeout     ← 在 kernel_init 阶段等用户态喂固件
```
用户态尚未启动 ⇒ 永远等不到 firmware helper ⇒ **整机卡死在内核 initcall**，
LOGO 后黑屏循环 / 看门狗复位。`CONFIG_TOUCHSCREEN_ST_FTS_V521_SPI=y`（被 m2y 翻成内建）
+ `CONFIG_FW_LOADER_USER_HELPER_FALLBACK=y` 是组合根因。

**旁证**（`work/p1-logs/ld-32m.bin`）：`msm_drm: module is already loaded`（L1 内建占用模块名）、
`cnss: Failed to register MSM PCI event (-19)` / `Failed to probe PCI driver`（WLAN 仍废，但不致命）。

**修法（P1 增量，已派发）**：`m2y.py` 的 `KEEP` 加入 `CONFIG_TOUCHSCREEN_ST_FTS`（保持 `=m`），
让 probe 推迟到模块加载、`/vendor/firmware` 可读之后。CI run **37131577741**。

**方法论**：
- **任何「内建驱动 probe 时 request_firmware」都会在 kernel_init 里死等**——GPU A660 已踩过（EXTRA_FIRMWARE），
  触摸同理。新增内建驱动前先查 `request_firmware`。
- Magisk `boot_patch.sh` 会**重打包 ramdisk + 改内核** ⇒ 破坏原厂 ramdisk 必砖；
  APatch `kptools -p` **只改内核**，ramdisk 可保持逐字节一致（已验证 md5）。
- 冷拷贝 `dd skip=32MB` 在刷回原厂后仍可读 → 卡死现场留痕的可靠手段。

# VERSIONS.md —— 自编内核镜像「血缘表」

> 目的：**后来的人一眼看懂"有哪些镜像、各自什么配方、走到哪一步、什么问题、为什么留/废"**。
> 规则：**每刷一个镜像就加一行**（用 `scripts/record-image.sh` 自动填 md5/大小/时间）。
>
> 证据等级（很重要，别把猜测当结论）：
> - `[目]` 用户目视（屏幕现象）
> - `[log]` 设备侧落盘日志（sde59 logdump）
> - `[adb]` 进系统后 adb 读取（boot_completed / /proc/modules / dumpsys）
> - `[§]` TAKEOVER.md 里的既有记录
> - `[?]` 未验证 / 推断

---

## ★ 本次任务的最初目的（先看这里）

> **用户原话（2026-10-02 立项目标）**
> 「目标一直是**编译成功 mars 内核,能全面符合 droidspaces 对内核的要求**。该让我手动参与的就参与。
>   请紧盯着终极目标,一个一个排查出启动过程的阻碍项。我有时间和耐心。」
>
> **用户原话（更早的立项描述）**
> 为 Xiaomi 11 Pro（mars / SM8350 / MIUI 14 / Android 13，原厂内核 `5.4.233-qgki-gbb70cde46897`）
> 构建一个**支持 Droidspaces/容器**、并且**能在真机上正常启动**的内核。

### 验收标准（可判定，四个都要成立）

| # | 标准 | 判定方式 | 现状 |
|---|---|---|---|
| 1 | **编译成功**，且**只在 GitHub Actions 上编译**（本地不编译）| CI run 绿色 + 产物 `boot-*.img` | ✅ 已达成（多次）|
| 2 | 刷入 `boot_a` 后**能正常开机**到 MIUI 桌面 | 用户目视桌面 **或** `boot_completed=1` | ⏳ **尚未达成**（当前卡在 LOGO 阶段）|
| 3 | 内核配置**全面符合 Droidspaces 要求** | 见 §3 的"核心要件"断言（命名空间/cgroup/SYSVIPC/POSIX_MQUEUE/OVERLAY_FS/VETH/容器网络…）| 🟡 要件已基本齐备（含今天补齐的 `MAC80211`/`MACVLAN`/`IPVLAN`/`VXLAN`/`NF_TABLES`），**待真机验证** |
| 4 | **手机永远可恢复**（只改 `boot_a`；其余分区原厂）| 刷 `work/boot_a-stock-69m.img`(md5 `58916775…`) 即完全恢复 | ✅ 全程遵守，已多次验证 |

### 工作方式约定（用户要求）

- 只用**中文**回复；**证据优先**，不许把推断当结论（本文件每条结论都标证据等级）；
- **只在 Actions 编译**；刷机走容器 → USB 直连（`adb` 推入 + `dd` + **回读校验**）或 fastboot；
- 该让用户手动参与的就参与（按 `电源+音量下` 进 fastboot、目视屏幕现象）；
- **一次只排查一个阻碍项**，每项都要有可复现的证据（`VERSIONS.md` §6.4 的 tag 二分法）；
- 任何时刻手机必须可用（失败就刷回原厂）。

---

## ★★ 2026-10-03 战略决策（先读，再动手）

> **定案：主路线改为「自包含 Allbuiltin-Hybrid + KernelSU」；raw 线降级为存档。**

### 为什么放弃 raw 线

raw 线 = 公开树 `MiCode/star-r-oss`（A11）编内核 + 加载 **小米内部 5.4.233 原厂 `.ko`**。
两者**不是同一棵源码树** ⇒ genksyms CRC / `struct module` 布局 / 导出集合都可能不一致。
已修：ABI 偏移、vermagic、MIUI 符号桩、43 撞名、模块名占用…… **每修一层露一层**。
小米 **未公开** 5.4.233-qgki 内部树 ⇒ 这条路线 **结构性不可收敛**（14 个镜像仍卡 LOGO）。

### 为什么 Allbuiltin-Hybrid 可收敛

1. **L1 `star-stock`（62 项 =m→=y）已进过 MIUI**：35.5s `boot_complete`，触摸/显示/RIL 正常
   （§70 / 血缘表 #1）——证明这棵树能驱动硬件；
2. L1 未交付的原因是**有界问题**：同名 `.ko` 重复注册（`qcom_llcc_perfmon` 等，**不只 WLAN**）
   + `init.target.rc` 的 `modprobe qca_cld3_wlan` 挂死占 `module_mutex`（§71）；
3. techpack（display/camera/audio/rmnet）在树内，硬编码 `obj-m` ⇒ **同树自编 .ko** 与内核
   同批编译，ABI 天然一致 ⇒ 不必啃原厂二进制；
4. Droidspaces 官方 **推荐 KernelSU**（APatch/Magisk 需 Daemon Mode）。

### 目标形态

```
内核本体   : 能 =y 的全部内建（L1）
techpack   : 同树自编 .ko，Magisk/KSU overlay 安装
原厂 .ko   : 【完全不加载】（不是“少依赖”——只要还装 stock .ko，module_mutex/ABI 风险仍在）
root       : KernelSU（allbuiltin-ksu）
WLAN       : Phase1 失效化，Phase5 专项恢复（不阻塞验收）
```

### 阶段与 Go/No-Go

| 阶段 | 内容 | Go |
|---|---|---|
| **P1** | allbuiltin + 黑名单 overlay（复用 `overlay/`）+ WLAN fail-fast | `boot_completed=1` + 10 分钟不复位 |
| **P2** | techpack 同树自编 .ko（显示链优先） | 显示/触摸/充电 Live，`/proc/modules` 为我们的 .ko |
| **P3** | Droidspaces 验收（`verify-droidspaces.sh` + `droidspaces check` + Alpine/Ubuntu systemd） | 全绿 = **项目验收达成** |
| **P4** | KernelSU 正式化（`allbuiltin-ksu`） | `su` 可用；P3 复跑 |
| **P5** | WiFi/相机/音频/NetHunter | 按依赖链逐项 |

**No-Go 一律 `scripts/tight-flash.sh` 刷回 `work/boot_a-stock-69m.img`，按 tag 回退最后一项。**

### STOP（明确不做）

- raw 线当主线；为装 stock `.ko` 追 CRC/layout/43 撞名/FTRACE 偏移
- `fw-timeout` 60→5s、`FW_LOADER_FALLBACK=n`、logdump 写盘风暴、`auto_fastboot`
- 只禁 WLAN 单独扛；只改 `modules.load` 当主路（显式 `modprobe` 不读它）
- 改 boot 头 576..608；本地编译；无日志下结论

### 派发参数（主线，必须显式传）

```
upstream=https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git
upstream_branch=star-r-oss
variants=star-stock          # 或 star-stock-ksu
toolchain=aosp-clang-11
```

### 这条主线走过的路（"一个一个排查阻碍项"的实际顺序）

```
原始目标：能开机 + 满足 Droidspaces
  ↓ ① 编译能过（补 .gitignore 误伤的文件、修 nl80211hdr_put 重名…）
  ↓ ② 模块装载（MIUI 私有符号桩、vermagic、MODVERSIONS）
  ↓ ③ 每 2~3 分钟硬复位（PMIC 看门狗 / longpress / SSR panic 链）
  ↓ ④ GPU 起不来 ⇒ surfaceflinger 自杀（KGSL VK_DEVICE_ID、A660 固件时序）
  ↓ ⑤ 卡死在 LOGO：模块加载死锁（raw 线）
       真因A: struct module 字段偏移（FTRACE_MCOUNT_RECORD）
       真因B: 43 符号与 vendor msm_drm.ko 撞名
  ↓ ⑥ 战略改道（见上「2026-10-03 战略决策」）：
       放弃 raw 线，改走 Allbuiltin-Hybrid（L1 为基线 + 中和重复注册）
  ↓ ⑦ 当前：P1（L1 + 黑名单 overlay + WLAN fail-fast）← 就在这里
```

---

## 0. 设备与环境基线

| 项 | 值 |
|---|---|
| 设备 | Xiaomi 11 Pro (`mars`) / `mars_eea`，Android 13 / MIUI `V14.0.7.0.TKAEUXM` |
| 原厂内核 | `5.4.233-qgki-gbb70cde46897` |
| 分区 | `boot_a=sde12`、`boot_b=sde37`、`vendor_boot_a=sde23`、`logdump=sde59`(64MB) |
| 只改 boot_a | ✓ 其余原厂 ⇒ 刷 69MB 原厂 `work/boot_a-stock-69m.img`(md5 `58916775a913a818cd12db6ac0908fec`) 即完全恢复 |
| **原厂镜像(带 root)** | `work/rollback/boot_a-stock-safe.img` = 192MB, md5 **`b56303df06631c1ac67d0c52f9ad0d36`** = **原厂内核 + APatch root** ✓ |
| 原厂镜像(快速刷入版) | `work/boot_a-stock-69m.img` = 上面那份的**前 69MB**(前缀 md5 实测一致 `58916775…`) ⇒ ~4 秒刷完,**同样保留 root** ✓ |
| ⚠️ root 的机理 | APatch 的补丁**在 `boot_a` 里** ⇒ 刷我们的自编内核会**暂时失去 root**(补丁被覆盖); 刷回上面任一份即恢复 root ✓。想"自编内核也带 root"有两条路: ①用 APatch 应用重新 patch 我们的 boot.img; ②让 CI 出 `ksu=1` 版(内置 KernelSU) |
| 刷机链 | 容器 → USB 直连(手机插一加 12)：`adb push`≈25MB/s、`dd` 0.2s、回读校验；fastboot 也在容器里可用 |
| 网络 | 家里 WiFi `192.168.1.114:5555`（热点时 `192.168.43.119`）——脚本已自动选路 |
| 服务器 | 容器 `192.168.1.81`（tailscale `100.124.119.49`） |

---

## 1. 镜像血缘表（按时间）

| # | 镜像 | md5 | 构建时间 | 来源(run/提交/变体) | 刷入实测 | 走到哪一步 | 外设 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 1 | `work/artifacts/run-36993922435/boot-star-stock.img` | `4199ac89` | 10-02 18:09 | run 36993922435 / `star-stock`(翻转=驱动内建) | 10-02 刷过 | **MIUI 桌面**(35.5s boot_complete) `[§70]` | 触摸✓ 显示✓ / WiFi✗ USB? 电量? | 留作**翻转线基准**；疑 129s WLAN 卡死 `[§71]` |
| 2 | `work/deliver/kraw/boot.img` | `c4fc2d02` | 10-02 21:33 | run 37010862587 系 / `star-stock-raw`(不翻转) | 10-03 今日重刷 | **卡在 LOGO+小绿人** `[目]` | 无 adb | 废（raw 缺 ABI/去撞名修复）|
| 3 | `work/deliver/kfix2/boot.img` | `f932d6a8` | 10-02 22:42 | unexport-mhi + KILL CNSS2 | 10-02 刷过 | **启动前就复位** `[§]` | — | 废（已撤回那两处改动）|
| 4 | `work/deliver/kdiag/boot.img` | `4ee1e081` | 10-02 23:40 | +55s 现场快照 + auto_fastboot | 10-02 刷过 | 卡死但**留下 55s 现场** `[log]` | 无 | 诊断用，已过期 |
| 5 | `work/deliver/kfw2/boot.img` | `6b8a3f43` | 10-03 06:31 | +fw-retry 变体 | 10-03 刷过 | 卡 LOGO `[目]` | 无 | 废 |
| 6 | `work/deliver/kfwfix/boot.img` | `f2ae4d95` | 10-03 06:03 | +fw 修复 | 10-03 刷过 | 卡 LOGO `[目]` | 无 | 废 |
| 7 | `work/deliver/kfw3/boot.img` | `cc90206f` | 10-03 07:06 | +fw-timeout(60→5s) ✗ | 10-03 刷过 | 卡 LOGO `[目]` | 无 | **废；且 5s 超时是回归嫌疑** |
| 8 | `work/deliver/kdiag2/boot.img` | `12439fc4` | 10-03 08:11 | 诊断 v2 | 10-03 刷过 | 卡 LOGO `[目]` | 无 | 废 |
| 9 | `work/deliver/kearly/boot.img` | `f91c1dee` | 10-03 10:29 | +6s 早期快照 | 10-03 刷过 | 卡 LOGO，**自动回 fastboot** `[目]` | 无 | 废（logdump 6s 快照是这版加的）|
| 10 | `work/a-fix/boot-star-stock-raw.img` | `d45aa296` | 10-03 13:5x | run 37097223965 / raw + 去`tracing_mark_write`导出 | 10-03 刷过 | **约 15s 硬卡死→20s看门狗咬→循环** `[目][log]` | 无 adb | 废（撞名符号换成了 `disp_log_printk`）|
| 11 | `work/a-fix2/boot-star-stock-raw.img` | `e607d96d` | 10-03 13:5x | run 37100656225 系 / raw + fw-timeout 回滚… | 10-03 刷过 | 同上（15s 卡死循环）`[目]` | 无 | 废（当时 43 符号未处理）|
| 12 | `work/artifacts/run-36993922435/…`(锚点复验) | `4199ac89` | — | 同 #1 | 10-03 尝试 | 用户判断放弃 `[?]` | — | 未正式复验 |
| 13 | `work/a-inc/boot-star-stock-raw.img` | `e1645928` | 10/03 06:45 | run 37102817574 / tag inc-abi-only = raw + 仅 ABI 修复(exit 偏移已=0x338) | 见下 | 卡在 LOGO+小绿人,约20s后黑屏并循环 [目] | 无 adb(未上线) | 废;但结论重要:**ABI 修复必要但不充分** ⇒ raw 线还需其它修复 |

| 14 | `work/a-v3/boot-star-stock-raw.img` | `b163b113` | 10/03 06:59 | run 37103316652 / L3 = raw + ABI修复 + 43符号去撞名 + MAC80211=y + 关冗余模块 + 安静logdump + 固件超时原厂 | 见下 | 开机后同前:仍停在 LOGO+小绿人(约20s 黑屏循环) [目] | 未上线,无法 adb | 废;但这是【目前最完整的一版】,自检全过(43符号0残留/exit=0x338/要件齐备) |
> 注：`work/deliver/*` 里的镜像是历史上从 CI 产物 `Image` 本地重打包的（`scripts/splice-bootimg.py`，用原厂 header+ramdisk）。

---

## 2. 两条线的脉络（以及为什么今天卡在 LOGO）

### L1 「翻转线」`star-stock`（把 62 个 `=m` 驱动翻成 `=y`，驱动**内建**）★ 现为 **主路线基线**
- **优点**：完全不依赖模块加载 ⇒ **能进 MIUI**（§70：35.5 秒 boot_complete，触摸/显示可用）✓
- **未交付原因（有界）**：与 `/vendor` 同名 `.ko` **重复注册**（不只 WLAN）+ `init.target.rc`
  的 `modprobe qca_cld3_wlan` 挂死占 `module_mutex`（§71）⇒ 2~3 分钟复位
- **修法（P1）**：Magisk/KSU overlay 黑名单（`/vendor` EROFS，只有 overlay 能改）+ WLAN fail-fast
- 结论：**Allbuiltin-Hybrid 的起点**。

### L2 「raw 线」`star-stock-raw`（保持原厂 `=m`，走**原厂模块**）⚠️ **已降级为存档**
> 2026-10-03 战略决策：公开树 ≠ 小米内部 5.4.233 树，装原厂 `.ko` 的 ABI 战不可收敛。
> 下列记录**只留证据与教训**，不再作为主线派发。
- **目标形态**：与原厂一致 —— 驱动由 `/vendor/lib/modules/*.ko` 提供 ✓
- **今天查明卡 LOGO 的两个真因**：
  1. **`struct module` ABI 偏移错位** ✗：`FTRACE_MCOUNT_RECORD`（由 `DYNAMIC_FTRACE` 带出）让 `source_list/target_list/exit/refcnt` **偏 8 字节**；vendor `.ko` 是按原厂布局编的 ⇒ 引用计数/依赖链全错 ⇒ `modprobe` 永久卡死（`faddr2line` 证据：`load_module+0x75c`=`add_unformed_module:3733`、`do_init_module+0xbc`）。
     **修**：配置生成后 `-d DYNAMIC_FTRACE -d FTRACE_MCOUNT_RECORD`（构建内断言 `exit` 偏移=原厂 `0x338`）
  2. **43 个符号与 `msm_drm.ko` 撞名** ✗：内建 techpack 显示驱动导出 `disp_log_printk`/`mi_disp_*`/`dss_reg_*`… 而 vendor `msm_drm.ko` 也导出同名 ⇒ 内核 `verify_exported_symbols()` 拒装 ⇒ 显示/触摸/充电/相机全部连带失败。
     **修**：精确取消这 43 个的内核导出（**只去导出、不删驱动** —— 删驱动会 `mi_disp_register_client undefined`）
- **另有回归**：`fw-timeout`(固件回退超时 60→5s) ✗、我加的 logdump 写盘风暴(100ms×2MB≈20MB/s) ✗、`auto_fastboot` 会误重启成功启动 ✗ —— 均已回滚/改安静/关掉。

### L2 增量实测(2026-10-03 14:5x, 镜像 `e1645928`)

`raw + 仅 ABI 修复` 刷入实测 **仍卡在 LOGO+小绿人(约20s 黑屏循环)** ✗。
从它的 logdump 现场(`work/inc-ld9.bin`, uptime 4.4s 后彻底静止)读到:

```
1.639s  msm_drm: exports duplicate symbol __tracepoint_tracing_mark_write (owned by kernel)
        ⇒ 只修 ABI 时 vendor msm_drm.ko 仍被拒装(去撞名未做)
3.79s   cnss: Failed to register MSM PCI event, err = -19
        cnss: Failed to probe PCI driver
        cnss: Retry cnss_bus_init #3
4.42s   cnss: BT_EN_GPIO State: Off. Delay WLAN_GPIO enable
4.43s   logdump: 心跳 #30 uptime=4439ms   ← 最后一条
```

**两条结论**：
1. **`struct module` ABI 修复是必要但不充分** —— 模块加载路径已修好，但 boot 仍不过 ✗；
2. **卡点收敛到 WLAN/CNSS 协议栈 probe**(`cnss2` 反复重试 `cnss_bus_init`，PCIe 事件注册 `-ENODEV`)⇒
   与 §71 记的"最后一个卡点是 vendor WLAN 栈"一致 ✓。
   ⇒ 下一步候选 v3(含 43 符号去撞名 + MAC80211=y + 安静 logdump + 固件超时原厂)刷入后看**是否越过 4.4s 这个点**。

### L3 「今天的主线」= L2 + 上面全部修复（当前在验）
- 变体 `star-stock-raw`，关键配方见 §3。

---

## 3. 当前主线的配方（可复现）

```
变体      : star-stock-raw      (NOFLIP:原厂 config 原样,不翻 =m→=y)
上游      : https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git  branch star-r-oss
工具链    : aosp-clang-11 (原厂同款)
配置生成后强制:
  -d DYNAMIC_FTRACE -d DYNAMIC_FTRACE_WITH_REGS -d FTRACE_MCOUNT_RECORD   # struct module ABI 对齐
  -e DETECT_HUNG_TASK --set-val DEFAULT_HUNG_TASK_TIMEOUT 15               # 卡住>15s 打印调用栈
  -e MAC80211 -d CFG80211_WEXT                                            # 厂商 WLAN 必需 / ABI 对齐
  (容器网络由 m2y.py 的 FORCE_Y 在 defconfig 阶段强制 =y)
m2y FORCE_Y: MAC80211 MACVLAN IPVLAN VXLAN NF_TABLES NF_TABLES_INET NFT_NAT NF_NAT
             NETFILTER_XT_TARGET_MASQUERADE IP_NF_NAT IP_NF_TARGET_MASQUERADE
精确去撞名: 43 个符号取消内核导出(见 workflow 步骤「★ 精确取消…」)
固件回退超时: 保持原厂 60s
logdump   : 512KB 正文 / 1s·3s·30s 周期 / auto_fastboot=false / 心跳每 5s 打一帧模块状态
```

### 构建内硬断言（不达标直接失败，不会白刷）
1. `FTRACE_MCOUNT_RECORD` 必须非 y；`FUNCTION_ERROR_INJECTION` 必须仍 y（后者在 `struct module` 尾部也有字段）
2. `out/Module.symvers` 里不得再出现那 43 个撞名符号
3. Droidspaces 核心要件必须 `=y`（MAC80211/MACVLAN/IPVLAN/VXLAN/NF_TABLES/USER_NS/PID_NS/IPC_NS/SYSVIPC/POSIX_MQUEUE/CGROUP_DEVICE/CGROUP_PIDS/TMPFS_XATTR/OVERLAY_FS/VETH/BRIDGE/SECCOMP_FILTER）
4. `CFG80211_WEXT` 必须非 y

---

## 4. 待验证 / 待办

- [ ] L3 镜像刷入实测：能否走过「三个点」进 MIUI；模块是否 111 全 Live；`msm_drm` 是否 Live
- [ ] WiFi（`qca_cld3_wlan` / `cnss2`）与 USB（adb）在 L3 上是否正常
- [ ] 电量/触摸（`qti_battery_charger_main` / `cyttsp5` / `xiaomi_touch`）
- [ ] Droidspaces 实跑（容器创建、网络、挂载）
- [ ] root：当前构建 `ksu=0` 不带 root；可用 APatch patch（内核有 `KALLSYMS_ALL`+`KPROBES`），或后续出 `ksu=1` 正式版
- [ ] 若 L3 仍不过：按「一次只加一项」在 L3 基础上二分（顺序：ABI 修复 → 43 符号去撞名 → 安静 logdump → 固件超时 → WiFi/容器要件）

### 4.1 原厂基线 vs 我们内核的目标（2026-10-03 实测，脚本 `scripts/verify-droidspaces.sh`）

| 检查项 | 原厂内核实测 | 我们内核应达到 |
|---|---|---|
| `/proc/cgroups` 控制器 | `cpuset cpu cpuacct blkio memory freezer`（**无 devices / pids** ✗）| **多出 `devices` + `pids`** ✓ |
| cgroup 层级 | v2 统一(`/sys/fs/cgroup`) + v1(blkio/cpu/cpuset) | 同（Android 13 原生布局）|
| `unshare -m/-u/-n` | ✓ ✓ ✓ | ✓ |
| `unshare -i`(IPC_NS) | ✗ `Invalid argument` | ✓ |
| `unshare -U`(USER_NS) | ✗ `Invalid argument` | ✓ |
| 全量 `unshare -m -u -i -n -U -p -f` | ✗ | ✓ |
| `mount -t overlay` | ✗ | ✓ |
| `ip link add … type macvlan/ipvlan/vxlan` | ✗ ✗ ✗ | ✓ ✓ ✓ |
| `veth` + `ip netns` | ✓ | ✓ |
| 模块数 / 关键模块 | 111，全 Live | 111，全 Live |
| UI / WiFi / 电池 | ✓ / ✓ / ✓ | ✓ / ✓ / ✓ |

> 用法：自编内核开机后跑 `bash scripts/verify-droidspaces.sh`，把结果填回本表第三列。
> 判据要点：**「原厂 ✗ → 我们 ✓」的那些格子，就是本任务第 3 条验收标准（Droidspaces 符合性）的证据。**

### ★ 2026-10-03 今日收尾状态（下次从这里接手）

**手机**：已刷回 **原厂 + root**（`work/boot_a-stock-69m.img`，md5 `58916775…`；完整版 `work/rollback/boot_a-stock-safe.img`，md5 `b56303df…`）⇒ 可用、带 APatch root ✓

**当前主线 L3 的状态**：`raw + 全部已知修复` 仍然**停在 LOGO+小绿人**（约 20s 黑屏循环）✗

**今天已确证的结论**（不再是猜测）：
1. **`struct module` ABI 偏移**（`FTRACE_MCOUNT_RECORD` 导致 `exit/refcnt` 偏 8 字节）—— 已修，实测 `.ko` 的 `exit` 偏移 = 原厂 `0x338` ✓；
2. **43 个与 vendor `msm_drm.ko` 撞名的内核导出** —— 已精确取消（0 残留）✓；删驱动不行（`mi_disp_register_client undefined`）；
3. **ABI 修复是必要但不充分**（增量实测：只修 ABI 仍卡 LOGO ✗）；
4. **卡点已收敛到 WLAN/CNSS 协议栈 probe**：增量版日志显示
   `cnss: Failed to probe PCI driver` → `Retry cnss_bus_init #3` → 4.4s 后内核彻底静止 ✗
   （vendor `cnss2.ko` 的符号都能解析，失败是**运行期 `-ENODEV`**，不是缺符号）；
5. **回归已回滚**：`fw-timeout`(60→5s) ✗、logdump 写盘风暴(100ms×2MB) ✗、`auto_fastboot` 误重启 ✗。

**v3 现场日志的关键结论（`work/fix-ld9.bin`，最后一次写盘 uptime=13.4s）**：
```
1.433s  msm_drm: module is already loaded        ← 不再是"符号重复"! 43 符号去撞名生效 ✓
2.497s  pcie_phy_init: PCIe RC0 PHY is ready!    ← 之前 4.4s 卡死的 cnss 段【完全通过】✓✓
4.33s~  init: wait for '/sys/devices/soc0/soc_id' / ufshc / qseecom / spunvm  全 0ms ✓
5.19s  logdump: spawn 采集脚本 成功 / 6.15s 早期快照已写
6.74s  init: processing action (early-boot) … / starting service 'vendor.ssgtzd'
8.40s  wcd938x codec 初始化 / wlan 栈继续加载
13.34s init: wait for '/sys/class/power_supply/usb/type' timed out (5005ms)   ← 卡点后移到这里
13.35s init: Service 'exec 24 (modprobe … qca_cld3_wlan …)' exited with status 1
```
⇒ **卡点从 4.4s 后移到 13.4s**，且性质变了：
`msm_drm.ko` 因为**名字已被占用**装不上（我们内核内建的 techpack 显示驱动注册了 `msm_drm`）
⇒ 依赖它的 **充电/触摸/相机** 模块全装不上（`power_supply/usb/type` 等待超时就是充电模块 ✗）。

**v4 实测（编译阶段就失败，未浪费刷机）** ✗：
```
ld.lld: error: undefined symbol: mi_disp_register_client
ld.lld: error: undefined symbol: mi_disp_unregister_client
>>> referenced by thermal_core.c:2080 / 2103   ← 内建 MIUI 热控在用
```
⇒ 去掉内建显示驱动后，**内建 `drivers/thermal/thermal_core.c`（MIUI 热控）**仍需要这两个符号 ✗

**v5（已派发）= v4 + 补两个【只定义、不导出】的桩** ✓
- 关键点：这两个名字**同时是 vendor `msm_drm.ko` 的导出**（在 43 撞名清单里）
  ⇒ 内核**绝对不能导出**它们（否则 msm_drm.ko 又被拒装 ✗），
  但内建 thermal 在 vmlinux 链接期必须有符号 ✗
  ⇒ 解法：在 `mi_syms.c` 里**只定义、不加 EXPORT_SYMBOL**（内建链接 ✓、导出表干净 ✓、vendor 提供真实现 ✓）
- 预期：链接通过 ⇒ 内核里没有 `msm_drm` ⇒ vendor `msm_drm.ko` 装得上 ⇒ 充电/触摸/相机/WiFi 全活

**v4（已派发）**：把内建 techpack 显示驱动整块去掉
（之前删会链接失败 `mi_disp_register_client undefined` ✗，正是因为树内那些模块 ✗；
 它们已在 v3 关掉 ⇒ 现在删是安全的 ✓）⇒ 预期 vendor `msm_drm.ko` 能装 ⇒ 下游模块齐活。

**下次最值得先做的实验（按优先级）**：
1. **看 L3 那轮的 logdump**（job `bash-60` 会自动取回 `work/fix-ld9.bin`）：
   - 若 `DETECT_HUNG_TASK=15s` 触发了 ⇒ 日志里会有**卡住任务的完整调用栈** ⇒ 直接定位；
   - 若停在同一个 cnss 位置 ⇒ 执行第 2 条。
2. **"先不要 WLAN 栈，把 boot 打通"**：既然 §70 那版（star-stock）是"**能进 MIUI，只差 WiFi**"，
   说明 **WLAN 是可以后置的**。可尝试：把 `mi_syms.c` 里那 3 个 `msm_pcie_*` 桩**去掉**
   （⇒ vendor `cnss2.ko` 因缺符号立刻装载失败 ✗ 而不是卡在 probe ✓），看 boot 是否能过。
   ⚠️ 这会让 WiFi 暂时没有，但能验证"WLAN probe 是不是唯一的拦路石"。
3. 打通 boot 后再攻 WiFi：查 PCIe 枚举（`msm_pcie_*` 的真实语义：`register_event`/`pm_control`/
   `enumerate`/`allow_l1`/`prevent_l1`/`set_link_bandwidth` 在公开树里没有对应实现）。
4. root：APatch 重新 patch 自编镜像，或出 `ksu=1` 版。

## 5. 留存位置（找旧版本用）

| 位置 | 保留 | 说明 |
|---|---|---|
| GitHub **Actions Artifacts** | **90 天** | 每次构建的 `boot-*.img` / `config.gz.txt` / `build.log` / `Module.symvers` / `modules.tgz` |
| GitHub Actions 运行日志 | 90 天 | 每个步骤的完整输出 |
| GitHub **Releases** | 永久 | 仅 2 个：`fix-36956585286`(boot-star-stock.img)、09-27 那版 |
| 仓库本身 | 永久 | workflow + configs + patches = 完整配方 |
| 本机 `work/artifacts/run-*` | — | 7 份历史产物缓存（含 10-02 那版 config/symvers/build.log）|
| 本机 `work/deliver/*` | — | 历史上本地重打包的镜像（见 §1 表）|

---

## 6. 源码仓库：用哪个、有哪些坑、我们填了哪些

### 6.1 唯一可靠的上游（★ 必须显式指定，别用默认值）

```
仓库 : https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git
分支 : star-r-oss
```
**为什么是它**：这是小米官方放出的、与本机同代的 OSS 树；`longpress` / `vkdevid`(KGSL_PROP_VK_DEVICE_ID) /
`mi_syms`(msm_pcie_*/mhi_force_reset) / minstrel 等补丁**只有在这棵树上位置才对**（实测过）。

> ⚠️ **地雷**：workflow 的默认值是 `EcrosoftXiao/kernel_xiaomi_mars@twelve` —— **另一棵树** ✗。
> 派发时**必须**显式传参，否则会静默用错树 ⇒ 补丁全线错位（历史踩过多次）：
> ```
> upstream        = https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git
> upstream_branch = star-r-oss
> variants        = star-stock-raw
> toolchain       = aosp-clang-11
> ```

### 6.2 树自带的坑 与 我们的处置

| # | 坑（现象 → 根因） | 状态 |
|---|---|---|
| 1 | 链接报 `No rule to make target .../vmlinux.lds` → 上游仓库 `.gitignore` 里有 `vmlinux*`，**误伤**了 `arch/arm64/kernel/vmlinux.lds.S` 和 `include/asm-generic/vmlinux.lds.h`（文件根本没被提交）| ✅ 已填：CI 里检测缺失并补回这两个文件 |
| 2 | 大量 `Unknown symbol` → 树是 A11 时代，**缺 MIUI 私有符号**（`power_debug_print_enabled`、`mi_power_save_battery_cave`、`mi_display_pm_suspend_callback_set`、`msm_pcie_*`、`mhi_force_reset`、`get_ufs_*`、`ufshcd_read_desc`…）⇒ 原厂 `.ko` 装不上 | ✅ 已填：`patches/mi_syms.c` **无条件导出**桩（⚠️ 不能用 `__weak`，会静默丢符号）|
| 3 | **`struct module` 字段偏移与原厂差 8 字节** → 树默认 `FUNCTION_TRACER`+`DYNAMIC_FTRACE` ⇒ `FTRACE_MCOUNT_RECORD`（`def_bool y/depends on DYNAMIC_FTRACE`）多插 2 个字段，把 `source_list/target_list/exit/refcnt` 顶偏；而 vendor `.ko` 内嵌的 `struct module` 是原厂布局，`MODVERSIONS=n` 又关掉了唯一能拦住它的 `module_layout` 校验 ⇒ 引用计数/依赖链全错 ⇒ `modprobe` 永久卡死 | ✅ 已填：`-d DYNAMIC_FTRACE -d FTRACE_MCOUNT_RECORD`；**校验手段**：`.rela.gnu.linkonce.this_module` 里 `exit` 偏移须=原厂 `0x338` |
| 4 | **内建 techpack 显示驱动与 vendor `msm_drm.ko` 43 个符号撞名**（`disp_log_printk`、`mi_disp_*`、`dss_reg_*`、`sde_rsc_*`…）⇒ 内核 `verify_exported_symbols()` 拒装 ⇒ 显示/触摸/充电/相机连带全废 | ✅ 已填：**精确取消这 43 个的内核导出**（⚠️ 不能整块删驱动：会 `mi_disp_register_client undefined`，有内建使用方）|
| 5 | `ld.lld: undefined symbol` → qca 树与内核都定义 `nl80211hdr_put` | ✅ 已填：全树改名 `qca_nl80211hdr_put`（定义处+调用处一起改）|
| 6 | `CONFIG_ICNSS2=y` 编译失败 → `drivers/soc/qcom/icnss2/qmi.h` 的 static inline 与真声明冲突 | ⏳ 未填（绕过：保持 `=m`，用 /vendor 的原厂 `cnss2.ko`）|
| 7 | **配置断言"假通过"** → GKI 片段链会在 `olddefconfig` 阶段把 `CONFIG_DRM_MSM` 之类又打开 ⇒ 断言必须放在 **olddefconfig 之后**、且要打印实际值 | ✅ 已填（方法论）：CI 断言放在配置生成之后，并逐项打印 |
| 8 | 用 `scripts/config -e X` 改配置**不可靠**（依赖链/藏符号会被 olddefconfig 还原）⇒ 改用 **defconfig 阶段强制**（`m2y.py` 的 `FORCE_Y`，且要同时处理 `=m` / `# ... is not set` 两种写法）| ✅ 已填（方法论）|
| 9 | `QCOM_WATCHDOG_BARK_TIME=20000`（20 秒）⇒ 任何 >20s 硬卡死都表现为「LOGO 约20s → 黑屏 → 循环」；诊断时**必须记住这个常数**，别误判成"启动循环" | 📌 记录（诊断常识）|
| 10 | PMIC(PON) 看门狗：bark 中断里 `panic("PMIC Watch Dog Triggered")` + 约 134 秒硬复位（`IRQ pmic-wd-bark not found`）| ✅ 已填：`patches/no-pmic-wd.py`（清使能位 + panic 降级为打印）|
| 11 | MIUI `longpress`（组合键检测 → `machine_restart`）⇒ 开机 ~9.7 秒自重启 | ✅ 已填：`patches/no-longpress.py` |
| 12 | 树比 A13 原厂旧，KGSL 缺 `KGSL_PROP_VK_DEVICE_ID` ⇒ `libEGL eglInitialize failed` ⇒ `RenderEngine: no suitable EGLConfig found` ⇒ surfaceflinger 自杀 | ✅ 已填：`patches/vkdevid.py` |
| 13 | 固件加载时序：自编内核比原厂早 ~7 秒请求 A660 固件，此时 `/vendor/firmware` 对内核还不可读(-EACCES) ⇒ GPU 起不来 | ✅ 已填：`patches/fw-retry.py`（-EACCES 重试）+ `CONFIG_EXTRA_FIRMWARE` 内嵌 a660 固件 |
| 14 | **别把固件回退超时改小**：`60s→5s` 会让走"用户态回退"的固件（GPU/ADSP/WLAN/触摸）更容易超时失败 ⇒ 卡 LOGO | ⛔ **我们踩过并回滚**（现由 CI 步骤强制保持 60s 并断言）|
| 15 | **调试设施反噬**：logdump 若按 100ms×2MB 落盘（≈20MB/s）会砸在启动期 I/O 上 ⇒ 卡住 → 看门狗复位 | ✅ 已填：安静版（512KB / 1s·3s·30s / 关 auto_fastboot）|
| 16 | Droidspaces 要件在原厂 config 里**大量缺失**（`PID_NS/USER_NS/IPC_NS/SYSVIPC/POSIX_MQUEUE/CGROUP_DEVICE/CGROUP_PIDS/OVERLAY_FS/VETH/MACVLAN/IPVLAN/VXLAN/NF_TABLES`…），且**设备上没有这些厂商 `.ko`** ⇒ 设成 `=m` 等于没有 | ✅ 已填：`m2y.py` 的 `FORCE_Y` 强制 `=y` + CI 硬断言 |
| 17 | `CONFIG_MAC80211=m`（原厂是 `y`）⇒ 厂商 `qca_cld3_wlan.ko` 依赖内核内建 mac80211 ⇒ WiFi 装不上 | ✅ 已填：`FORCE_Y` 强制 `=y` |
| 18 | `CONFIG_CFG80211_WEXT=y`（原厂 `n`）⇒ `struct wireless_dev` 多一段，与 vendor WLAN 布局不一致 | ✅ 已填：关掉 |
| 19 | vermagic 缺 `modversions` 字样（`MODVERSIONS=n` 但原厂模块带该串）| ✅ 已填：`patches/vermagic.py` |
| 20 | 对齐原厂杂项：RELR / `STACKPROTECTOR_PER_TASK` / `REFCOUNT_FULL` 必须关（原厂关，且影响 ABI/自重定位）| ✅ 已填：CI Kconfig 强制 |

### 6.3 方法论坑（比代码坑更容易害人）

1. **`pkill -f <名字>` 会匹配到自己所在的命令行** ⇒ 自杀（今天又踩一次 ✗）。用不含该字样的模式，或拆成 `"abc-""def"`。
2. **别把"内核跑了 694 秒"当成"进了 MIUI"** —— 卡在 LOGO 时内核照样跑，看门狗 20s/134s 才复位。判断"进系统"只有三个硬指标：`boot_completed=1` / `dumpsys` 里有 launcher / 用户目视桌面。
3. **多台设备时选路必须校验身份**（`ro.product.device == mars`）—— 否则会把容器宿主机（一加 12，`172.28.0.1:5555`）当成目标机，得出假的"启动成功"。
4. **`screencap` 在本机全黑**（即使系统正常）⇒ 不能用截图当证据，用 `dumpsys SurfaceFlinger --list`。
5. **改动要能二分**：一次只加一项，每项留一条 `VERSIONS.md` 记录（含证据等级）。

### 6.4 二分手法（标准化，2026-10-03 定）

`workflow_dispatch` **不接受 commit sha**（只接受 branch/tag，短 sha 报 `No ref found`）⇒
每个"增量"提交先打 tag 再派发，tag 名即该增量的含义：

```bash
SHA=$(git -C gh rev-parse <短sha>)          # 取完整 sha
# 打 tag
curl -X POST -H "Authorization: token $T" .../git/refs \
     -d "{\"ref\":\"refs/tags/inc-abi-only\",\"sha\":\"$SHA\"}"
# 用 tag 派发
curl -X POST .../actions/workflows/build.yml/dispatches \
     -d '{"ref":"inc-abi-only","inputs":{"variants":"star-stock-raw",
          "upstream":"https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git",
          "upstream_branch":"star-r-oss","toolchain":"aosp-clang-11"}}'
```

已打标签：`inc-abi-only` = `9889c0e`（= kraw 基线 + **仅** ABI 修复）⇒ 若它也不启动，
就能确定"ABI 修复不是充分条件"，下一增量再加"43 符号去撞名"。

## 2026-10-04 夜间值守记录（自动）

**镜像** `work/repack/boot-p1-fw2s.img`（md5 `d01fdb95…`）= hwid 去导出 + FTS=mod + **fw-timeout 2s**。
刷入后 ~40s 进 fastboot，已 `tight-flash` 刷回原厂+root ✓。

**fw-timeout 2s 结果**：
- ueventd 固件回退正常（modem 固件 1–2ms 装载）✓
- 但 `aw8697_rtp_1.bin` 缺失快速失败、`healthd: No battery`（11.6s）仍在
- **疑似回归**：2s 过短可能让早期 GPU/ADSP 固件请求失败（§70/§73 教训）。
  与 60s 版对比：60s 版电池在 16s 通了（late-diag healthd l=74），2s 版反而没到那一步。

**结论**：fw-timeout 不宜过短。下一增量建议：
1. fw-timeout 改 **10 秒**（折中），或回退 60s；
2. 或不改超时，改为 **跳过会挂住的模块**（触摸/haptics 固件）让 vendor_modprobe exec 返回；
3. 电池 probe 比原厂晚 ~6s（pmic_glink 子设备创建晚）是 `init.mi_thermald.rc` 5s 等待超时的根因，
   需让 probe 提前或覆盖该 rc。

**手机状态**：原厂+root，可用。


## ★★★ 2026-10-04 p1i7 失败根因：`XIAOMI_TOUCHFEATURE` 被 m2y 翻成 `=y` ⇒ fts 永不装载

### 实测（p1i7 = Inc7，md5 `bc4ca9e1…`）

- 能进 MIUI，显示/亮度正常，**无触屏**；USB adb 也挂（用户盲区，救回原厂）。
- logdump（`work/fix-ld9.bin`）实锤：
  - `xiaomi_touch_dev_open/ioctl` 大量出现 ⇒ **内建 xiaomi_touch 框架在跑**
  - **0 条 fts / hwid / dummy-psy / mars-blacklist** 消息
  - `display_panel_avdd: disabling`(31.7s) 是整包 regulator 关闭潮，不是触摸供电主因

### 根因链（已符号级验证）

1. 源 defconfig：`CONFIG_TOUCHSCREEN_XIAOMI_TOUCHFEATURE=m`
2. `m2y.py` KEEP 只有 `CONFIG_TOUCHSCREEN_ST_FTS`（startswith 匹配 FTS*）
   ⇒ `XIAOMI_TOUCHFEATURE` **被翻成 `=y` 内建**
3. NAMES 又把 xiaomi_touch 的 **10 个接口符号去导出**（get_xiaomi_touch_class /
   update_* / copy_touch_rawdata / xiaomitouch_register_modedata / …）
   ⇒ 内建不给符号，原厂 `xiaomi_touch.ko` 又因占名装不上
4. `fts_touch_spi_k2.ko` 的 `depends=xiaomi_touch,hwid,msm_drm`
   ⇒ modprobe 依赖解析失败 ⇒ **fts 永不装载** ⇒ 无触屏

对照（原厂模块导出表）：
- `xiaomi_touch.ko` 导出 fts 需要的 10 个符号 + `last_touch_events_collect`
- `hwid.ko` 导出 `get_hw_*` / `product_name_get`
- p1i7 `Module.symvers` 里 vmlinux **0 个**上述符号（全被去导出）

### 修复（p1i8 = Inc8）

`m2y.py` KEEP 增加 `CONFIG_TOUCHSCREEN_XIAOMI_TOUCHFEATURE`（保持 `=m`）。
⇒ 原厂 `xiaomi_touch.ko` 可装载并导出符号 ⇒ `fts_touch_spi_k2` 可解析依赖。

**铁律**：凡 NAMES 去导出的驱动接口符号，其提供者**绝不能**被 m2y 翻成 `=y`
（内建占名 + 不给符号 = 双杀）。要么保持 `=m` 走原厂 .ko，要么重新导出。


## 2026-10-05 p1i8 实测：能进桌面，触屏仍无效 + 诊断盲区根因

### p1i8（Inc8，md5 `b6969372…`，XIAOMI_TOUCHFEATURE=m 已生效）

- ✅ 能进 MIUI 桌面（用户目视，>2 分钟）
- ❌ 触屏仍无效
- dummy-psy 假充电显示（未插 USB 也有充电）✓ 预期内
- USB adb / WiFi adb 均不可用 ⇒ **无活体诊断通路**（盲区）

### logdump 诊断 bug（实锤，已修在 Inc9）

`LOGDUMP_EARLY_OFFSET` 与 `LOGDUMP_SNAP2_OFFSET` **同为 32MB**
⇒ 6s 早期快照（模块装载行）被 55s 快照**覆盖** ⇒ 读回来只有 27s+ 挂起栈。
这就是为什么 p1i7/p1i8 的 logdump 里 0 条 fts/hwid/mars-blacklist。

**Inc9 修复**：早期快照改 **36MB** 偏移；postflash-cycle 增读 `skip=36`。

### p1i8 结论

`XIAOMI_TOUCHFEATURE=m` 是必要条件（否则 fts 依赖必失败），但**不充分**。
因早期日志丢失，尚不知 fts/hwid 是「没装载」还是「装载了 probe 失败」。

### Inc9 增量（已派发 37227984531）

1. logdump 早期快照 36MB（保模块装载证据）
2. mod-blacklist 放行 **WLAN 链**（cnss2/qca_cld3_*/…）⇒ 无线 adb 通路
3. 放行更多 USB gadget（xhci_hcd/libcomposite/…）
4. check_modinfo 对**每个**模块打 `mars-allow:` / `mars-blacklist:` 日志

**目标**：Inc9 起来后能 adb 进去 live 查 `lsmod` / `dmesg` / 手动 modprobe 触屏链。

### ⚠️ IP 换位（2026-10-05）

- 一加 12 = `192.168.1.4`（**绝不动**）
- mars = `192.168.1.37`
刷机前必验 `ro.product.device==mars`。`dev-pick.sh` 已更新。


## ★★★ 2026-10-05 p1i9 早期 logdump 实锤：**vermagic 不匹配拦死全部 vendor 模块**

### 36MB 早期快照（Inc9 新修）首次拿到 0–6s 装载现场

```
dummy-psy: touch_vreg enable ret=0          ← 触摸供电成功！
mars-allow: hwid
hwid: version magic '5.4.233-gbb70cde46897 SMP preempt mod_unload modversions aarch64'
              should be '5.4.233-qgki-gbb70cde46897 SMP preempt mod_unload modversions aarch64'
mars-allow: dwc3 / dwc3_qcom / phy_msm_ssusb_qmp / xhci_hcd / extcon_usb_gpio
  ⇒ 全部同一 vermagic 报错
mars-blacklist: skip …（242 条）
```

**唯一差异 = `-qgki` 前缀**。原厂 .ko 的 vermagic 不统一：
- 有的带 `5.4.233-qgki-gbb70cde46897`（如 msm_drm，装得上）
- 有的是 `5.4.233-gbb70cde46897`（hwid/dwc3/xhci/…，被拒）

### 为什么之前一直没发现

p1i7/p1i8 的 logdump 早期快照被 55s 快照**覆盖**（同写 32MB 偏移）⇒ 0 条装载日志。
Inc9 把早期快照改 36MB 后立刻实锤。

### Inc10 修复（已派发 37230793059）

`check_modinfo` 对 allowlist 放行的模块**直接 return 0**，跳过 vermagic 比对
（MODVERSIONS 已关，符号 CRC 本来就不查）。

**预期**：hwid/xiaomi_touch/fts_touch/dwc3/xhci 全部装上 ⇒ 触屏 + USB 同时通。


## 2026-10-05 p1i10 实测 + 下一增量（Inc11）

### p1i10（跳过 vermagic）36MB 早期快照结论

- ✅ vermagic 报错消失（bypass 生效）
- ❌ `hwid: module is already loaded`（内建占名，且 get_hw_* 已去导出 ⇒ fts 无符号）
- ❌ **xiaomi_touch / fts_touch_spi_k2 全程 0 次 check_modinfo**
  （modprobe 见到内建同名直接跳过，finit_module 从未调用）
- USB：`xhci_hcd` 撞名 `xhci_get_sec_event_ring_phys_addr`、`dwc3` 撞名 `dwc3_core_init`
  多个 USB 驱动 "already registered"（m2y 内建占名）

### Inc11 修复（37233516846）

1. **NAMES 去掉 18 个 get_hw_*/xiaomi_touch 接口符号** ⇒ 从内建重新导出
   （提供者是内建且占名，原厂 .ko 装不上，必须由内建供符号）
2. **dummy-psy 增加 request_module 触屏链**（hwid/xiaomi_touch/fts_touch…）
   每个打 `dummy-psy: request_module(xxx) ret=N` —— 绕过 modprobe 静默跳过
3. vermagic bypass 保留

**预期**：fts_touch 能解析 get_hw_*/xiaomi_touch_* 符号并装载 probe。


## 2026-10-05 逐版验收矩阵（回答「上一版问题是否解决」）

| 版本 | 改动 | 上一版问题 | 本版实测 | 新问题 |
|---|---|---|---|---|
| p1i9 | logdump 早期→36MB；XIAOMI_TOUCHFEATURE=m | 看不到装载日志 | ✅ 有 0–6s 日志；✅ touch_vreg=0 | vermagic 拦死全部 vendor .ko |
| p1i10 | 跳过 vermagic | vermagic | ✅ 报错消失 | hwid 内建占名；fts 0 次 check_modinfo；USB 撞名 |
| p1i11 | 重导出符号 + request_module | fts 无符号；modprobe 静默跳过 | ✅ force-load 执行 | request_module=ENOENT(路径)；重导出→hwid duplicate |
| **p1i12** | **call_usermodehelper+insmod 直载 fts** | fts 不被装载 | 待验 | — |

**贯穿主目标**：`fts_touch_spi_k2.ko` 装载成功。
阻塞链: ①vermagic(已解) → ②hwid 依赖失败(内建占名) → ③modprobe 跳过 fts → ④request_module 路径错(p1i11 发现)

p1i12: insmod 不走 modules.dep，直接解析内核导出表（get_hw_*/xiaomi_touch_* 已重导出）。


## 2026-10-05 p1i13 两轮实测 + post-fs-data 方案

### 第一轮 p1i13（FORCE_Y + 重导出符号）

| 项 | 结果 | 证据 |
|---|---|---|
| xiaomi_touch_probe | ✅ **成功** | `xiaomi_touch_probe enter/over` @1.06s |
| touch_vreg | ✅ enable ret=0 | dummy-psy |
| fts_touch_spi_k2 | ❌ 未装载 | 无任何 FTS 日志 |
| insmod(usermode) | ❌ exit 65280 | 3.1s 时 linker64 未就绪 |
| 能进系统 | ✅ 用户确认 | 但触屏无效 |

### 第二轮 p1i13 + post-fs-data 脚本

- 脚本在原厂验证 OK（event4: fts）
- 刷自编后**卡死**（15 分钟无 fastboot）⇒ 疑 fts_probe 固件等待挂起
- 已改为 `timeout 8 ... &` 后台非阻塞

### 根因总结（insmod 255）

`/system/bin/insmod` → toybox（**动态链接 linker64**）。
`call_usermodehelper` @3.1s 时 linker 不可用 ⇒ 所有命令 exit 255。
init 的 vendor_modprobe 能跑是因为它以 init 域、在完整挂载后执行。

### Inc14 修复

1. insmod 延到 **12s**（linker64 就绪）
2. stderr 写 `/dev/kmsg`（logdump 可抓）
3. post-fs-data 改后台非阻塞


## ★★★ 2026-10-05 静态兼容性矩阵（离线分析,114 个 vendor .ko）

### 全局结论

| 类别 | 数量 |
|---|---|
| **完全兼容**（符号全齐） | **93 / 114** |
| 缺符号 | 21 |
| 导出撞名 | 85 个冲突（8 个模块） |

### 触屏链：fts_touch_spi_k2 仅缺 4 个符号

| 符号 | 提供者 | 修复 |
|---|---|---|
| `mi_disp_register_client` | msm_drm.ko（已装载） | insmod 时自动解析 |
| `mi_disp_unregister_client` | msm_drm.ko | 同上 |
| `last_touch_events_collect` | 仅 xiaomi_touch.ko | **补桩导出** |
| `update_fod_press_status` | 仅 xiaomi_touch.ko | **补桩导出** |

### Inc16 全量修复（37253962884）

1. mi_syms.c 补 `last_touch_events_collect` + `update_fod_press_status` 桩并导出
2. NAMES 加 `dwc3_core_init` / `xhci_get_sec_event_ring_phys_addr` / `ipa_is_ready`（去导出，解 USB/WiFi 撞名）
3. 保留既有：FORCE_Y xiaomi_touch、vermagic bypass、12s insmod、符号重导出

**矩阵报告**：`work/compat-matrix.json`

---

## ★★★★ 2026-10-09 P2 里程碑：**LOS 5.4.242 基线 + allbuiltin 版首次进入 MIUI**（新血缘主线）

> 旧的 `MiCode/star-r-oss`(5.4.61) 老树因为「vendor WLAN/GKI 模块 ABI 不兼容」被放弃（详见
> `docs/mars-handover-CHECKLIST.md` §41.48-§41.49）。新基线 = **LineageOS `android_kernel_xiaomi_sm8350`
> branch `lineage-20`（5.4.242, tip d42d2eb6c）+ 真机 `/proc/config.gz` 原厂 config**，工具链 clang 11.0.2。

| 镜像 | md5 | 配方 | 结果 |
|---|---|---|---|
| `Image-los10` | `2cb7e036…` | 原厂 config + 容器项 + kabi + ignore-vermagic + mi_syms + wlanblock | ❌ 黑屏（recovery 模式 + vendor 模块被拒） |
| **`Image-los11`** | **`9e372a48…`** | 同上 + **allbuiltin**（`=m`→`=y` 全内建）+ 无 recovery ramdisk + APatch | ✅ **进 MIUI**（首个可用内核） |
| `Image-los12` | 待测 | `Image-los11` 但 **wlanblock=0**（去掉 WLAN 黑名单门禁） | 目标：让 MIUI 自己的 `qca_cld3_wlan.ko` 开机装进来 ⇒ `wlan0` |

### Image-los11 实测（`[adb]`，run 37854523421 的前一版）

- 内核 `5.4.242-qgki-gbb70cde46897+ #1 SMP PREEMPT Thu Oct 8 22:07:49 UTC 2026`，槽 `_a`，`boot_completed=1`，稳定不自重启
- 触屏 ✅（fts 设备 + FTS 驱动日志 + getevent 有事件）；屏幕 ✅（锁屏截图有画面）
- 容器 ✅：运行内核 17/17 容器项 `=y`；`droidspaces check` **28/28 通过 0 失败**；能起 alpine 容器、有 veth/NAT
- root ✅：`su` = `uid=0`、`su --version 11224:APatch`、`apd` ×2（每次刷入都经 `apatch-flash-generic.sh`）
- WLAN ❌（本轮修）：见下

### WLAN 结论（`Image-los12` 的依据）

原厂是**开机时**由 `/vendor/etc/init/hw/init.target.rc:272-273` 执行
`/vendor/bin/modprobe -a -d /vendor/lib/modules/ qca_cld3_wlan qca_cld3_qca6390` 来装 WLAN 驱动的；
我们的 wlan-block 黑名单按模块名拒装 ⇒ 那两条 modprobe 必然失败 ⇒ 永远没有 `wlan0`。
运行期无法补救（`rmmod wlan` → `Try again`；`insmod` 原厂模块 → `File exists`）⇒ **只能在开机时放行**。
内建 `cnss2` 本身已跑通射频（MHI POWER_ON → 固件 `WLAN.HSP.1.1.c3-00260` → `COLD_BOOT_CAL_DONE` →
`Calibration completed successfully`），所以 `Image-los12` 只要放行原厂 `qca_cld3_wlan.ko` 就有机会出 `wlan0`。

---

## ★★★★★★ 2026-10-10 P3 里程碑：**WiFi 通了 + 全项验收通过**（可日常使用的 Droidspaces 内核）

| 项目 | 结果 | 证据 |
|---|---|---|
| 内核 | `5.4.242-qgki-gbb70cde46897`（runner@，`CONFIG_MODVERSIONS is not set`），槽 `_a` | `[adb]` |
| MIUI | `boot_completed=1`，稳定 | `[adb]` |
| **WiFi** | **`wlan0` UP + `192.168.1.145/24`，连上 `jjhome`（5GHz 5180MHz，11ax，Link 2401Mbps），ping 网关/223.5.5.5 **0% 丢包** | `[目录]` `work/p3-evidence/screen-wifi.png` |
| 触屏 | fts 正常 | `[adb]` |
| 容器内核项 | SYSVIPC/POSIX_MQUEUE/PID_NS/IPC_NS/NET_NS/USER_NS/UTS_NS/CGROUPS/VETH/OVERLAY_FS/BRIDGE/… 全 `=y` | `[adb]` |
| `droidspaces check` | **28/28 通过，0 失败** | `work/p3-evidence/ds-check.txt` |
| 容器 | alpine 起来（PID1=`init`，`uname -a` 看到内核 `5.4.242-qgki`），`ds-v*` veth UP + NAT MASQUERADE | `work/p3-evidence/final.log` |

### 关键翻转：之前"原厂 WLAN 驱动 ABI 不兼容"是**误判**
真凶是手机上的遗留实验脚本 `/data/adb/service.d/mars-wlan-prep.sh`：
它把 `/vendor/firmware/wlan/qca_cld/wlan/` 用 **空 tmpfs** 盖住，并塞进一个 **5597 字节全空白**的
`wcnss-ipa0.ini` ⇒ 原厂的 `WNSNS_qcom_cfg.ini`(→`/vendor/etc/wifi/wlan/…`, 215 行) 与 `wlan_mac.bin`
一起被藏起来 ⇒ 驱动 probe 失败。撤掉该 overlay（`chmod -x` + `umount` + 文件改名）后，
**原厂 cnss2 + qca_cld3_wlan.ko 在我们内核上 probe 成功、建出 wlan0、能上网**。

### 最终可用配方（当前手机就是这个状态）
- 镜像：`Image-los45`（= los40 配方：LOS d42d2eb6c + 原厂 config + allbuiltin + kabi +
  ignore_vermagic + mi_syms + hwid_deexport + wlanblock=1），boot image md5 `663ce79e…`
- 开机自动 WLAN：`/data/adb/service.d/99-wlan-mars.sh` v3（顺序**必须**是：
  开闸 `mars_wlan_allow=1` → cnss_utils/prealloc/nl + mi_cnss_statistic → **原厂 cnss2.ko**
  → `echo 1 > …/fs_ready` 等 CBC 完成 → **原厂 qca_cld3_wlan.ko** → `/system/bin/svc wifi enable`）
  * 注意 1：`qca_cld3_wlan` 早于 CBC 装会被 cnss2 以 `-EPERM` 拒绝
  * 注意 2：service.d 里 `svc` 会解析到 APatch BusyBox 的 runsv 命令 ⇒ 必须写 `/system/bin/svc`
- 救机：GOLD `work/boot_a-stock-69m.img` / 149 上 `apatch-patched-boot-0.13.3.img`(md5 `8fcf3576…`)

### 已知残留（不影响使用）
- `wlanblock=1` 门禁让 MIUI 自己在开机早期装原厂栈必然失败一次；由上面的脚本在 boot 完成后补装。
  下一步可试 `wlanblock=0`（门禁放开）让 MIUI 原生流程直接装（旧"开闸开不了机"同样是空 INI 的锅）。
- 自编 cnss2/wlan.ko 路线（los39/40/43/44/45 的附产物）已无必要：我们的 cnss2 能把芯片拉到
  FW_READY，但 qcacld probe 里返回 -1（QDF 未映射状态 ⇒ -EPERM），原厂栈既然能用就先搁置。

---


## ★★ 2026-10-10 收尾②：**一次离线符号分析的假阳性 + 判定模块集归属的指纹**（los53 已取消）

原本想用"缺 `debugfs` 导出符号"解释相机/声卡链装不上——**该结论已被证伪**，记录在此以免后人重犯：

- 我扫的模块集 `work/repack/rootfs/vendor/lib/modules`（含 `camera.ko`，md5 `7beff942…`）vermagic 是
  `5.4.233-qgki SMP preempt mod_unload modversions aarch64`（**没有构建哈希**），而真机内核与模块是
  `5.4.233-qgki-gbb70cde46897`。前者是另一套（GKI 风味）构建，**不是手机上那套**。
- 真机证据（`work/baseline-stock/`，2026-10-06 从原厂手机拉取）：
  * `dmesg.txt`：`CAM_WARN: … DebugFS not enabled in kernel!`、`cnss_utils: Unable to create debugfs -19`
    ⇒ 原厂内核 **DEBUG_FS=n**（与它的 `/proc/config.gz`、`extract-ikconfig` 一致）；
  * `lsmod.txt`：`camera`(被 27 个模块依赖)、`mbhc_dlkm`、`swr_ctrl_dlkm`、`wcd938x_slave_dlkm`、`cnss2`
    **全部装载成功** ⇒ 真机那套模块**不引用 debugfs 符号**（无 debugfs 时走 `#else` 分支，打印上面那些警告）。
- 真机 vendor_boot 镜盘自带模块（`work/vb/vb_rd.cpio`：`msm_drm.ko`、`5.4-gki/clk-*.ko`）vermagic 同样是
  `…-gbb70cde46897`，`debugfs_UND=0`。⇒ **判定一套 .ko 是否属于真机的可靠指纹 = vermagic 里的构建哈希**，
  其次是"真机 `lsmod`/`dmesg` 里有没有装载成功的记录"。
- 基于错误前提的 los53（`DEBUG_FS=y`，run `38009842825`）**已取消**（`cancel http 202`）。**不要刷它**。

**仍然成立的音频根因**：真机 `mbhc_dlkm.ko` 引用小米私有 `is_early_cons_enabled`，而该符号
**在原厂内核 Image 的导出表里存在**（`strings` 明文命中 1 次），我们内核没有 ⇒ `mi_syms_audio` 桩仍然必要。

**下一步（正确做法）**：手机恢复后第一件事 `adb pull /vendor/lib/modules`（root）把**真机模块集**完整存档
（带 md5 清单 + `modules.load/dep`），再用
`work/compat-out/compat-matrix.py --symvers <我方 Module.symvers> --ko-dir <真机集>` 重算缺口——
相机/蓝牙真正的缺符号一律以这套为准（同时用 vermagic 校验归属）。

---

## ★★★ 2026-10-10 收尾③：相机=脚本级修复、蓝牙=配置修复（离线算清，候选已预编译）

新工具 `work/compat-out/device-gap.py`（自带 vermagic 归属校验、只对真机 `modules.load` 里的模块出报告）：

| 问题 | 证据 | 修法 |
|---|---|---|
| **相机** `vendor.camera-provider-2-4` 崩溃循环 | `camera.ko` 300 个未定义符号里 8 个是 `debugfs_*`（**真机那份 `DEBUG_FS=n`，根本没这引用**）；余下 292 个中 **291 个由我们 vmlinux 提供**，只有 `get_hw_version_platform` 要 `hwid.ko`；与 vmlinux **零撞名**。装不上是因为 `modules.dep` 的依赖 `leds-qti-flash`/`led-class-flash`/`qti_battery_charger_main`/`msm_drm` 与我们内建驱动撞名被拒 ⇒ modprobe 链断 | **脚本级**：开机脚本里直接 `insmod /vendor/lib/modules/camera.ko`（先 `hwid.ko`），绕过依赖解析。试验脚本 `scripts-mars/camera-try.sh` 已就位 |
| **蓝牙** 能开不能连 | 工厂表 `SLIMBUS`/`SLIMBUS_MSM_NGD`/`BTFM_SLIM`/`MSM_BT_POWER` 本来**都是 `=m`**，被 `allbuiltin=1` 翻成 `=y` ⇒ 真机 `slimbus.ko` 与 vmlinux 撞 **44** 个符号被拒装；`bt_fm_slim.ko` 虽装上但驱动已注册 ⇒ `Failed to register slimbus driver: -16`（与真机日志一致） | **配置**：`force_m=…,SLIMBUS,SLIMBUS_MSM_NGD,BTFM_SLIM,MSM_BT_POWER`（`force_m` 在 allbuiltin 之后执行） |

**普遍规律（重要）**：凡真机 `modules.load` 会装的原厂 DLKM，我们内核都不能把同一个驱动编进去 ——
与 vmlinux 撞名会被 `insmod` 直接拒（`exports duplicate symbol … owned by kernel`），驱动先注册会让原厂模块
注册失败（`-16`）。要么 `force_m` 保持 `=m`（CNSS2 那套），要么像 `hwid_deexport` 那样把符号让出去。

**已派发预编译**：`los54` = los52 + BT 四配置（run `38010682716`）；`los55` = P3 + BT 四配置（run `38010690901`）。
产物后台下载到 149 `~/mars-build/artifacts/`。相机修复不需要新内核。

---

## ★★★ 2026-10-10 09:0x 收尾④：蓝牙修复已在**产物层**确认（los54/los55 双候选就绪）

| tag | 配方 | run | 结果 |
|---|---|---|---|
| **los54** | los52(=P3+固件内建+音频桩) + `force_m` 追加 `SLIMBUS,SLIMBUS_MSM_NGD,BTFM_SLIM,MSM_BT_POWER` | `38010682716` | ✅ 成功，产物在 149：`Image-los54` md5 `5de7e3636e3c4831fdcdb56edccf4855`（43,387,392B）、`los54-modules.tgz` md5 `a24a86d8d1d6ab79aa40d658c868dfe2`（4,288,414B） |
| **los55** | P3 + 同一组 BT 配置 | `38010690901` | ✅ 成功 |

**产物级硬证据**：`modules.builtin` 里 `slimbus|btfm_slim|btpower` 条目 **los52=3 ⇒ los54=0**；模块包新产出
`slimbus.ko`/`slimbus-ngd.ko`/`btpower.ko`/`bt_fm_slim.ko`（los52 为 0）；模块总数 43→47；`Image-los54` 同时含
`st_fts_k2.ftb`（固件内建）与 `is_early_cons_enabled`（音频桩）。⇒ 真机 `slimbus.ko` 不再被 vmlinux 撞名拒装，
`bt_fm_slim.ko` 也不会再撞"驱动已注册(-16)"。

**顺带结论**：我们自编模块 vermagic 一律 `5.4.233-qgki-gbb70cde46897`（与真机模块同串；内核 Image 是 5.4.242）
⇒ `ignore_vermagic=1` 仍必要。

**工具**：`scripts-mars/flash-tag.sh <tag>`（通用打包+刷机+计时+p4-verify）、`evening-run.sh --tag los54`
（蓝牙验证）、`misc-diag.sh`（指纹/NFC/红外/触感）、`stability-watch.sh`（长稳）、`cleanup-mars-scripts.sh` v2。
`work/keep-p3/MD5SUMS` 漂移已修（以 149 KEEP 为权威，本地 5/5 OK）。

---

## ★★★★ 2026-10-10 09:2x 收尾⑤：**两个配方级错误被揪出**（会影响今晚闪机，必须记住）

### 1. `force_m` 里塞 `CNSS_UTILS` ⇒ **WiFi 必挂**（los52/54/55/56/57 全部作废）

- 工厂表 `CONFIG_CNSS_UTILS=y` / `CNSS_GENL=y` / `WCNSS_MEM_PRE_ALLOC=y`；原厂内核是**内建**
  （`work/baseline-stock/lsmod.txt` 里没有 cnss_utils/prealloc/nl 三个模块）。
- 真机上唯一那份 `/vendor/lib/modules/5.4-gki/cnss_utils.ko` 在 P3 上 insmod 报
  **`invalid module format`（rc=8）**，vendor_boot 镜盘与 main 目录都没有它。
- los52 的实际 config 提取确认 `CONFIG_CNSS_UTILS=m` ⇒ 内建没了、模块又装不上
  ⇒ 原厂 `cnss2.ko` 缺 `cnss_utils_*` 符号 ⇒ **装不上 ⇒ 没 WiFi**。
- P3 之所以好，是"缓存毒化"让它保持 `CNSS_UTILS=y` + `ICNSS2=y`。**忠实 P3 = 不要把这两个塞进 force_m**。
- **修正配方**：`force_m=CNSS2,CNSS_GENL,WCNSS_MEM_PRE_ALLOC`（+蓝牙四项可选）+ `force_y=CNSS_QCA6490`。
- **新候选**：**los58**（P3 实际配置 + 固件内建，run `38012926791`）、
  **los59**（los58 + 蓝牙四项，run `38012935558`）。旧候选 los52/54/55 降级为存档，los56/57 已 cancel。

### 2. 音频桩 `is_early_cons_enabled` 的前提**不成立**

- 扫遍本地全部 400+ 个 `.ko`：**没有任何模块引用它**（它只在内核串口驱动的 printk 与原厂内核导出表里）。
- repack 套的音频 DLKM 对我们内核**缺符号 = 0**（剔除 debugfs 后）：mbhc 42 UND/0、machine 94/0、
  wcd938x 105/0、swr_ctrl 96/0、apr 59/0 ⇒ **音频模块没有符号障碍**。
- ⇒ los58/los59 **不带桩**；若音频仍无声，用 `mod-gap.sh` + dmesg 从别处找因（重点看真机音频模块是否被 MIUI 装载）。

### 3. 方法学：判"固件内建"必须用 `extract-ikconfig`，不能看字符串或体积

`st_fts_k2.ftb` 是**驱动里的固件名**（P3 镜像里 grep = 0，los52 = 1 只是因为 EXTRA_FIRMWARE 会把文件名存进 `.builtin_fw`）。
los52 比 los50 大的 4.9MB **全部来自 LTO/CFI 被恢复**（los50/51 是丢 LTO/CFI 的旧缓存 bug 版：
`LTO_NONE=y`/无 `CFI_CLANG`；los52 是 `LTO+THINLTO+LTO_CLANG+CFI_CLANG=y`，与 P3/工厂一致），固件载荷本身只有 0.4MB。

### 4. 真机 111 个开机模块的离线归类（服务 ⑤）

**62 个在我们内核里内建**（含 `goodix_fod` 屏下指纹、`nfc_i2c`、`ir-spi` 红外、`stmvl53l5`、`xiaomi_touch`、
`cyttsp5*`、`leds-qti-flash`、`qti_battery_charger_main` ⇒ ⑤ 的指纹/NFC/红外有内建驱动兜底）；
**39 个是我们自编模块**（音频全套、camera、rmnet_*、msm_drm）；**14 个两边都没有**（真机提供；其中
**`cs35l41_dlkm` = CS35L41 扬声器功放，我们根本没编** ⇒ 音频异常优先查它）。P3 的 v3 日志确认
`rmnet_data0..5` + `rmnet_ipa0` 都在 ⇒ 电话数据面内核侧通。

---

## ★★★★ 2026-10-10 10:2x 收尾⑥：**los58 / los59 产出并核验通过**（今晚用这两个，los52/54/55 作废）

| tag | 配方（相对 P3） | Image md5 | 模块包 md5 | 核验结论（`verify-tag.sh` + `extract-ikconfig`） |
|---|---|---|---|---|
| **los58** | P3 **+ 固件内建**（`firmware_embed`） | `2d4454ba858fa2adc451f5187b03e2a8`（43,674,112B） | `912e053c5eabae9507015f6f9c91a5a4` | ✅ `CNSS_UTILS=y`（WiFi 安全）、`ICNSS2=y`、`CNSS_GENL=m`、`WCNSS_MEM_PRE_ALLOC=m`、`EXTRA_FIRMWARE` 有、`LTO/THINLTO/LTO_CLANG/CFI_CLANG=y`；**与 P3 配置逐项对比只差 1 项**（自编 qcacld `QCA_CLD_WLAN=m`→未设置，无关） |
| **los59** | los58 **+ 蓝牙四项转模块** | `156e78bde76db741bb23c39b832206d9`（43,604,480B） | `61fcb5946f2a99b92bd1ff2f3c46c374` | ✅ `CNSS_UTILS=y` + `SLIMBUS=m`/`SLIMBUS_MSM_NGD=m`/`BTFM_SLIM=m`/`MSM_BT_POWER=m`（蓝牙修复生效） |

- CI run：los58 `38012926791`（artifact `los-kernel-75`）、los59 `38012935558`（`los-kernel-76`）；产物含 `Image`/`Module.symvers`/`System.map`/`build.log`。
- 149 直连 GitHub 会偶发 http 000 ⇒ 改在**本容器**下载（容器侧 API 正常）再 `ssh 'cat >'` 推给 149（`/tmp/push59.sh` 就是这个补推逻辑）。
- **作废**：los52/54/55（`CNSS_UTILS=m` ⇒ 没 WiFi）、los56/57（已 cancel）。详见 §41.85。

---

## ★★★★ 2026-10-10 23:0x 收尾⑦：**真机实测**（los61 为当前最优；相机/WiFi/清理已验证，音频仅剩声卡注册 -16）

| 项 | 结论 |
|---|---|
| ①电话 | **手机无 SIM**（`gsm.sim.state=ABSENT,ABSENT`）；内核侧 modem/IPA/rmnet/固件挂载全正常 ⇒ 无卡可测 |
| ②音频 | **音频桩必需（真机证实）**：los58 报 `mbhc_dlkm: Unknown symbol is_early_cons_enabled`；los61 带桩后整条链全装（含 cs35l41）。**但声卡仍注册失败**：`SLIMBUS_7_RX -517`（slimbus-ngd 开机没装上）→ 手动补装后 `register soundcard -16`（EBUSY）。`CONFIG_SND*` 与工厂逐项一致，无内建重复 |
| ③蓝牙 | `slimbus`/`bt_fm_slim`/`btpower` 均已装载（模块化修复生效）；能开/扫/连待验 |
| ④相机 | **✅ 修好**：`insmod camera.ko rc=0` + `/dev/video*` + **`dumpsys media.camera` = 10 个相机（3 normal）** |
| ⑤其它 | **清理 ✅**（唯一脚本 md5 `553e48be…`，5 个遗留移走，droidspaces 模块未动）；触感 ✅；指纹/红外待细查；NFC `-107` 异常 |

**los61** = P3 实际配置 + 固件内建 + 音频桩 + 蓝牙四项，`Image` md5 `bb92407f23f0a9266a90da75aac679f6`。

**两个必须记住的操作坑**：① 守护刷的是**未打 APatch 补丁**的镜像 ⇒ 无 root、无 WiFi 脚本 ⇒ 正确顺序是 fastboot 刷 GOLD（原厂+APatch）→ 再用
`flash-local.sh`/`flash-tag.sh` 刷我们镜像；② `flash-local.sh` 依赖 `/tmp/apatch-flash-generic.sh`（149 /tmp 被清过），已从 `scripts-mars/` 复制回去。

**音频下一步**：把 `slimbus` + `slimbus-ngd` 放到**音频 DLKM 之前**（`post-fs-data.d` 早期 insmod）以消除 `-517`；
若干净单次探针仍 `-16`，对比 stock/GOLD 同阶段的 `dmesg | grep -i asoc` 找重复注册的部件。

---

## ★★★★ 2026-10-11 00:5x 收尾⑧：④相机**持久化**验证通过 + ③蓝牙/⑤指纹实测 + los63 事故与 ASoC 补丁

| 项 | 结论 |
|---|---|
| ④ 相机 | **持久修复验证通过**：真重启后 v7 脚本自动 `insmod camera.ko rc=0`（日志 `C0) camera=1 个 / /dev/video*=4 个`），`dumpsys media.camera` **10 个相机**，crash 缓冲无新条目 ⇒ 唯一必需脚本升级为 **v7**（md5 `6a5d52475c5dfb4149c15ba074780497`），留档 `KEEP/2026-10-11-los61/` |
| ③ 蓝牙 | **能开 ✓**（`curState=OnState`）、**能扫 ✓**（`MSG_START_BLE_SCAN`/`start gattClientScanNative`）；能连待用户配对 |
| ⑤ 指纹 | HAL 健康（`Fingerprint21`、`isUdfps:true`、`HAL deaths:0`），录入需用户 |
| ⑤ 长稳 | `stability-watch` 已跑并记录（含两次刷机 boot_id 变化）；los61 `mods≈53` vs 原厂 112 = allbuiltin 的效果 |
| ② 音频 | los63（DEBUG_FS+DYNAMIC_DEBUG）**刷入后无法开机**（已用 GOLD 恢复），改走 **ASoC 补丁**：定位到 `snd_soc_add_controls()` 里的 `return err` 是 `-16` 致命出口，新增 `patches/asoc-dup-tolerant.py` 容忍 `-EBUSY`（与小米原厂行为对齐），派发 **los64** 验证 |

**两个必须记住的坑**（§41.88）：① 这台机器 **`adb reboot` 被静默忽略**，重启要用 `adb shell 'su -c reboot'`，判定用 `/proc/uptime`；
② 救援守护刷的是**未打 APatch 补丁**的镜像（无 root）—— 已部署 **v2 守护**（见 fastboot 先刷 GOLD 恢复 root，再 `flash-tag` 刷目标镜像 los61）。

---

## ★★★★ 2026-10-11 01:4x 收尾⑨：los65 音频补丁 v2（含 DAPM）仍差一步；相机时序优化生效

- **音频**：补丁 v2（`soc-core.c`+`soc-dapm.c` 都容忍 `-EBUSY`）刷入 los65 后，v1 里那条 `failed to add widget … dapm kcontrol … -16` **已消失**，
  但声卡仍 `failed to register soundcard -16`（45.5s）⇒ `snd_soc_instantiate_card()` 里**还有第三个 -16 出口**
  （可疑：card 级 `snd_soc_dapm_add_routes()`，日志里有 `msm-dai-fe: Failed to add route AUXPCM_*`；或 `snd_card_register()`）。
  tracefs 可用但 `function_graph` 没生效（疑似没开 `CONFIG_FUNCTION_GRAPH_TRACER`）⇒ 下一步用**显式 dev_err 打点**（`patches/asoc-trace.py`）最省。
- **④ 相机时序优化 ✅**：新增早期脚本 `post-fs-data.d/01-mars-camera.sh`（insmod hwid+camera），实测 **uptime≈40s 相机就绪**
  （此前要等 service.d 的 WLAN 段，~100s 后才装），`dumpsys media.camera` 仍 10 个相机。这不是 APatch 分阶段加载的锅，是我们把相机放在"晚阶段"。
- **开机时间根因（§41.92）**：`Freeing unused kernel memory`(13.3s) → `Run /init`(26.6s) 中间空转 **13.3s**，高度怀疑是我们
  logdump/moddbg 自救看门狗的"全任务状态转储+裸分区写"；叠加内核 init 阶段的 13.3s（987 个内建驱动的探测）。
  下一步出 `logdump=0` 版对比（顺带出打点诊断内核）。
- **当前手机状态**：跑 **los65**（WiFi ✓ / 相机 ✓（40s 就绪）/ 蓝牙模块 ✓ / 音频仍无声），唯一脚本 v7 + 早期相机脚本均已安装；
  留档以 `KEEP/2026-10-11-los61/`（v7 脚本）为准。

---

## ★★★★ 2026-10-11 05:0x 收尾⑩：los68 纯打点定位成功 —— **`-16` 出自 `snd_card_register()`（ALSA 核心）**

- **los68 = los61 + 17 处 `MARS-TRACE` 纯日志（零控制流改动）→ 正常开机** ✅（证明"纯打点"方案安全）
- dmesg 唯一关键行：`MARS-TRACE line=2213 ret=-16` → 映射到源码 = **`ret = snd_card_register(card->snd_card)`**
  ⇒ **排除**了此前所有"ASoC 控件/路由重名"的推断；`snd_soc_dapm_new_widgets()` 的返回值根本没被检查，也不是它。
- 现场：`/proc/asound/cards` 空、`/proc/asound/devices` 只有 `timer`、`/dev/snd` 只有 `timer`
  ⇒ 失败发生在整卡注册的最后一步，ALSA 的 `snd_register_device()` 发现 **`snd_minors[minor]` 已被占用** 就返回 `-EBUSY`。
- **下一步**：los69 = los68 + 在 `sound/core/sound.c:snd_register_device()` / `sound/core/init.c:snd_card_register()`
  插纯日志（打印 type/card/dev/minor 是否 busy）⇒ 定出"谁占了槽位"；若确认是"多次 defer 探针留下的残槽"，
  修法是让机器驱动**只探针一次**（先保证 SLIMbus 等组件就绪），而不是改 ASoC 控件列表（los67 已证会挂内核）。

---

## ★★★★ 2026-10-11 06:2x 收尾⑪：**循环重启真因锁定（非 trace 的 ASoC 容忍补丁）+ 两个 CI 假象已修 + 声卡失败全景**

**镜像血缘（本轮）**

| tag | 配方要点 | run | 结论 |
|---|---|---|---|
| los70 | los61 + `logdump=0`（**默认 extra_config 带 hung task**） | 380… | ❌ **470s 才进系统**，期间反复重启（用户手动进 fastboot）；但**开机耗时达标**：2.1s / 7.6s / 34.1s（原厂 9.1 / 14.2 / 37.6） |
| los71 / los72 | los61 + `logdump=1` + `wlan_debug=1`（ASoC **纯打点**） | … | ✅ 稳定；给出 `MARS-TRACE/2/3` 三级定位 |
| **los72（假）** | 同 los72，但 pcm.c 打点**编译失败** ⇒ job=failure，产物是旧对象拼的假 Image | 38089587857 | ⚠️ 被刷进手机，白跑一轮（行为=los71，**无 TRACE4**）⇒ 促成 CI 三处加固 |
| los74 | 同 los72 但 pcm.c 打点已修 | 38090756803 | 待刷：取 `MARS-TRACE4`（重复 PCM 的 owner） |

**结论 1（更正 §41.99）：循环重启与 hung_task 无关。** 三份镜像 `Image-los61/70/71` 的 `/proc/config.gz` **逐字节相同**（各 7002 行，diff 空）
⇒ 唯一差异是代码：los70 打的是**非 trace 版 ASoC 补丁（真的改控制流：把 -EBUSY 容忍成成功）**，los61/71 没有或只有纯打点。
⇒ 该"容忍式"补丁 = **开机重启循环元凶**（与 los67 硬挂同源）。**已把补丁步骤改成仅 `wlan_debug=1` 时打纯日志**（workflow `8bd50871`）。

**结论 2（CI 加固，防"假内核"）**
1. `patches/asoc-dup-tolerant.py`：pcm.c 打点里 Python `\n` 未转义 ⇒ C 字符串出现真换行 ⇒ 编译崩；已改 `\\n` 并本地验证（裸换行 0、括号平衡 0）。
2. `los.yml`：`Image/System.map/Module.symvers/modules.tgz` **只在 `success()` 上传**；日志改独立 `los-logs-<run>`（`failure()`）。
3. 下载器（`scripts/dl-run-all.sh`，已入仓）：run 结论 ≠ `completed success` ⇒ **拒绝下载**。

**结论 3（声卡全景，los71/72 的 dmesg 证据）**
- `populate_snd_card_dailinks` 被调 **7 次**（逐个异步 probe 的 macro：va→tx→rx→wsa），`TX_CDC_DMA_TX_5` 报 `-517` **6 次**（EPROBE_DEFER，等组件，非故障）；
- `msm-pcm-routing … failed to add widget … dapm kcontrol … -16`（**非致命**，注册流程继续）；
- `cs35l41 1-0040: PDN failed`；
- 终点：`snd_card_register()` → `-16`（`MARS-TRACE3 type=4`/`TRACE2 cardnum=0`/`TRACE line=2213`）⇒ `snd_pcm_add()` 同 card 同 device 撞车。
- **无任何音频模块落入 allbuiltin 撞名黑洞**；`q6core_audio`/`lahaina-asoc-snd`/`msm-dai-q6*` 都注册成功，全套 codec DLKM 全 Live。
⇒ 下一步：los74 取 `MARS-TRACE4` 的 `new(...) existing(...)` 名字/设备号，再做**定点**修（不再用全局容忍式补丁）。

**镜像/脚本留档**：`KEEP/2026-10-11-los61/`（Image `bb92407f23f0a9266a90da75aac679f6` + **99-wlan-mars.sh v7** `6a5d52475c5dfb4149c15ba074780497`，`md5sum -c` 5/5 OK）；
手机当前跑 los61（稳定，`boot_id` 采样递增）。救援守护 v2 在 149 常驻（fastboot → GOLD → los61），日志 `logs-mars/rescue2.log`。

---

## ★★★★★ 2026-10-11 06:2x 收尾⑫：声卡无声根因 = **机驱 link 表重复 `.id`**（MultiMedia10 与 Compress3 撞 `MSM_FRONTEND_DAI_MULTIMEDIA10`）

- **证据（静态，源码就在本内核树里）**：`techpack/audio/asoc/lahaina.c` = `machine_dlkm.ko` 源码。
  展开 `populate_snd_card_dailinks()` 会拼进卡里的 9 个数组 ⇒ **99 条 link，重复 `.id` 恰好 1 对**：
  `msm_common_dai_links[12] MultiMedia10` 与 `msm_common_misc_fe_dai_links[45] Compress3`
  都写 `.id = MSM_FRONTEND_DAI_MULTIMEDIA10`，且 `SND_SOC_DAILINK_REG(multimedia10)` 完全相同。
- **证据链（真机 dmesg）**：`num = dai_link->id`（FE 组件 `use_dai_pcm_id=1`）⇒ 同 card 同 device 两个 PCM
  ⇒ `snd_pcm_add() -EBUSY` ⇒ `device_register_all() -16` ⇒ `snd_card_register() -16` ⇒ `snd_soc_register_card() -16`
  ⇒ `probe ... failed with error -16` ⇒ `/proc/asound/cards` 空。
- **修法**：新增 `patches/asoc-pcm-renum.py`（只改 `soc-core.c`）——撞号时给后建的 PCM 换本卡第一个空闲 device 号，
  先建者保留原号（HAL 编号不变）；不碰控件/DAPM 控制流（los67 硬挂、los70 重启循环的教训）。
  本地已用真源码验证括号平衡/无裸换行/可与 `--trace` 叠加；**los76 = los74 + 该修复**（run `38091499791`）。
  （los75/run `38091146216` 因"推补丁时被 `&&` 短路漏推"而失败，下载器的"非 success 拒收"挡住了假 Image；已补推并回读 md5 核对。）
- **CI 三处加固（同轮）**：pcm.c 打点裸换行修复、产物仅 `success()` 上传 Image（失败只传 `los-logs-*`）、
  下载器拒绝非 success run（见 §41.100）。补丁步骤改为**仅 `wlan_debug=1` 打纯日志**。

---

## ★★★★★ 2026-10-11 07:5x 收尾⑬：fastbootd 陷阱、音频模块三份血统、`/vendor` 只读、renum 会崩、第二轮打点已派发

- **fastbootd 陷阱（重要）**：手机连续启动失败会掉进 userspace fastboot（USB `18d1:d00d`），那里
  `fastboot flash boot_a` 报 `OKAY` 却**不写分区** ⇒ 救援守护 v2 死循环。修法：先 `fastboot reboot bootloader`
  再刷；已写 **`rescue-daemon-v3.sh`**（`getvar is-userspace` 自动切换）。本轮手动恢复一次成功。
- **音频模块三份血统**：顶层 `/vendor/lib/modules/`（**实际装载**）= **我们早期构建**（dmesg 无 vermagic 警告，
  但不等于 los50+ 的任何 tgz）；`5.4-gki/` 与 `~/mars-build/tmp/kostrip/`（库存 stock，vermagic `5.4.233-qgki`）各一套。
  ⇒ 音频栈是"我们的机驱/platform + 原厂的 codec/swr/stub"**混装**。库存 29 个音频模块已打包
  149 `artifacts/stock-audio-ko.tgz`（md5 `a392d765692931cc6b9fcfa19eaaca7d`）并推到手机 `/data/local/tmp/stock-ko/`。
- **`/vendor` 是 erofs 只读**（dm-9），不能换文件 ⇒ 只能 overlay/运行期 rmmod+insmod/改内核。
- **运行期换原厂 machine_dlkm.ko**：rc=0、probe 跑到 `populate_snd_card_dailinks` 与
  `failed to init link AUX_PCM_RX: -517`，**不崩**；但静态环境下 deferred-probe 不重试 ⇒ 声卡仍空（待开机时验证）。
- **renum 路线证伪**：los76/los77 = 声卡能注册，但系统 ~65s 后崩/循环（USB 窗口仅 8–9s），los77 掉进 fastbootd。
  ⇒ 已从 workflow 移除 renum 步骤（补丁留档）。
- **第二轮打点 los78**（run `38096314070`）：`MARS-USEID`（谁触发 use_dai_pcm_id）+ `MARS-NUM`（每条 link 的 PCM 号）
  + `TRACE4` 打印指针与 `pcm->id`。静态已查明：LOS/star 两棵树**没有任何文件设置 `use_dai_pcm_id`**
  ⇒ 高度怀疑**跨模块结构体 ABI 不一致**（原厂 5.4.233 模块读出的位是垃圾）⇒ los78 会点名那个组件。

---

## 2026-10-11 08:0x 收尾⑭（交接轮）：**交接文档已重写** → [`docs/mars-NEXT-HANDOVER.md`](docs/mars-NEXT-HANDOVER.md)

用户要在本轮切换模型 ⇒ 已把 **`docs/mars-NEXT-HANDOVER.md` 全量重写**为单页可执行交接（2026-10-11 08:0x 版）：

- 目标完成度表（①~⑤，含"缺 SIM/需配对设备/需人录指纹"这类只能人做的事）；
- **现行镜像矩阵**（los61=唯一推荐；los70/74/76/77/78/79 各自能刷不能刷的原因与 run id）；
- **GOLD 派发 JSON**（25 输入已满 ⇒ 新开关只能走 `extra_config`；`RENUM` 标记才打 renum 补丁）；
- **音频问题完整证据链**（`MARS-TRACE/2/3/4`、99 条 link / 17 条无 `.id` / MultiMedia10≡Compress3 重复 id、
  `/vendor` 三份模块血统、erofs 只读、renum 会崩、原厂机驱 -517 不退）；
- **两个候选根因 (A) 跨模块 ABI 不一致 / (B) rtd->num 撞号**，以及 los78 三行日志如何二选一；
- **下一步具体动作**（读 los78 → 读 los79 panic → 补验 `logdump=0` 单变量 → 出声双验收）；
- 11 条坑清单（fastbootd 假刷、erofs 只读、假 Image、流水超时、USB 8–9s 窗口、mi_syms_audio、wlan-prep 等）；
- 手机侧脚本/deploy 规矩、交付物清单、以及用户原话目标。

**本轮已做但未取回结果的实验**（下一个模型直接看日志即可）：
- **los78 = run `38096314070`**（los61 + `wlan_debug=1` 第二轮打点）⇒ 日志 `logs-mars/los78-run.log`，
  关键 `MARS-USEID` / `MARS-NUM` / `MARS-TRACE4`。
- **los79 = run `38096679132`**（los61 + `RENUM` + `logdump=1`，抓"卡注册后崩溃"的 panic）⇒
  日志 `logs-mars/los79-run.log` + `evidence-mars/crash-1011-los79/`。
- 安全网已升级：**`rescue-daemon-v3.sh` 正在跑**（识别 fastbootd 并先 `reboot bootloader`，再刷 GOLD → los61）。

---

## ★★★★★ 2026-10-11 08:0x 收尾⑮：los78 定案 + **声卡真修已实现并派发（los80）**

- **los78（run `38096314070`）决定性数据**：`MARS-USEID` 点名 **`msm-stub-codec` 设置了 `use_dai_pcm_id=1`**；
  `MARS-NUM` 显示 `MSM AFE-PCM RX/TX`（stream=AFE-PROXY RX/TX）`rtd_num=5/6 但 num=0 id=0`，
  而 `Media1 rtd_num=0 num=0 id=0`；`MARS-TRACE4` 打印冲突双方：
  `new=AFE-PROXY RX msm-stub-rx-0` vs `ex=MultiMedia1 (*)`，都是 card 0 / dev 0。
  ⇒ **根因定案**：机驱表里 AFE-PROXY RX/TX 没写 `.id`（默认 0），`MSM_FRONTEND_DAI_MULTIMEDIA1` 也 =0 ⇒ 抢 PCM 0 号
  ⇒ `snd_pcm_add -EBUSY` ⇒ `snd_card_register -16` ⇒ 无声卡。（原厂 machine_dlkm.ko 给这些 link 写了各自 id。）
- **修复 `gh/patches/asoc-pcm-numid-fix.py`**：`soc_link_init()` 里改成 `if (no_pcm) num += be_pcm_base;
  else if (dai_link->id) num = dai_link->id; else 保持 num = rtd->num`（id==0 视为未指定）。只改设备号计算、不碰控制流。
  已并入 workflow 固定步骤；**los80 = run `38097268667`**（los61 配方 + `wlan_debug=1` + 本修复），
  流水 `logs-mars/los80-run.log` 会在 los79 收工后自动刷并验收（`/proc/asound/cards`、`tinyplay`、boot_id 稳定性）。
- **los79 = run `38096679132`**（`extra_config` 带 RENUM + `logdump=1`）用来抓"卡注册后 ~65s 崩"的 panic。
- **红旗**：`cs35l41`（原厂 5.4.233 模块）读出 `driver->name = NULL`、`be_pcm_base = -34` ⇒ 其 `snd_soc_component_driver`
  布局可疑，会影响 BE link 设备号；若 los80 后仍有异常优先处理。
- **交接文档已重写**：`docs/mars-NEXT-HANDOVER.md`（含 §4.4 本节内容、镜像矩阵、派发 JSON、坑清单、下一步）。

---

## ★★★★★ 2026-10-11 08:30 收尾⑯：los79 解密 —— **声卡能注册了**；"循环重启"是 logdump 自救，不是 panic；已派发 los81（logdump=0 + 真修）

- **los79（run `38096679132`，= los61 + renum + logdump=1）现场**：
  `round1.txt` 里 `/proc/asound/cards` = **`0 [lahainamtpsndca]: lahaina-mtp-snd - lahaina-mtp-snd-card`**，
  dmesg `[42.627] msm_asoc_machine_probe: Sound card lahaina-mtp-snd-card registered` ⇒
  **换号后整卡注册成功**（首次在真机见到声卡）；`MARS-PCM-RENUM` 显示 **~25 个 PCM** 被换号（FE 3 条 + TDM/CDC DMA/VA DMA/Slimbus7 等
  BE 一串 —— 后者是 `cs35l41` 的 `be_pcm_base=-34` 歪号导致）。
- **"~65s 循环重启"真凶 = logdump 自救看门狗**（`[64.268633] logdump: logdump-rescue:`；逻辑：
  64s 内日志里没见 USB 枚举 ⇒ dd golden→boot_a + reboot）。ld.bin 里**没有 panic** ⇒ **不存在"卡注册就崩"**。
- **⇒ 赢的配置 = 声卡号修复 + `logdump=0`**：已派发 **los81 = run `38098882088`**（los61 配方 + `logdump=0` + `MARS-NUMID-FIX`），
  流水 `logs-mars/los81-run.log` 自动刷 + 双验收（`tinyplay` 直通 + 框架播放）+ 开机里程碑 + 稳定性。
- 备选（若要留 logdump 的记录能力）：把自救关掉或延后（`logdump.logdump_rescue_slot=0` 或阈值 >120s）。

---

## 2026-10-11 09:0x 收尾⑰：补一个"组合候选" los82 + 无人值守验收已就位（手机等用户回来）

- **为什么还要 los82**：§收尾⑯ 的 renum 日志证明 **BE 也在撞号**（`cs35l41` 读出的 `be_pcm_base=-34` 把 BE 号算歪：
  Tertiary TDM0/1、RX CDC DMA0–6、TX CDC DMA3/4、VA CDC DMA0–2、Slimbus7 共 ~22 条），
  而 **`MARS-NUMID-FIX` 只治 FE（`id==0`）** ⇒ 用 renum 的"号唯一化"兜住 BE。
- **los82 = run `38100355889`**：los61 配方 + `logdump=0` + `MARS-NUMID-FIX`（无条件步骤）+ renum（`extra_config` 带 `RENUM`）。
- **无人值守验收**：149 `/tmp/los82-run.sh`（留档 `scripts/149-los82-run.sh`，日志 `logs-mars/los82-run.log`）：
  等手机（≤12h，用户回来进 fastboot 即可，`rescue-daemon-v3` 先恢复 los61）→ 先刷 **los81** 全套验收 →
  若无声卡再刷 **los82** 全套验收（声卡/tinyplay/框架播放/开机里程碑/boot_id 稳定性/WiFi+相机）。
- 手机当前仍是"USB 无枚举"（用户出门、无法手动进 fastboot）⇒ 本轮无法再取真机数据；**下一个模型第一件事就是读
  `logs-mars/los82-run.log`**（见 `docs/mars-NEXT-HANDOVER.md` §4.6）。

**（09:20 补记）** los82 已构建完成并落到 149：`Image-los82` = 43,604,480 B；CI 步骤真值确认
**RENUM 步骤 success + NUMID-FIX 步骤 success**（= `logdump=0` + FE 修复 + BE 号唯一化兜底）。
无人值守流水已确认"los81/los82 都到货"，现处于 **"等手机恢复（≤12h）"**；
`scripts/149-los82-run.sh` 已加"每次刷机前等就绪（各 30min）"，并已留档。手机仍待用户回来进 fastboot。

**（09:24 补记 2）** 无人值守流水已加 `finalize()`：验收通过即 **自动 `keep-tag.sh <tag>` 留档（含 `md5sum -c` 校验）**
+ 后台起 **6 小时长稳**（`stability-watch.sh 6 600`），结论写回 `logs-mars/los82-run.log`
⇒ 目标里"留存并 md5 校验"与"长时间稳定性观察"两条会随验收自动完成。

**（09:25 补记 3）** 无人值守流水改为 **los82 优先**（`logdump=0` + NUMID-FIX + 号唯一化兜底），
los81（只 NUMID-FIX）留作对照 —— 依据：los79 的 renum 日志显示 BE 那 ~22 条也会撞号，单靠 FE 修复预期不够。
成功即 `finalize()`（留档 + `md5sum -c` + 6h 长稳）。

**（19:5x 补记）** 用户回来实测：los82 四次进 MIUI 但每次 3–5 秒后重启 ⇒ 判定为**用户态**（很可能厂商音频 HAL）
被 renum 挪过的 PCM 编号搞崩。已改方向：`MARS-NUMID-FIX` 增强版（`id==0` 回退 `rtd->num` + 净化
`be_pcm_base=-34` 垃圾值），**不再用 renum**；派发 **los84 `38136808254`**（logdump=0，候选）与
**los86 `38136868466`**（logdump=1+打点，取证）。流水 `logs-mars/los84-run.log` 无人值守验收+留档+长稳。

---

## ★★★★ 2026-10-11 20:40 收尾⑱：los87 起不来 ⇒ 定论"卡能注册，但带声卡的开机会卡死在音频路径"

- **los87（run `38138603227`，logdump=0 + 打点 + 增强修复）**：刷入后**只到 MIUI 三个点**就被重启、循环。
- **los86（run `38136868466`，同修复 + logdump=1）**现场：`[45.8] Sound card lahaina-mtp-snd-card registered`
  → `[48.7–50.8] usb_audio_rx/tx_*` 控件被读写 → **内核日志静默 ~16s** → `[67.07] logdump-rescue:`（自救 dd+reboot）。
- ⇒ **病根**：卡一注册 ⇒ 音频路径把启动卡死（到不了 boot_completed）；带 logdump 的被自救看门狗提前打断（~65s 循环），
  不带的被 MIUI 启动失败保护重启（los87 三点循环）。
- **"让声卡注册"已证明可行**（los79/los86 都有 `Sound card registered`），修复也已做到编号贴近原厂；
  **"带声卡 + 能开机 + 出声" 卡住**，超出配置级修复范围。两条干净替代路线也堵：`/vendor` erofs 只读、
  原厂 `machine_dlkm.ko` 在我们内核上 `-517` 装不上。
- **已恢复**：亲手刷 GOLD → **los61**（稳定：boot_id 不变、WiFi `192.168.1.145`、`camera` 已装 27 引用、`dumpsys media.camera` 正常）；
  **按用户要求已停掉所有守护/流水**（`ps` 确认 0 个），手机侧脚本仍是 {`00-mars-slimbus.sh`,`01-mars-camera.sh`,`99-wlan-mars.sh`}，`/data/adb/modules` 未动。
- **下一轮线索**（见 §41.106）：① 关内建 USB 音频 gadget 让原厂 `u_audio.ko` 能装；② 编出同源 cs35l41；③ 用 logdump 的"日志停涨全任务栈"抓卡死点。

**（21:0x 补记）** **los88（run `38140777358`，= los87 + 关内建 UAC2）仍然卡在 MIUI 三个点**（这次 5–6 轮后重启）
⇒ "内建 `u_audio` 抢符号" 假设被证伪。**音频最终定论**：卡能注册（已证明），但带声卡的开机会在音频路径卡死
（los86 现场：`usb_audio_*` 控件被读写后内核日志静默），且两条干净路线（原厂模块 / `/vendor` 换文件）都被堵
⇒ 需要厂家 DLKM 源码级调试，超出本轮配置级修复范围。**交付版 = los61**，已亲手刷回（21:12 进系统，槽 `_a`），
并按用户要求不再挂任何常驻守护/流水。

---

## ★★★★★ 2026-10-11 21:2x 收尾⑲：**音频卡死真凶 = 原厂 cs35l41 驱动无限刷 DSP 日志**（我们内核里根本没有 cs35l41）

- 用已有 los86 dump 零成本定位：50.3s 之后不是"静默"，而是**几十万行 `cs35l41 1-0042: DSP1: …`**（固件下载死循环）。
  ⇒ 卡一注册 → HAL 初始化功放 → 原厂 cs35l41 驱动跑飞刷屏 → printk/控制台堵死 → 启动推进不下去 → 被
  logdump 自救（64s）或 MIUI 启动失败保护重启。**与 renum 编号、内建 UAC2/`u_audio` 均无关**（已分别证伪）。
- 我们构建里**完全没有 cs35l41**：`strings Image-los88 | grep -ci cs35l41` = 0、`los88-modules.tgz` 里也没有；
  而源码在树里（`techpack/audio/asoc/codecs/cs35l41/`）、`Kbuild` 里也有 `obj-y += cs35l41/` ⇒ **没编进产物**。
  加上 `MARS-USEID` 读到 `cs35l41` 的 `name=NULL/base=-34`（struct 读数不对）⇒ 判定 **ABI 不匹配**。
- **下一轮首选修法**：把树内 `cs35l41` 编出来（内建或独立模块），用同源驱动替掉原厂那份 ⇒ 期望"刷屏消失 + 带卡开机 + 出声"；
  备选：先把 `TERT_TDM_RX_0/1`（cs35l41 所在的 BE link）从机驱表去掉/改 `no_pcm`，牺牲外放先拿可用声卡。
- 另：本轮还免费试了"开机早期换原厂 `machine_dlkm`"（`post-fs-data.d/02-audio-stock-try.sh`）：能加载、能 probe，
  但**永远卡在 `AUX_PCM_RX: -517`**（踢 12 次 deferred-probe 无效）⇒ 原厂那张表在我们内核上建不了卡，此路封死。

---

## ★★★★★ 2026-10-11 22:0x 收尾⑳：**los89 = cs35l41 内建修复（抢占原厂功放驱动，解决音频卡死真凶）**

- **修法**：`gh/patches/cs35l41-build.py`（推 `7dff204e`）+ workflow 加无条件步骤（推 `204c78b5`）。
  三处改动：① `codecs/Kbuild` 拆 `TARGET_PRODUCT` 门；② `cs35l41/Kbuild` 强制 `obj-y` + TDM 宏；
  ③ `lahainaauto.conf` 设 `CONFIG_SND_SOC_CS35L41=y`（内建）、`CONFIG_SND_EVENT=y`。
  ⇒ 我们的 cs35l41 与 5.4.242 内核同头文件，ABI 一致；原厂的 `_dlkm.ko` 因"already registered"被拒。
- **los89 = run `________`**（`logdump=0` + cs35l41 内建，开机应 ~34s）—— 流水 `logs-mars/los89-run.log` 自动刷 + 验收。
- **已知的风险**：cs35l41 的 VPBR/DAI 名取决于 mars vs star 血统；`TARGET_PRODUCT_STAR` 宏已硬打。
  若功放仍跑飞（DSP 仍刷屏），下一条路是直接在 lahaina.c 里把 `TERT_TDM_RX_0/1`（cs35l41 BE link）改成 `no_pcm = 1`。
- **已证伪/封死的路**：renum（los82）、关 UAC2（los88）、换原厂 machine_dlkm（永远卡 AUX_PCM_RX: -517）、
  改 `/vendor`（erofs 只读）、容忍 -EBUSY（los67 硬挂）、logdump 记录（自救看门狗 64s 重启）。

---

## ★★★★★★ 2026-10-12 06:0x–07:0x 收尾㉑：**根因大修正 —— 真凶是"PCM 编号垃圾"，DSP 刷屏/卡死均系误判；MARS-STOCKNUM 总修复（los92）**

### 三个决定性取证（全部推翻 收尾⑲/⑳ 的"cs35l41 DSP 刷屏"结论）
1. **"几十万行 DSP1 刷屏"不存在**：los86 的 `evidence-mars/crash-1011-los86/ld.bin`（37MB 全量日志）里
   `DSP1` 仅 **1300 行**、`Algorithm ID` 仅 **8 行**（两颗功放各 2 个算法）——是**正常的固件装载**
   （`cs35l41-dsp1-spk-prot-revb2-mars.wmfw` 解析正常，region/TIMESTAMP 都对）。⑲的"几十万行"是误读。
2. **los86 根本没卡死**：body.txt 显示 65.535s `android_work: sent uevent USB_STATE=CONFIGURED`、
   67.3s 蓝牙开启（BTON）、触屏(FTS)/QSEECOM 全程活跃——**系统在正常推进**（只是比 los61 慢一倍），
   是 **logdump 看门狗在 67s 误杀**（判据只认 USB 枚举痕迹，而收集缓冲被日志涨满截断、漏看了 65.5s 那行）。
   与 §4.5 los79 的定论（"~65s 循环是自救不是 panic"）同款误判。
3. **原厂编号机制被彻底解明**（二进制解析 `stock-ko/machine_dlkm.ko` + 源码对照）：
   - 原厂表里 `MSM AFE-PCM RX/TX` 的 `.id` **同样是 0**（重定位解析实锤）⇒"原厂给这些 link 写了 id"不成立；
   - LOS 源每条 link 都有 `{/* hw:x,N */}` 注释 = **原厂 PCM 设备号真值**；与表序对照 ⇒
     **原厂编号 = 纯 `rtd->num`**（VoiceMMode1 id=50 但原厂号=2、Compress2 id=6 但原厂号=11、
     MM10/Compress3 的 id 还都是 9 ⇒ `num=id` 必撞）；
   - `use_dai_pcm_id`/`be_pcm_base` 覆盖路径**原厂从不触发**（stub 源码 `msm_dai_stub_component` 只写 `.name`，两字段=0）；
     但它在我们核上被**ABI 错位垃圾值误触发**（los78 实测 stub 读出 1、cs35l41 读出 `be_pcm_base=-34`）
     ⇒ FE 抢 device 0、BE 号算歪 ⇒ 撞号 ⇒ `snd_card_register -16` ⇒ 无声/半残。

### 修复：`gh/patches/asoc-pcm-stockmap.py` + `gh/patches/mars-stock-map.txt`（MARS-STOCKNUM）
- 编号策略一步到位：①一律 `rtd->num` 为基（=原厂真实行为）；②按**原厂基准表 50 条**（`hw:x,N` 提取）
  `stream_name→设备号` 精确归位；③唯一性兜底（互斥变体 32/33/44/45 同号/未收录 ⇒ `200+rtd` 高位号）。
- 与原厂编号逐条一致 ⇒ HAL 按原厂号开 PCM 不再崩（los82 实证"HAL 依赖原厂编号"）。
- workflow 改造（推 `3f28ab8b`/`59515a7e`/`3523f4ed`）：`MARS-STOCKNUM` 步骤**取代** numid-fix/renum 全套；
  **停用 cs35l41 内建步骤及闸门**（los90 硬挂头号嫌疑 + 真凶已另案；改回用原厂 `cs35l41_dlkm.ko`）。
- **los92 = run `38182166441`（#113）** = GOLD 配方 + `logdump=1` + MARS-STOCKNUM；149 全自动链
  （救援 v3b：fastboot→GOLD+**原厂音频基准抓取**→los61；等待器：→取证→自动刷 los92→四条验收）。
- los90（cs35l41 内建版）**硬挂**（35min 无任何 USB 活动）——产物侧已核对 cs35l41=83/snd_event=15/wm_adsp=31
  全内建 ✓ ⇒ 运行时问题，内建 cs35l41/snd_event 为头号嫌疑，los92 起停用。
- **旧结论作废清单**：⑲"cs35l41 DSP 刷屏真凶"、⑳"同源 cs35l41 内建=赢法"、§4.4"原厂靠 .id 编号"、
  §4.4b"卡一注册音频路径就把启动卡死"。los86 实为**慢而正常**的启动被看门狗误杀。

## ★★★★★★ 2026-10-12 12:3x–13:0x 收尾㉒：los92 真机首轮结案 —— **音频大跃进** + "无通道自锁"循环；"谁刷了机"结案；149 守护清查

### A. 事件时间线（全部有 log 实证）
| 时刻 | 事件 | 证据 |
|---|---|---|
| 05:30 | #17（los90/91 系，Oct 11 21:22 构建）开机，稳跑 7h（无 USB、WiFi 后补） | `[adb]` waiter phase2 |
| 12:35:47 | **等待器链自动刷 los92**（boot md5 `55a9344d…` 回读一致） | `los92-run.log` + `flash-los92.log` |
| 12:35–12:38 | los92 "一进系统就重启" 循环（≈106s/轮） | `[目]` 用户 |
| 12:38:42 | 用户进 fastboot → **v3b 救援守护按设计刷 GOLD**（7.159s） | `rescue3.log` |
| 12:5x | 等待器+flash-tag 停链（防再刷）；GOLD 稳定态 | 本会话 |

### B. logdump 分区（sde59, 64MB）取证 —— 刷 boot_a 不碰它 ⇒ los92 现场全在
7 个 `KLOGDMP4` 快照：0MB 主区 / 32MB=55s / 36MB=4s / 40MB=11s / 46+50+54MB。
50 处 `MARS-STOCKNUM` 打印 ⇒ **循环版=los92 实锤**；`rescue行=0` ⇒ logdump 自救**从未触发**
（被 `02-mars-nologrescue.sh` 关掉）⇒ **循环 = MIUI 用户态 ~106s"启动失败"重启**，非 panic、非自救。
转储止于 55s、无 panic/powerctl 指令行；GOLD 上 `/sys/fs/pstore` 空（root 也空）与此一致。

### C. ★los92 音频侧大跃进（P3/los61 从未达到）
- `cs35l41 1-0040/1-0042 i2c probe` **成功**（Cirrus Logic CS35L41 (35a40) Revision B2，两颗）；
- **DSP1 固件装载 + ~190 个 ALSA control 创建**（"DSP1 刷屏"765 行=一次性初始化爆发，非无限刷）；
- `populate_snd_card_dailinks` 已在跑（声卡构建中）+ `wcd938x_codec … variant 0` + `wcd_mbhc_init`；
- MARS-STOCKNUM 重映射工作正常（stock#44/45 占用/未收录 ⇒ 高位兜底）。

### D. los92 失败画像（"无通道自锁"）
| 症状 | 行 | 判 |
|---|---|---|
| USB gadget | `udc a600000.dwc3: failed to start g1: -19`（52.7s 起每秒重试） | dwc3/PHY 被拦（AGENTS.md 白名单坑同款） |
| WLAN | `wlan: Unknown symbol cnss_qmi_send/cnss_idle_shutdown/cnss_idle_restart` | 原厂 `cnss2.ko` 未装上 ⇒ qca_cld3 挂 |
| HAL | `Could not find ISensorManager/default` | 传感器 HAL 未注册 |
| 显示 | `dsi_display_init [msm_drm] *ER`（27s） | 待查 |
⇒ 判定启动失败 ⇒ 106s 用户态 reboot ⇒ 循环（**无任何通道**，只有 logdump 分区可取证）。

### E. 构建身份三分（banner + STOCKNUM 串实锤）
los61=`#8 Oct 10 15:07`（无 STOCKNUM）／7h 版=`#17 Oct 11 21:22`（第三版）／**los92=`#18 Oct 11 23:07`**（STOCKNUM ✓）。
los92 **真实构建 config**（IKCONFIG 内嵌流 zlib 解出）：`CNSS_UTILS=y` `CNSS_QCA6490=y` `CNSS2=m`
`CNSS_GENL=m` `WCNSS_MEM_PRE_ALLOC=m` `ICNSS2=y` `PSTORE_RAM=y` ⇒ **没踩 CNSS 坑**，wlan 符号缺失另有原因（下轮查原厂 cnss2.ko 在 los92 上的 insmod 失败点）。

### F. 149 守护全面清查（用户指令：非我建立的一律删）
全量盘点 `ps`/`crontab`/`cron.d`/`systemd`(system+user)/`init.d`/`rc.local`：**无任何外来守护**；
火星相关仅两个且均为本 AI 建立：`rescue-daemon-v3b.sh`（**保留**，救机用）+ 无线抢窗循环（已杀，使命完成）。
cron 仅用户 quant 任务与系统项（不动）。

### G. 内核模块答复（用户"应该只有一个模块"）
开机 **0 insmod**（allbuiltin=1 全内建）；运行时唯一 insmod 组 = **原厂 WLAN 栈 2 个 .ko**
（`cnss2.ko` → 等 CBC → `qca_cld3_wlan.ko`）= 一个栈。内核内嵌"看门狗"= logdump（built-in，我方补丁）；
下版（los93）把**自救/自重启默认关**（仅保留取证快照），彻底消除"内核自主刷机/重启"。

### H. 下一步（los93 = 保 STOCKNUM + 拆自锁）
一次一项：①修 USB `-19`（dwc3/PHY 门禁面）→ ②修 wlan 符号链 → ③拆 logdump 自救 → 逐版验收四条。

### I. 收尾㉒续(13:0x-13:2x):死亡机制收敛 + los93 派发
- **bootstat 重启史**（跨重启存活）：`reboot,shell`(05:30 #17 开机)→`reboot,shell`(12:36 los92 开机)
  →**裸 `reboot`**(12:38:14 记录,boot#1 自然死亡)→`reboot`(12:39:08 GOLD)。
  **★时序修正(13:3x)**：bootstat +6s 模型(#17 校准)定 boot#1 内核起点 ≈12:36:43 ⇒
  wtf(12:37:10-17)=启动后 27~34s(**中期噪声,非死前**——此前映射有误); 55s 快照=12:37:38;
  **死亡 ≈12:38:02(uptime ~85s±5s)**。⇒ 非崩溃级联的证据来自:无任何崩溃工件+裸 reboot 记录+无 RESTART 转储。
  ⚠️ 死亡点正落在 los93 快照梯(75/85s)边缘:若死亡 <85s, 85s 快照缺席, 75s 快照(内容覆盖~45-75s)
  是最后现场——仍可能含 bark(咬口前 5-11s 打出)或卡死任务初形; 若不足, los94 加密梯/末口气复用槽。
- 用户态证据全清白：dropbox 无 crash/watchdog 条目、tombstones 无今日条目、ANR 无窗口内条目、
  MIUI `stability/reboot` 归档只到 10-08。
- **restart 转储缺失 = 关键证据**：0MB 快照位内容=55s 现场（footer `uptime=55088ms`）,
  若走过 `kernel_restart/emergency_restart` 的 `kmsg_dump(RESTART)` 必覆盖为 85s 内容+RESTART 状态
  ⇒ **复位绕过了正常重启路径 ⇒ 硬件级复位(WDT 咬/PMIC PS_HOLD)嫌疑最大** `[?]`。
- **rescue 误杀假设二次排除**：44/48/52MB 快照 banner 全是 `#18`（los92）⇒ rescue 的 dd 未生效；
  0MB 状态块无 `slot-rescue` 标记 ⇒ rescue 未触发（`02-mars-nologrescue.sh` 疑生效）。
- wlan 链定性为良性噪声：`mars-wlan-block: refuse cnss2`（门禁设计内）+ 厂商 modprobe 漏放
  `qca_cld3_wlan` 单飞报缺符号；CBC 未到时 WLAN 本就不装。
- **los93 = run `38207025281`(#114)** 派发（`aca382a3`）：logdump 75s/85s **死亡窗口快照**(56/59MB)
  + 90s 检查点无条件打点 + **`logdump_rescue_slot` 默认 false**（用户指令:内核不得自主刷机/重启;
  cmdline `logdump.logdump_rescue_slot=1` 可显式开）。其余配方 = GOLD 配方原样（MARS-STOCKNUM 保留在 workflow）。
- 149 守护终态：唯一留存 `rescue-daemon-v3b.sh`（本 AI 建立,只对 fastboot 反应）；
  抢窗循环已杀；手机 service.d 被 v7/流程清理后只剩 `99-wlan-mars.sh`(v7, 7656B)。

### J. 死因机制锁定(13:2x):hh-watchdog(虚拟机级看门狗)咬口复位 [推理链闭合]
los92 快照 40MB 区的正常引导行揭示机制：
`hh-watchdog hypervisor:qcom,hh-watchdog: QCOM Apps Watchdog Initialized`(1.09s)+
`watchdogd`(pid150)/`hh-watchdog`(pid73) 喂狗线程 ⇒ **SM8350 的 apps 看门狗由 Gunyah 虚拟机管理器接管**。
咬口 = **hypervisor 直接硬件复位,完全绕过 `kernel_restart`/`kmsg_dump(RESTART)`**
⇒ 与 los92 三大死亡签名严丝合缝：①无 RESTART 转储(0MB 位仍是 55s 现场)
②干净重启(dropbox/tombstone/ANR 全清白) ③bootstat 只记裸 `reboot`(HARDRESET 也解析为 reboot)。
bark 阶段(咬口前 ~5s)会打出 "watchdog bark"+卡死 CPU 现场——落在 55~95s 未取证窗口
⇒ **los93 新增的 75s/85s 快照(56MB/59MB)正是为它准备的**,复现一轮即见真凶(卡死的任务/CPU/锁)。

### K. 音频 HAL 层新线索(13:2x): crus_adm 参数三连败(-22)
los92 死亡窗口前(50.7s)出现 Cirrus 智能功放 HAL 的 ADM 参数配置失败：
`crus_adm_get_params ret:-22` / `adm_pack_and_set_one_pp_param err -22` /
`crus_adm_set_params media format err -22`（一次性爆发,非循环）。
cs35l41 固件 `cs35l41-dsp1-spk-prot-{revb2-mars,RCV-revb2-mars}.bin` 直载 -2 → ueventd 兜底成功(DSP1 系数表解析正常)。
**嫌疑链**：crus_adm/HAL 参数被拒(疑似 PCM 重映射后 AFE/ADM 路由对不上) → 播放路径重试 →
I2C/AFE 死锁持住 CPU → hh-watchdog 咬口(§J)。los93 的 75/85s 快照(bark 现场)即可定谳；
若确认, los94 选项: (a)拦 crus HAL 重试 (b)修 AFE/ADM 路由 (c)关 cs35l41 运行期 IRQ。

### L. los93 复现+根因+los94 派发(13:3x-13:5x) ★音频无声卡谜题破案
- **los93(#19, run#114)真机表现**：**85s 死亡未复发**(uptime 708s+ 稳)、boot_completed=1、
  USB+无线双通道全活(los92 的 -19 gadget 故障也未复发)。**但 asound 无卡**。
- **logdump 新机制真机实证**：快照位点 9 个(0/32/36/40/44/48/52/**56/59**MB), 90s 检查点打点+75/85s 快照全落盘 ✓。
- **无声卡根因(三步锁死)**：
  1. `machine_dlkm`(ASoC 机器驱动)未装载 ⇒ `Unknown symbol wcd937x/938x_*`;
  2. 主编解码器 `wcd937x/wcd938x_dlkm` 未装载 ⇒ `Unknown symbol wcd_mbhc_*`;
  3. **`mbhc_dlkm` 未装载 ⇒ `Unknown symbol is_early_cons_enabled`(唯一缺口!)**。
  该符号由 workflow 输入 **`mi_syms_audio`** 注入(`patches/mi_syms_audio.c`,注释自证:"原厂 mbhc_dlkm 必需 ⇒ 有声卡")。
  **los92 的 Image 有此桩串、los93 的没有 ⇒ 派发 JSON 漏带 `mi_syms_audio":"1"`**(默认 0)。
- **los92/los90 死亡新理论**：los92=音频桩+同源 cs35l41 内建; los93=两者皆无 ⇒ 稳。
  ⇒ 85s 死亡疑凶=同源 cs35l41 内建(声卡注册后 HAL 初始化功放即死,§K crus_adm 三连败时序吻合)。
- **los94(run `38209506422`/#115)= los93 + 仅 `mi_syms_audio=1`**(cs35l41 内建保持停用)。
  若卡注册且稳 ⇒ 一举达成验收四条; 若 85s 死亡随卡回归 ⇒ 死因=音频初始化链实锤, los95 定点修。
- 证据保全:149 `~/mars-build/los93-evidence/{ld-los93.bin(64MB),los93-lg.tgz(末口气记录器 3.7MB)}`。
- 末口气记录器(`01-mars-lastgasp.sh`+`mars-lastgasp.sh`,3s/份 dmesg 持久化)为临时测器,los94 验收后移除。

### M. los94 死亡侦查全记录(14:1x-15:2x) ★排除法收窄
- **los94(#19+音频桩) = 85s±2 确定性死**(4+ 轮 boot_id 全不同,周期 83-85s,USB 窗口 67-85s)。
- **已排除**:
  1. crus_adm -22 失败链 → **GOLD 原厂同样 -22**(基准实证,良性噪声);
  2. /data 满/EXT4 损坏(sda33) → **los93 稳定 boot 同样 43 条报错**(慢性噪声; sda33=小分区非主 /data);
  3. 出声=死因 → **62s 主动 tinyplay 手机照活**(但抓到 `ADSP_EFAILED opcode 68557` + `no backend DAIs enabled` = **路由缺失,验收④的真实拦路虎**);
  4. 音频 HAL 内核 ioctl 挂死 → 每条 Enter 都有配对返回。
- **死亡特征**:85.19s 后零日志、pstore 空、无 watchdog bark、init 当时还在跑 gadget 配置
  ⇒ **硬件级复位**(PMIC/hypervisor 静默咬) 或 **85.2s 后的日志缺失**(快照窗口截断)。
- **待决**:85s±1 固定死线之谜(音频卡是必要条件: los93 无卡稳 20min+)。主嫌:ADSP 子系统
  在 ~85s 崩溃/SSR→恢复路径死锁→全核冻结;次嫌:音频用户态服务 85s 动作触发 init 重启。
- 实验工具:手机 service.d 注入脚本循环窗口自跑(02-fire-tinyplay.sh=62s 开火 / SIGSTOP 音频进程实验)。
- 85s 死亡时序与"开机完成(73.4s 杀 bootanim)后"强相关,但与"第一声出声"无关。

### N. 音频守卫攻防(v1-v5) + 凶手画像(15:3x-16:3x)
- **SIGSTOP 全冻结 = 稳**(实验轮 717s+/v2 自杀冻结轮同样稳) ⇒ 死因在音频用户态进程的"活动"。
- **冻结@75s-68s → 解冻即死, 且死亡点紧跟解冻**:
  v1 全解@120 → 死; v3 逐解@115-145 → 死; v4 EARLY 解@115-130 → 死; v5 首解@350(ozo) → 15s 内死。
- **但实验轮 440-643s 逐个解冻全员安然**(misound@440→ozo@490→HAL@525→audioserver@570→rpcd@635)。
  ⇒ **毒性有"成熟期"**: 开机后约 440s 内唤醒音频进程=必死; 490s+ 唤醒=安全(待 v6 复核 366→490 边界)。
- 画像: 音频链某进程(ozo/audioserver 嫌疑最大)恢复后执行"开机时排队的初始化", 该路径在我们核上
  直接触发硬件级复位(零日志/pstore 空/无 bark); 开机超过 ~440s 后同样的恢复无害(队列已作废/超时)。
- 工具演化: 98-mars-audio-guard.sh v1→v5(冻结/解冻时刻二分), 自杀坑: 脚本名含 audio 会被自己的
  `*audio*` 匹配冻结(v2)。本轮守卫最终版待定(v6=解冻≥490s)。
- 当前实验态: 手机 los94, 全音频进程冻结, 声卡注册✓ boot_completed✓, 守卫已掐, 待 600s 手动解冻验证。

### O. 音频路由全栈取证(17:0x-17:5x) — ④的真凶定性
- **扬声器配方到手**(手机 `/vendor/etc/audio/sku_lahaina/mixer_paths.xml` "speaker" 路径):
  扬声器 = **WSA_CDC_DMA_RX_0**(不是 TERT_TDM!)+ `WSA RX0/1 MUX=AIF1_PB` + `WSA_RX0/1 INP0`
  + `WSA_COMP1/2` + `SpkrLeft/Right COMP/VISENSE/SWR DAC_Port` 全套开关。mars 双功放 cs35l41@1-0040/1-0042
  (DSP1 diag 固件装载成功, 双通道应答正常)。
- **tinyplay 全链失败三层**(每次稳定复现):
  ① `q6asm_callback: cmd=0x10bcd ADSP_EFAILED`×2(最先); ② `LAHAINA Media1: no backend DAIs enabled`
  (FE→BE 路由注册不上——16 个 FE 全试、按索引写双值、照抄 speaker 配方, 全部无效; mixer 读回恒 "On Off");
  ③ 部分路径 AFE port start `-22`(通道掩码 0x0: `MultiMedia1 Output Channel Map` 默认全零)。
- **TERT_TDM/功放路径 = 秒级硬件死**: tinymix 开路由安全, 但 PCM open(DAPM 上电功放)<0.5s 硬复位
  (零日志/pstore 空), **静音波形同样死** ⇒ 与信号幅度无关, 死在功放上电序列。
- **GOLD 对照**: 声卡注册日志与我们逐字一致(同 17 条 Failed to add route/同 TX_CDC_DMA_TX_5 -517×2/
  同 populate×3) ⇒ 注册无差异, 问题在运行期。
- **根因定性**: 原厂音频 DLKM 全家(machine_dlkm/platform_dlkm/q6_dlkm/cs35l41_dlkm/宏们)系 5.4.233 编译,
  在我们 5.4.242 内核上 **struct 字段读出垃圾**(MARS-STOCKNUM 补丁注释实锤: stub use_dai_pcm_id=1、
  cs35l41 be_pcm_base=-34)——编号已被 MARS-STOCKNUM 修, 但路由 ID/DAPM/功放配置同样在被污染 ⇒
  kcontrol put 不生效(no backend DAIs)+ 功放上电序列错乱(秒死)。los90/92 的 cs35l41 同源内建没治好
  (只换了 codec, CPU DAI/machine/routing 仍是原厂 DLKM)。
- **修法方向(下轮主攻, 单变更)**: 把 techpack/audio **整栈"同源"内建**(树里源码齐全, TARGET_PRODUCT
  门关着 ⇒ cs35l41-build.py 的"拆门"泛化成 audio-full-build), 连 machine/platform/q6/macro/codec 一起
  以 5.4.242 ABI 编译 ⇒ 路由/功放全对齐 ⇒ tinyplay 出声 + 85s 死亡一并消失(守卫可撤)。
- 当前手机态: los94 + v6 守卫(冻框架四件套/放行 audioadsprpcd), 声卡✓ boot_completed✓ 稳定;
  证据: 149 ~/mars-build/los94-evidence/{mixer_paths.xml,live2.txt,live3.txt}; 本仓 work/98-mars-audio-guard.sh v6。

### O2. 用户侧故障"文件管理器全空白"根因(18:0x-18:3x) — 冻结方案的死刑判决
- 症状: MIUI 文件管理器无任何目录/文件, adb shell 可见; root 看 /data/media/0 正常。
- 根因链: **SIGSTOP 冻结音频进程 ⇒ 其 binder 调用被无限阻塞**:
  system_server 主线程 `NotificationManagerService.playSound→AudioSystem.setParameters`
  → 打向冻住的 audioserver 永久挂起 → watchdog 60s 杀 system_server(17:11/17:17/17:37/18:19 四次)
  → vold `Aborting fuse connection` → FUSE 挂载成孤儿(fusectl 空) → MediaProvider 服务不了
  → 文件管理器全空白。MediaProvider.getCodecList→mediaserver→冻住的 ozoaudio c2 同理。
- v7(ctl.stop 停服务而非冻结)更糟: `AudioSystem::get_audio_policy_service()` 走
  binder `getService/waitForService` ⇒ 服务不存在时**永久等待**且持有静态 mutex
  (实测 thread199 futex 挂死→主线程等其 Java 锁→照样 watchdog)。
- **"解冻/重启音频服务即死"再证**: 18:25 恢复 audioserver/vendor.audio-hal 瞬间手机硬复位
  (排队播放事件冲向 TERT_TDM 功放 = 历次解冻死亡同款)。
- **los94 定性为不可日用**: 音频活=任何播放(TERT 功放上电)秒硬死; 音频停/冻=framework 连环
  watchdog、FUSE 反复孤儿。二者必居其一 ⇒ **必须内核修复**。
- **处置**: 刷回 P3 日用版(18:31:49 flash-ok, 回读 3e70678c2573610a7ed7c5f09db10779, 镜像 md5
  663ce79ea3aa5e308d4b4b026730b0fb 不变) ⇒ /sdcard 全可见、MediaStore 响应、audioserver 正常
  运行、无 watchdog ⇒ **用户文件管理器恢复**。守卫已摘(service.d 仅剩 99-wlan-mars.sh;
  v7 备份于手机 /data/local/tmp/02-mars-audio-guard.sh.bak-los94 与本仓 work/98-mars-audio-guard.sh)。
- **下轮 los95 候选(按优先级)**:
  A. 同源 cs35l41 + TDM 编译宏(仓内文档定论: 少 `CONFIG_TARGET_PRODUCT_CS35L41_TDM` ⇒ 功放按 I2S
     初始化"跑飞"=死亡根因) — 小改动, 或可一举解决死亡+出声;
  B. 若仍死: 再加 TERT_TDM_RX_0/1 链路屏蔽(扬声器路径物理不可开 ⇒ 播放快速失败, 音频栈正常跑
     ⇒ system_server 健康/文件管理器正常, 耳机 WCD938x 路径可试出声);
  C. 兜底: techpack/audio 整栈同源内建(修 ABI 垃圾读数, 连带修路由 "no backend DAIs")。

### O3. los95 实测(19:16 刷入) — 内建 cs35l41 探针成功但声卡消失; **模块依赖链雪崩**根因
- boot md5 `dcae7df9e728b4463ff70aec5b65204f`(run 38238110025); 开机稳定(u=419s, boot_completed=1,
  boot_id 无循环), **FUSE/文件管理器完全健康**(连接 180), 音频三服务正常 running(无守卫无挂起)
  —— 音频事故以来最好的日用状态; 但 `--- no soundcards ---`, DSP1=0, USB 未枚举(待甄别)。
- **根因(实锤)**: 我们内建 snd_event 占了驱动名 ⇒ 原厂 `snd_event_dlkm.ko` 装载败 ⇒
  `apr_dlkm` modinfo `depends=q6_notifier_dlkm,snd_event_dlkm` 不满足 ⇒ apr→q6→native→platform→machine
  全链雪崩(lsmod 佐证: machine_dlkm/apr/q6/platform 全缺席) ⇒ 机器驱动不注册 ⇒ 无卡。
- **依赖链真值(原厂 .ko modinfo 二进制)**: `machine_dlkm depends=snd_event_dlkm,wsa883x_dlkm,wcd_core_dlkm,
  wcd938x_dlkm,q6_dlkm,bolero_cdc_dlkm` —— **不含 cs35l41_dlkm**(功放=ASoC 动态按名绑定);
  `apr_dlkm depends=q6_notifier_dlkm,snd_event_dlkm`; `cs35l41_dlkm` 无依赖、无人依赖它。
- **codec 名真值**: 原厂 mars `machine_dlkm.ko`(5.4.233-qgki 真机版) 期望 `cs35l41.1-0040`+`cs35l41.1-0042`
  (bus 1) = 源码 `CONFIG_TARGET_PRODUCT_CS35L41_TDM` 裸宏变体; mars 由 DT `cirrus,is-mars-pa`
  运行时覆盖 DAI 名(`cs35l41.1-0042`=SPK/`cs35l41.1-0040`=RCV) —— 与宏无关。
  ⚠️ `CONFIG_TARGET_PRODUCT_STAR` 会把名改成 star bus-2(`cs35l41.2-004x`)——对 mars 无害(运行时覆盖)但无用。
- **cs35l41-i2c.c 才是 snd_event 真调用点**: probe 里 `snd_event_client_register()` 失败直接 return
  ⇒ 内建 cs35l41 必须链 snd_event ⇒ 被迫连带内建 ⇒ 死锁成立。
- **USB 之谜**: los95 后 USB 未枚举(gadget 已配 mtp,adb 且绑定 a600000.dwc3, 链路 DISCONNECTED);
  dwc3 日志与 los94 逐字相同(`rev 00000000` 系正常) ⇒ 疑状态问题而非内核栈回归(待重启甄别)。
  教训: 勿在手机上做 `setprop sys.usb.config none` 实验(会杀 WiFi adb tcp 监听, 双通道全断)。

### O4. los96 设计(已派发 run 38245465726) — **cs35l41-i2c.c snd_event 三处打桩**(最小修复)
- 原理: 桩掉 `snd_event_client_register/notify/deregister` 三处调用(仅失 PA SSR 恢复) ⇒
  内建 cs35l41 零 snd_event 引用 ⇒ **snd_event 不再内建** ⇒ 原厂 snd_event_dlkm 正常装载 ⇒
  依赖链完整 ⇒ machine 装卡并按名绑定我们的 TDM 安全功放驱动 ⇒ TERT 流可开、功放配置正确。
- 落点: `patches/cs35l41-build.py` 新增 `_patch_cs35l41_i2c`(3 处单行桩, 不动控制流);
  `_patch_snd_event_kbuild` 停用; conf 的 SND_EVENT 保持 =m。mock 树干跑全绿(桩后残留调用=0)。
- CI 注意: workflow_dispatch **输入上限 25**(74 轮双开关顶爆被拒) ⇒ 开关改走 `extra_config`
  标记门控(`NOCS35`/`TERTMASK`, 同 RENUM 模式)。
- 验收流程不变: 刷后四条 + 出声请用户听音确认; 若仍死 ⇒ los97 = TERT 屏蔽(`patches/audio-tert-mask.py`
  已入仓, 干跑 4 处全中)。
- **命名机制闭环(soc-core.c fmt_single_name 实锤)**: I2C 设备 dev_name="1-0040" + driver->name="cs35l41"
  ⇒ `snprintf("%s.%s", driver, dev_name)` = component/DAI 名 **"cs35l41.1-0040"**(单 DAI 时 dai->name 同名)
  ⇒ 与原厂 mars machine 的 COMP_CODEC("cs35l41.1-0040","cs35l41.1-0040") 精确匹配, 且与产品宏无关
  ⇒ los96 绑定前提 100% 成立(注册名由 ASoC 核心按 i2c 设备自动生成)。
- **los96 产物(run 38245465726, 三闸门全过含"cs35l41 已编入 Image")**:
  `Image-los96` 43,809,280B md5 `8b100a8ffcbb91682b57927db6937840`;
  `los96-modules.tgz` 4,114,946B md5 `d3f02d136a8cf6039c6069d2c6247fe0`;
  已落 149 `~/mars-build/artifacts/`; 归档目录预置 `~/mars-build/KEEP/2026-10-12-los96-audio/`。
  刷机/验收链(149 `~/mars-build/los96-flash-verify.sh`)在等手机上线, 60 分钟窗口。

### O5. ★los96 音频收官(2026-10-12 20:50) — **四条验收全过, 用户耳听确认出声**
- 刷机: run 38245465726 产物(三闸门全过) → flash-tag.sh los96(USB d6fba222) → 一次成功。
- **验收**: ① `/proc/asound/cards` = `0 [lahainamtpsndca]: lahaina-mtp-snd-card` ✓
  ② cs35l41 DSP1: 725→725 双采样稳定不增长(仅开机固件载入段, 尾部为正常 amp 事件) ✓
  ③ `boot_completed=1`, boot_id `e0bb8131-a577-4920-b3a3-6bfa4be191b7` 稳定无循环 ✓
  ④ **tinyplay rc=0 + 框架播放(AudioFlinger 4 路输出线程)全跑完 + 用户确认"声音已经出来了"** ✓
- 附加: **蓝牙适配成功**(state:ON); 电池 100%/Full、VBUS 5V 在线(状态栏早期"电量为零/未充电"系
  开机早期 UI 误报, healthd 日志一直正确)。
- **USB 归属判定**: 重启后 d6fba222 恢复枚举 ⇒ los95 的"USB 丢"= **状态问题**(setprop sys.usb.config
  诊断把 gadget/adbd 停掉) 而非内核回归; WiFi adb(tcp:5555)同理被该实验杀掉, 重启均恢复。
- 归档双份: 149 `~/mars-build/KEEP/2026-10-12-los96-audio/` + 本仓 `work/keep-los96/`:
  `boot-Image-los96.img` md5 `a18c89f2ced96836bee138ee20ceb33c`(64,167,936B);
  `99-wlan-mars.sh` md5 `6a5d52475c5dfb4149c15ba074780497`(7,656B); 双侧 md5 一致。
- 生产配方(最终): GOLD JSON + `mi_syms_audio=1` + `patches/cs35l41-build.py`
  (TDM 宏内建 cs35l41 + **cs35l41-i2c.c snd_event 三处打桩** + 不内建 snd_event) + MARS-STOCKNUM。

### O6. 发布与归档(2026-10-12 21:0x)
- **GitHub Release `los96-audio-final`**: https://github.com/birdnofoots/Mi11Pro-Droidspaces-Kernel-KSU/releases/tag/los96-audio-final
  资产: boot-Image-los96.img(64,167,936B) / 99-wlan-mars.sh / MD5SUMS / MANIFEST.md / FLASH-GUIDE.md, 全部 uploaded。
- **git 整理推送**(commit `c6f0724`): README 现状化 + docs/FLASH-GUIDE.md 权威版(刷机注意事项 10 条)
  + docs/AUDIO-EPIC.md(音频攻坚全过程) + VERSIONS.md/AGENTS.md/实验流水入仓 + 旧 docs-flash-guide.md 改指针去重。
  本地 gh/ 与远端已硬同步(历史 4 个本地提交内容均被 ghpush 版本超越, 无丢失)。
- 手机端核对: /data/adb/service.d/99-wlan-mars.sh md5 `6a5d52475c5dfb4149c15ba074780497` = 归档最新版 ✓;
  WiFi 自动联网 192.168.1.145 ✓。
