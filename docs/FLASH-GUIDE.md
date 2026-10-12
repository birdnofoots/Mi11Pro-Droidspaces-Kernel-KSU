# mars 内核刷机指南（2026-10-12 更新 · los96 音频收官版）

> 本文是**唯一权威刷机文档**（旧版 `docs-flash-guide.md` 已改为指针）。
> 适用于 Release `los96-audio-final` 及之后的镜像；历史镜像（P3/los6x）同理。

---

## ★ root 方案选择：APatch vs KernelSU（用户自选，2026-10-13 起）

> 两种 root 方案**择一使用**，差异核心在一句话：**APatch 的 KernelPatch 会占用 syscall 436
> （"supercall"），而 KSU 不占** ⇒ 内核对 glibc/systemd 的 `close_range(436)` 行为不同
> ⇒ **APatch 方案下容器要装 `nr436-shim`，KSU 方案下不用**。

|  | **方案 A：APatch（默认）** | **方案 B：KernelSU v0.9.5** |
|---|---|---|
| root 原理 | 刷机时 `boot_patch` 注入 KernelPatch → `apd`/supercall(nr 436) | 内核源码整合 `drivers/kernelsu`（kprobe + LSM 钩子，prctl IPC） |
| **syscall 436** | **被 supercall 加塞占用**（glibc `close_range` 撞号 ⇒ systemd 服务孵化失败） | 本树原生撞号（QGKI 把 `process_madvise` 抢占 436，glibc `close_range` 收 EINVAL 不回退 ⇒ 同样孵化失败）；**由 `MARS-CLOSE-RANGE-436` 内核补丁根治**（436 还给 `close_range` 真实现）⇒ 容器无需 shim |
| **容器 NAT** | **每容器必须装 `nr436-shim`**（见下节） | **不需要任何 shim**（靠 `MARS-CLOSE-RANGE-436`，los100-ksu 起） |
| 镜像 | 净版 + APatch App/flash-local.sh **打补丁后**再刷 | **净版直接刷，绝不能打 APatch 补丁** |
| root 管理 | APatch App（`me.bmax.apatch`） | KernelSU 管理器 **v0.9.5**（`me.weishu.kernelsu`，装同版本避免版本错配） |
| 开机脚本 | `/data/adb/service.d/`（apd 执行） | `/data/adb/service.d/`（ksud 执行，路径不变） |
| 构建 | GOLD JSON 常规构建 | 构建时 `extra_config` 里加标记 **`KSU`**（自动整合 v0.9.5 + `MARS-SECUREBITS-FIX` + `MARS-ROOTCAP-FIX`；`MARS-CLOSE-RANGE-436` 全构建通用） |
| 已知坑 | 436 撞号（shim 根治） | ① 需 `CONFIG_KPROBES=y`（我们 config 已带，CI 有断言）<br>② **必须带 `MARS-SECUREBITS-FIX`**（上游 v0.9.5 `escape_to_root` 不清 securebits ⇒ Android 的 0x2f 锁位遗传 ⇒ ping/systemd 全瘫）<br>③ 刷后需在管理器里授权"Shell"才有 adb root<br>④ **必须带 `MARS-CLOSE-RANGE-436`**（否则 glibc `close_range()` 撞 `process_madvise` 收 EINVAL ⇒ systemd ExecCondition 202/FDS、dbus/networkd 全挂 ⇒ 容器无网；APatch 下同理所以才要 shim）<br>⑤ **必须带 `MARS-ROOTCAP-FIX`**（`default_root_profile` 是零初始化 static、缓存只靠管理器下发 ⇒ 重启后 `escape_to_root` 发出**零能力 root**（uid=0 但 CapEff/CapBnd 全 0）⇒ unshare/chmod/容器起不来/droidspaces check 全挂） |

### 方案 A 步骤（APatch，沿用现状）
1. 净版镜像 → APatch 打补丁（方式 A/B 见下方"快速通道"）→ 刷 `boot_a`；
2. 装开机脚本 `99-wlan-mars.sh`（WiFi 命根子）；
3. **每个容器**装一次 `nr436-shim`（见下节），否则现代 systemd 发行版容器无网。

### 方案 B 步骤（KSU）
1. CI 构建：`extra_config` 加 `KSU` 标记（产出 `los98-ksu` 及以后）；
2. **裸刷净版**（不打补丁）：`adb push boot-xxx.img` → `dd of=/dev/block/by-name/boot_a` → 回读校验 → 重启
   （或 `fastboot flash boot_a boot-xxx.img`）；
