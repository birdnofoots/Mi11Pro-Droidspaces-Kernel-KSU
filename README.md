# mars-droidspaces-kernel（GitHub Actions 构建）

给 **Xiaomi Mi 11 Pro (`mars`, SM8350)** 编译带 **Droidspaces-OSS** 容器支持的自编内核。
构建全部在 GitHub Actions 完成，不需要本地编译环境。

---

## 🎉 当前状态（2026-10-12）：los96 音频收官 —— 日用完全体

| 能力 | 状态 |
|---|---|
| 进 MIUI / 触屏 / 电池 / 相机 | ✅ |
| WiFi（原厂 WLAN 栈 + `99-wlan-mars.sh`） | ✅ |
| **音频出声**（声卡注册 + tinyplay/框架播放） | ✅（用户耳听确认） |
| 蓝牙 | ✅（适配成功） |
| Droidspaces 容器（`droidspaces check` 28/28） | ✅ |

### 📸 真机截图（mars 实拍）

> 2026-10-12 los96 刷入验收后拍摄（Droidspaces App ×4 + APatch root 管理 ×2），
> 另附 2026-10-11 一张作对照。原图在 [`docs/screenshots/`](docs/screenshots)。

| | |
|---|---|
| <img src="docs/screenshots/droidspaces-2026-10-12-a.jpg" width="270"> | <img src="docs/screenshots/droidspaces-2026-10-12-b.jpg" width="270"> |
| *Droidspaces App · 10-12 21:12* | *Droidspaces App · 10-12 21:12* |
| <img src="docs/screenshots/droidspaces-2026-10-12-c.jpg" width="270"> | <img src="docs/screenshots/droidspaces-2026-10-12-d.jpg" width="270"> |
| *Droidspaces App · 10-12 21:12* | *Droidspaces App · 10-12 21:12* |
| <img src="docs/screenshots/apatch-2026-10-12-a.jpg" width="270"> | <img src="docs/screenshots/apatch-2026-10-12-b.jpg" width="270"> |
| *APatch root 管理 · 10-12 21:13* | *APatch root 管理 · 10-12 21:13* |
| <img src="docs/screenshots/droidspaces-2026-10-11.jpg" width="270"> | |
| *Droidspaces App · 10-11（对照）* | |

**直接使用**：下载 [Release `los96-audio-final`](../../releases) 里的
`boot-Image-los96.img` + `99-wlan-mars.sh`，按 [`docs/FLASH-GUIDE.md`](docs/FLASH-GUIDE.md) 刷入。
md5: `boot-Image-los96.img` = `a18c89f2ced96836bee138ee20ceb33c`。
⚠️ **镜像是净版（未打 root 补丁）**：刷前先用 APatch App"选择并修补一个文件"打补丁（或走
`flash-local.sh` 自动打），否则没有 root ⇒ `/data/adb/service.d/99-wlan-mars.sh` 不执行 ⇒ 无自动 WiFi。
root 方案 = APatch（本仓不含 KernelSU；非 GKI 内核若要 KSU 须源码集成 v0.9.5，见讨论 §非GKI）。

**文档索引**：
- [`docs/FLASH-GUIDE.md`](docs/FLASH-GUIDE.md) — **刷机指南与注意事项（唯一权威）**
- [`docs/AUDIO-EPIC.md`](docs/AUDIO-EPIC.md) — 音频攻坚全记录（根因/配方/验收证据/运维铁律）
- [`VERSIONS.md`](VERSIONS.md) — 权威版本/配方日志
- [`docs/mars-handover-CHECKLIST.md`](docs/mars-handover-CHECKLIST.md) — 全部实验流水
- [`AGENTS.md`](AGENTS.md) — 操作手册（硬约束/环境/血泪坑）
- [`docs-flash-guide.md`](docs-flash-guide.md) — 旧版指南指针（内容已迁移）

---

## 为什么需要这个内核

设备出厂内核（`5.4.233-qgki-gbb70cde46897`）关闭了容器所需的关键选项：

```
CONFIG_SYSVIPC / POSIX_MQUEUE / IPC_NS / PID_NS / CGROUP_DEVICE / DEVTMPFS / USER_NS ...
```

这些是**编译期**开关，只能重编内核才能打开。

## 核心难点与做法

### 1. GKI kABI 兼容（Droidspaces 官方补丁）

