# mars 内核刷机指南

> 本文覆盖两种情况,请先确认你刷的是哪一种:
> **看内核里有没有 KernelSU。**

---

## 判断方法

```bash
strings Image | grep -c KernelSU
#  0    → 不含 KSU,走【方案 A:APatch】
#  >0    → 含 KSU,走【方案 B:直接刷】
```

本次 GitHub Actions 构建的 `Image`(**51.5 MB**)含 **158 个 KernelSU 符号**,属于**方案 B**。

---

## 方案 B:KernelSU 内置内核(本次构建)

### 核心区别:**不需要 APatch patch**

KernelSU 已经**编进内核**,而且 KSU 会把 `ksud` 直接**嵌入内核镜像内部**
(源码里的 `embed_ksud.c`),所以 **ramdisk 无需任何改动**,
刷进去 root 就生效了。

> ⚠️ **不要再用 APatch**。APatch 与 KernelSU 都靠内核层 hook 工作,
> 同时存在会冲突。用 KSU 就卸载 APatch;用 APatch 就刷不含 KSU 的内核。

### 步骤

```bash
# 1) 确认镜像已在手机上
#    /storage/emulated/0/DroidspacesKernel/kernel/mars-droidspaces-ksu-boot-trimmed.img

# 2) 临时启动验证(不写盘,失败直接重启)
adb -s 192.168.1.114:5555 reboot bootloader
fastboot boot mars-droidspaces-ksu-boot-trimmed.img
#    ↑ 敲完这条手机就开始启动了。不要在这里敲 fastboot reboot!

# 3) 在启动起来的系统里验证(用 ADB,不依赖触屏)
adb -s 192.168.1.114:5555 shell "uname -r"        # 期望 5.4.233-qgki-gbb70cde46897
adb -s 192.168.1.114:5555 shell "su -c id"        # 期望 uid=0(root)
adb -s 192.168.1.114:5555 shell "su -c droidspaces check"
adb -s 192.168.1.114:5555 shell "ip addr show wlan0"   # 验证 Wi-Fi(已内建)

# 4) 验证通过 → 永久刷入
adb -s 192.168.1.114:5555 reboot bootloader
fastboot flash boot mars-droidspaces-ksu-boot-trimmed.img
fastboot reboot

# 5) 安装 KernelSU Manager APK(v0.7.6 对应版本),即可获得 root 管理
# 6) 卸载 APatch
```

### 如果 KSU 没生效

- 确认装的是匹配版本的 **KernelSU Manager**(v0.7.6)
- 检查内核: `strings /dev/block/by-name/boot | grep -c KernelSU`(需 root)
- 不要同时开 APatch

---

## 方案 A:不含 KernelSU 的内核(用 APatch 提供 root)

> 如果你的目的是继续用 APatch,就用这套流程(需要构建时 `ksu_tag` 留空)。

### ⚠️ 关键前提:**APatch 需要的是 `boot.img`,不是裸 `Image`**

GitHub / 本地编译产出的是**裸内核 `Image`**。APatch 的 Patch 流程要读 boot 镜像的
结构和 ramdisk,所以**必须先打包成 `boot.img`**(替换内核、保留原厂 ramdisk):

```bash
bash scripts/make-bootimg.sh <新内核Image> <输出boot.img>
# 内部用 magiskboot:解包参考镜像 → 换 kernel → 重打包
```

### 步骤

```bash
# 1) 把 boot.img 推到手机
adb -s 192.168.1.114:5555 push mars-droidspaces-boot.img /sdcard/DroidspacesKernel/

# 2) 在手机上用 APatch: Patch → 选择该 boot.img → 生成已打补丁的镜像
#    (APatch 的 root 能力在内核里,所以这一步不能省,否则刷完没有 root)

# 3) 把补丁后的镜像拉回电脑
adb -s 192.168.1.114:5555 pull /sdcard/Download/apatch_patched_xxx.img ./

# 4) 临时验证
adb -s 192.168.1.114:5555 reboot bootloader
fastboot boot apatch_patched_xxx.img
#    在启动起来的系统里: uname -r / su -c id / su -c droidspaces check

# 5) 永久刷入
fastboot flash boot apatch_patched_xxx.img
fastboot reboot
```

---

## 第 5 步(两种情况都需要):补齐仍为模块的驱动

音频 `*_dlkm`、`camera.ko`、`rmnet_*.ko`(移动数据)、`wireguard.ko`
由高通 **techpack** 机制以 `obj-m` 构建,**无法编进内核**。

用 APatch / KernelSU 的模块机制,把自编译的 `.ko` bind-mount 覆盖到
`/vendor/lib/modules/`:

```
/data/adb/modules/mars-droidspaces-modules/
├── module.prop
├── post-fs-data.sh          # bind-mount 覆盖
└── vendor-modules/*.ko      # 来自 mars-modules-overlay.tar.gz(36 个)
```

> 设备**没有 `vendor_dlkm` 分区**;模块位于 `super` 里 `vendor` 逻辑分区的
> `/vendor/lib/modules/`,所以不能单独刷模块分区,只能叠加。
> 这些模块(数据/相机/音频)都在 post-fs-data 之后才加载,时机来得及。

---

## 回退

```bash
# 回到当前 APatch 版原厂内核(你现在能正常开机的状态)
fastboot flash boot        /root/mars/backup/stock-boot/stock-boot_b.img
fastboot flash vendor_boot /root/mars/backup/stock-boot/stock-vendor_boot_b.img
```

---

## 常见问题

**Q:能不能直接刷 AnyKernel3 的 zip?**
A:会**丢 root**。AnyKernel3 会 dump 当前 boot 分区 → 用 zip 里的内核替换 → 写回,
而 APatch 的 root 在内核里,替换内核就等于删掉 root。
(含 KSU 的内核用 AnyKernel3 则没问题,因为 KSU 在新内核里。)

**Q:为什么原厂模块不能复用?**
A:实测:`modversions` 的 CRC 只取决于源码树的头文件类型签名。上游是 5.4.**191**,
设备是小米内部 5.4.**233** 树 → 940 个符号里 **583 个 CRC 不同**,
连第一个门槛 `module_layout` 都不匹配 → 原厂模块全部被拒绝加载。

**Q:为什么把驱动编进内核?**
A:既然模块不可复用,就让内核自带。Wi-Fi(`QCA_CLD_WLAN`/`CNSS2`/`ICNSS2`)、
触控(`ST_FTS_V521_SPI_K2`,设备实际用 `fts_touch_spi_k2.ko`)、指纹、存储(UFS)、
显示(SDE)等全部 `=y`。实测新内核里:
`wlan_hdd_cfg80211_init`✓ `hdd_wlan_startup`✓ `cnss_wlan_register_driver`✓
`fts_touch_spi`✓ `xiaomi_touch`✓ `goodix_fod`✓ `ufs_qcom_`✓ `sde_kms`✓

**Q:版本号为什么是 5.4.233 而不是源码的 5.4.191?**
A:为了 `uname -r` 与设备一致,便于排查。Makefile 用 `SUBLEVEL=233`,
配置里 `CONFIG_LOCALVERSION="-qgki-gbb70cde46897"`。
注意这**不能**让原厂模块可用(CRC 由源码决定),仅用于标识。