3. 装 **KernelSU 管理器 v0.9.5** APK（`adb install` 被 MIUI 拦时用 `su -c pm install`）；
4. 打开管理器 →「超级用户」→ 给 **Shell** 打开允许（否则 adb shell 无 root）；
5. 开机脚本照旧放 `/data/adb/service.d/`（ksud 会执行）；
6. **容器无需 shim**，NAT 直接验证。
7. 刷后自检（可选但建议）：`su -c /data/local/tmp/droidspaces check` 应 28/28；`grep CapEff /proc/self/status` 应为 `ffffffffffffffff`（若全 0 = 缺 `MARS-ROOTCAP-FIX`）。

### ⚠️ 红线（不能混）
- **APatch 打过补丁的 boot + KSU 内核** = 禁止（436 重新被占 + 双钩子冲突）；
- 同一 boot 镜像**只走一种**方案；切换 = 用对应镜像重刷；
- 不要把 KernelSU 管理器与 APatch 同时当 root 源（`/data/adb` 下两套用户态会话并存易混）。

---

## 0. 快速通道（推荐）：刷 Release 的日用完全体 los96

```bash
# 0) 手机连电脑（USB 或 WiFi adb），确认设备
adb devices
#    ⚠️ 若 USB 与 WiFi 两个设备同时在线，先 adb disconnect 192.168.1.145:5555
#       留 USB 单通道，否则裸 adb 命令会报 "more than one device"

# 1) ★先打 root 补丁，再刷（净版镜像直接刷会丢 root ⇒ 开机脚本不跑 ⇒ 没 WiFi！）
#    Release 里的 boot-Image-los96.img 是"净版"（未打 root 补丁）。
#    方式 A（推荐，已 root 设备）：用本项目 flash-local.sh，它会自动 APatch 打补丁→dd→回读
#    方式 B（任意设备）：装 APatch App → "选择并修补一个文件" → 选 boot-Image-los96.img
#      → 产出 patched_xxx.img 再刷它：
adb reboot bootloader
fastboot flash boot_a patched_boot-Image-los96.img   # ← 刷打过补丁的！
fastboot reboot

# 2) 装开机脚本（★ WiFi 的命根子，必做）
adb push 99-wlan-mars.sh /data/local/tmp/
adb shell su -c "cp /data/local/tmp/99-wlan-mars.sh /data/adb/service.d/99-wlan-mars.sh"
adb shell su -c "chmod 755 /data/adb/service.d/99-wlan-mars.sh"

# 3) 刷后核身份（防假阳性/刷错槽）
adb shell 'uname -a; getprop ro.boot.slot_suffix; cat /proc/sys/kernel/random/boot_id'
#    自编内核: "runner@..." + 2026 年日期 + 槽 _a；boot_id 重启后不应循环变化
```

**los96 = 日用完全体**：进 MIUI ✅ WiFi ✅ 触屏 ✅ 电池 ✅ 相机 ✅ **音频出声** ✅ 蓝牙 ✅ 容器 ✅

---

## 1. 判断镜像类型（KSU 与否）

```bash
strings Image | grep -c KernelSU
#  0  → 不含 KSU，root 走 APatch（§4）
#  >0 → KSU 已内建，root 直接生效（§3）
```

> ⚠️ **APatch 与 KernelSU 不要共存**（同为内核层 hook，会冲突）。

---

## 2. ★ 刷机注意事项（硬约束，违者轻则假阳性重则变砖）

1. **只刷 `boot_a`**：`fastboot flash boot_a <img>`。活动槽必须是 `_a`。
   **绝不要 `fastboot set_active b`**（会从错误槽启动，浪费半天排查）。
2. **`fastboot boot` 在本机不可用**——旧版指南曾建议"临时启动验证"，**该建议已作废**。
   验证请直接刷入后用 adb 核身份。
3. **`fastboot flash` 报 `waiting for any device` = 没刷上**，别当成功。
   刷完用 `adb shell cat /proc/version` 复核。
4. **刷后必须核对内核身份**（防"刷了自编却跑原厂"的假阳性）：
   ```bash
   adb shell 'uname -a; zcat /proc/config.gz | grep MODVERSIONS; cat /proc/cmdline'
   ```
   自编：`runner@...` + 2026 年日期 + `# CONFIG_MODVERSIONS is not set`；
   原厂：`builder@pangu-build-...` + `Wed Dec 20 08:12:00 UTC 2023`。
5. **`99-wlan-mars.sh` 必须在** `/data/adb/service.d/`（755）：
   没有它 ⇒ 开机没有 WiFi（内核门禁挡住原厂 WLAN 栈，且必须等 CBC 校准后才能装模块）。
   换机/重刷后唯一要补的就是这个脚本。
