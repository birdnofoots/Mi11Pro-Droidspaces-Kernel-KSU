# mars-droidspaces-kernel (GitHub Actions 构建)

给 **Xiaomi Mi 11 Pro (`mars`)** 编译带 **Droidspaces-OSS** 容器支持的内核,可选集成 **KernelSU**。
构建全部在 GitHub Actions 上完成,不需要本地环境。

## 为什么需要这个内核

设备出厂内核 (`5.4.233-qgki-gbb70cde46897`) 关闭了容器所需的关键选项:

```
CONFIG_SYSVIPC / POSIX_MQUEUE / IPC_NS / PID_NS / CGROUP_DEVICE / DEVTMPFS / USER_NS ...
```

这些是**编译期**开关,只能重编内核才能打开。

## 核心难点与做法

### 1. GKI kABI 兼容(Droidspaces 官方补丁)

打开 `CONFIG_SYSVIPC` / `CONFIG_POSIX_MQUEUE` 会改变 `task_struct` / `user_struct` 的内存布局,
导致厂商预编译模块崩溃/开机循环。`patches/` 里的两个补丁把字段挪进 `ANDROID_KABI_*` 保留槽位,
**不改变内存布局**。

| 补丁 | 作用 |
|---|---|
| `001.GKI-below-6.12-fix_sysvipc_kabi_*.patch` | SYSVIPC → `ANDROID_KABI_USE(6/7/8)` |
| `002.5.10_or_lower_..._posix_mqueue.patch` | POSIX_MQUEUE `mq_bytes` → `ANDROID_KABI_USE(1)` |

### 2. ⚠️ 厂商模块**不可能**复用(已验证)

即使把版本字符串与配置都与原厂完全对齐,**原厂模块仍然无法加载**:

| 原厂模块 | 依赖符号 | CRC 相同 | CRC 不同 |
|---|---|---|---|
| `ufs-qcom.ko` | 120 | 46 | **73** |
| `msm_drm.ko` | 735 | 258 | **474** |
| 合计 | 940 | 351 | **583** |

第一个门槛 `module_layout` 就不匹配 → 所有原厂模块被拒绝。

**原因**:`CONFIG_MODVERSIONS` 的 CRC 由 genksyms 对**头文件中类型签名**计算,
只取决于源码树。本仓库用的上游源码是 5.4.**191**,而设备是 5.4.**233**(小米内部树),
**不是同一棵树**。

### 3. 因此:**把驱动编进内核**

既然模块不可复用,就让内核自带一切。本仓库的 `configs/mars_droidspaces_defconfig` 已把
能内建的驱动全部设为 `=y`:

- **Wi-Fi**: `QCA_CLD_WLAN` / `CNSS2` / `ICNSS2`
- **触控**: `TOUCHSCREEN_ST_FTS_V521_SPI_K2`(设备实际用的是 `fts_touch_spi_k2.ko`)
- **指纹**: `FINGERPRINT_GOODIX_FOD`
- **存储/显示/时钟/电源**: UFS、SDE(显示)、RPMH、interconnect 等

编译 Wi-Fi 驱动时需要两处修改(工作流自动完成):

- `drivers/staging/qcacld-3.0/Kbuild`:本树顶层 `Makefile` 硬编码了 `-Werror`,
  内建模式下 qcacld 会触发 `unused-function` → 为该目录加 `-Wno-error`
- `qca-wifi-host-cmn/utils/nlink`:它自定义的 `nl80211hdr_put` 与 `net/wireless` **重名**
  → 改名为 `qca_nl80211hdr_put`

### 4. 仍为模块的部分(需要 APatch 叠加)

高通的 **techpack** 模块由外部 Makefile 以 `obj-m` 构建,`=y` 无效:

```
techpack/datarmnet/core/Makefile:  all: $(MAKE) -C $(KERNEL_SRC) M=$(pwd) modules
```

涉及:**音频 `*_dlkm`、`camera.ko`、`rmnet_*.ko`(移动数据)、`wireguard.ko`**

这些用 APatch 模块把**自编译的** `.ko` bind-mount 覆盖到 `/vendor/lib/modules/` 即可
(这些驱动在 post-fs-data 之后才加载,时机来得及)。

> 注意:设备**没有 `vendor_dlkm` 分区**,模块位于 `super` 里 `vendor` 逻辑分区的
> `/vendor/lib/modules/`,所以无法单独刷模块分区。

## 使用

1. Fork 本仓库
2. **Actions** → **Build mars kernel (Droidspaces ± KernelSU)** → **Run workflow**
   - `ksu_tag`:填 KernelSU 版本(如 `v0.7.6`)则集成 KernelSU;留空则不集成
   - `kabi_variant`:`6_7_8`(推荐)/ `1_2_3` / `3_4_5`
3. 构建完在 Artifacts 下载:
   - `Image` — 裸内核镜像
   - `mars-droidspaces-*.zip` — AnyKernel3 刷机包
   - 若干 `*.ko` — 需要 APatch 叠加的模块

## 版本字符串

工作流把内核 release 精确对齐设备:

```
Makefile SUBLEVEL=233
configs/... CONFIG_LOCALVERSION="-qgki-gbb70cde46897"
→ 5.4.233-qgki-gbb70cde46897      (与设备一致)
```

这样 `uname -r` 与设备一致,便于排查。

## 刷机流程

```
① PC: 用 AnyKernel3 的 Image 或 boot.img 作为输入,APatch → Patch → 生成已 root 镜像
② adb reboot bootloader
③ fastboot boot <已 root 镜像>     # 临时启动,不写盘
④ adb shell uname -r / su -c id / su -c droidspaces check   # 验证
⑤ 通过后: fastboot flash boot <已 root 镜像>
```

**必须「先打补丁再刷」**:APatch 的 root 能力在内核里,直接刷未打补丁的内核会丢 root。

## 目录

```
.github/workflows/build.yml                 构建流程(含全部源码修改)
configs/mars_droidspaces_defconfig          内核配置(Xiaomi 真实配置 + Droidspaces + 全内建)
patches/                                    Droidspaces 官方 GKI kABI 补丁
```

## 参考

- [Droidspaces-OSS 内核配置指南](https://github.com/ravindu644/Droidspaces-OSS/blob/main/Documentation/Kernel-Configuration.md)
- [上游内核源码](https://github.com/EcrosoftXiao/kernel_xiaomi_mars)
- [KernelSU](https://github.com/tiann/KernelSU)
- [AnyKernel3](https://github.com/osm0sis/AnyKernel3)

## 许可

配置与工作流脚本:MIT。内核源码沿用上游 GPL-2.0。