打开 `CONFIG_SYSVIPC` / `CONFIG_POSIX_MQUEUE` 会改变 `task_struct` / `user_struct` 的内存布局，
导致厂商预编译模块崩溃/开机循环。`patches/` 的补丁把字段挪进 `ANDROID_KABI_*` 保留槽位，
**不改变内存布局**。

| 补丁 | 作用 |
|---|---|
| `001.GKI-below-6.12-fix_sysvipc_kabi_*.patch` | SYSVIPC → `ANDROID_KABI_USE(6/7/8)` |
| `002.5.10_or_lower_..._posix_mqueue.patch` | POSIX_MQUEUE `mq_bytes` → `ANDROID_KABI_USE(1)` |

### 2. ⚠️ 厂商模块不可能整体复用（已验证）

即使版本字符串与配置全对齐，**原厂带 CRC 的模块仍无法加载**（`module_layout` CRC 不匹配 583/940）：
本仓上游源码与小米内部树**不是同一棵树**。

### 3. 因此：把驱动编进内核 + 选择性保留原厂 DLKM

- 触控/指纹/存储/显示/电源等全部 `=y` 内建（`allbuiltin=1` + 专项 `force_m/force_y`）。
- **WiFi 用原厂栈**：`cnss2.ko` → CBC 校准 → `qca_cld3_wlan.ko`（顺序敏感，由 `99-wlan-mars.sh` 完成）。
- **音频（los96 最终解）**：cs35l41 功放驱动**同源内建**（TDM 宏修正上电配置）+ `cs35l41-i2c.c`
  的 snd_event 调用**三处打桩**（保证原厂 `snd_event_dlkm` 正常装载、依赖链完整），
  其余音频 DLKM 用原厂。详见 [`docs/AUDIO-EPIC.md`](docs/AUDIO-EPIC.md)。

### 4. 仍为模块的部分

高通 **techpack** 部分模块由外部 Makefile 以 `obj-m` 构建；设备**没有 `vendor_dlkm` 分区**，
模块位于 `super` 里 `vendor` 逻辑分区的 `/vendor/lib/modules/`，无法单独刷模块分区。

## 构建（当前工作流 `los.yml`）

```bash
python3 /tmp/ghdisp2.py los.yml '{"config":"mars_factory.config","logdump":"1","wlanblock":"1",
  "ignore_vermagic":"1","mi_syms":"1","kabi":"1","allbuiltin":"1",
  "force_m":"CNSS2,CNSS_GENL,WCNSS_MEM_PRE_ALLOC","force_y":"CNSS_QCA6490",
  "hwid_deexport":"1","modules":"1","firmware_embed":"1","los_commit":"d42d2eb6c",
  "mi_syms_audio":"1"}'
```

- 基线：LineageOS `android_kernel_xiaomi_sm8350@d42d2eb6c`（5.4.242）
- 真机原厂 config：`configs/mars_factory.config`；产物带 `ignore_vermagic` + MIUI 符号桩
- 历史工作流 `build.yml`（早期 5.4.191 上游树方案）仅作存档

## 刷机

**一律 `fastboot flash boot_a <img>`**（活动槽 `_a`；`fastboot boot` 在本机不可用）。
完整步骤、注意事项、救机、验收见 [`docs/FLASH-GUIDE.md`](docs/FLASH-GUIDE.md)。

## 目录

```
.github/workflows/los.yml        当前构建工作流（GOLD 配方）
.github/workflows/build.yml      早期工作流（存档）
configs/                         mars_factory.config 等内核配置
patches/                         kABI/音频/WLAN/诊断等全部补丁脚本
firmware/                        内建固件（EXTRA_FIRMWARE）
ref/ tools/                      boot 打包参考件与工具
docs/                            刷机指南 / 音频史诗 / 实验流水
VERSIONS.md AGENTS.md            权威日志 / 操作手册
```

## 参考

- [Droidspaces-OSS 内核配置指南](https://github.com/ravindu644/Droidspaces-OSS/blob/main/Documentation/Kernel-Configuration.md)
- [LineageOS kernel_xiaomi_sm8350](https://github.com/LineageOS/android_kernel_xiaomi_sm8350)
- [KernelSU](https://github.com/tiann/KernelSU)

## 许可

配置与工作流脚本：MIT。内核源码沿用上游 GPL-2.0。