6. **别在手机上 `setprop sys.usb.config` 做实验**：adbd 重启会连 WiFi adb 监听一起杀，
   USB+WiFi 双断只能等物理重启（2026-10-12 丢联数小时的教训）。
7. **卡死救援**：手机进 fastboot（电源+音量下）后，149 常驻 `rescue-daemon.sh` 会自动刷回
   GOLD 原厂+APatch 镜像（`apatch-patched-boot-0.13.3.img` md5 `8fcf3576ea35c98da130d16c292d9967`）；
   手动救机同理：`fastboot flash boot_a <GOLD镜像> && fastboot reboot`。
8. **屏幕全黑不可信**；判进系统用 `boot_completed=1` + `/proc/version` + `boot_id` 稳定。
9. **电池/充电以 sysfs 为准**（`/sys/class/power_supply/battery/status` + healthd 日志）；
   开机早期状态栏"电量为零/未充电"是 UI 误报。
10. 大文件传输用 `ssh 'cat > 远端' < 本地`（高 RTT 链路 scp 不稳）；
    149 上跑后台任务用 `setsid nohup`；`pkill -f 某.sh` 时同一条命令行里别出现该文件名（会自杀）。

---

## 3. 方案 B：KernelSU 内建内核

KSU 已编进内核且 `ksud` 嵌入镜像，**ramdisk 无需改动**，刷入即 root。

```bash
adb reboot bootloader
fastboot flash boot_a mars-droidspaces-ksu-boot.img   # ← boot_a，不是 boot！
fastboot reboot
# 系统起来后:
adb shell 'uname -r; su -c id; su -c droidspaces check'
```

KSU 未生效时：装匹配版本的 KernelSU Manager（v0.7.6）；确认没装 APatch；
`strings /dev/block/by-name/boot | grep -c KernelSU`（需 root）复查。

---

## 4. 方案 A：不含 KSU 的内核（APatch 提供 root）

**APatch 需要打包好的 `boot.img`，不是裸 `Image`**（要读 boot 结构与 ramdisk）：

```bash
# 打包（替换内核、保留原厂 ramdisk）
python3 tools/make-bootimg.py <新Image> <输出boot.img>   # ref/boot-header.bin + ref/boot-ramdisk-norec.gz
# 在手机上用 APatch: Patch → 选该 boot.img → 生成补丁镜像 → 拉回电脑
adb reboot bootloader
fastboot flash boot_a apatch_patched.img
fastboot reboot
```

---

## 5. 手机端 dd 刷法（无 fastboot 时，root 可用）

149 自动化脚本 `flash-local.sh` 的等价手动流程：

```bash
adb push boot-Image-los96.img /data/local/tmp/next.img
adb shell su -c 'dd if=/data/local/tmp/next.img of=/dev/block/by-name/boot_a bs=1048576'
adb shell su -c 'dd if=/dev/block/by-name/boot_a bs=1048576 count=61 | md5sum'   # 回读校验
adb reboot
```

---

## 6. 刷后验收（los96 音频版）

```bash
adb shell 'cat /proc/asound/cards'        # 期望: 0 [lahainamtpsndca]: lahaina-mtp-snd-card
adb shell 'su -c dmesg | grep -c DSP1'    # 期望: 开机一段后稳定不增长
adb shell 'getprop sys.boot_completed'    # 期望: 1（且 boot_id 稳定）
tinyplay t.wav -D 0 -d 0                  # 期望: 出声（rc=0）
```
完整背景与三连蜂鸣听音流程见 `docs/AUDIO-EPIC.md`。

---

## 7. 回退

- **回到日用完全体（推荐）**：刷 Release 的 `boot-Image-los96.img`（md5 `a18c89f2ced96836bee138ee20ceb33c`）。
- **回到原厂+APatch**：刷 GOLD 镜像（§2.7）。
- 救砖：进 fastboot（电源+音量下）→ `fastboot flash boot_a <镜像> && fastboot reboot`。

---

## 8. 常见问题

**Q: AnyKernel3 zip 能直接刷吗？**
A: 不含 KSU 的内核会**丢 root**（AnyKernel3 换内核 = 删掉 APatch 的内核层 root）；
含 KSU 的内核可以。

**Q: 刷完没有 WiFi？**
A: 十有八九是 `/data/adb/service.d/99-wlan-mars.sh` 没装/没 755。补上重启。

**Q: 刷完没声音/打开播放器就重启？**
A: 确认刷的是 los96 以上（`uname -a` 为 2026-10-12 后的 runner 构建）。
los95 及更早的音频栈有 TERT 上电秒死问题，见 `docs/AUDIO-EPIC.md`。
