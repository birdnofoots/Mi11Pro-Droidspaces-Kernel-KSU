# mars 音频攻坚全记录（2026-10-10 ~ 10-12）— 从"TERT 上电秒死"到"声音出来了"

> 一句话结局：**los96 四条验收全过**（声卡注册 / DSP1 不刷屏 / 开机稳 / tinyplay 出声=用户耳听确认），
> 另加蓝牙适配成功。可用镜像与开机脚本已双份归档（见 `MANIFEST.md` / Release）。

---

## 0. 背景

mars（小米 11 Pro, SM8350）的自编 **Droidspaces 容器内核**（LOS 5.4.242 基线）此前已达成：
进 MIUI / WiFi / 触屏 / 容器 28/28 / 相机快门全通。**音频是最后一块拼图**，验收四条：

1. `/proc/asound/cards` 有卡
2. `cs35l41 DSP1` 不再刷屏
3. 开机完成且 `boot_id` 稳定
4. `tinyplay`/框架播放出声

---

## 1. 事故谱系（先看失败，才懂成功）

### 1.1 TERT_TDM_RX 上电秒死（核心事故）
任何程序打开 `TERT_TDM_RX_0`（扬声器 PCM）**即使播静音**，也在 <0.5s 内触发整机硬件级重置
（无 oops、无 warning、直接黑屏重启）。结论：**功放（cs35l41 ×2）上电即死**。

### 1.2 错误路线一：冻结/停止音频进程（系统级雪崩）
- `SIGSTOP` 音频进程 → binder transact 挂起 → system_server watchdog 杀进程 →
  vold `Aborting fuse connection` → **FUSE 孤儿 → 文件管理器全盘空白**。
- `ctl.stop audioserver` → `get_audio_policy_service()` waitForService/mutex 死等；
  重启音频 → 队列积压播放 → TERT 硬死。
- **铁律（checklist §43）**：永远不要用 SIGSTOP/ctl.stop/kill 处理音频进程。已废弃的
  `98-mars-audio-guard.sh` v7 是反面教材（`/data/local/tmp/02-mars-audio-guard.sh.bak-los94`）。

### 1.3 错误路线二：内建整条音频栈不知取舍
los95 把 cs35l41 + snd_event 一起内建 → 声卡反而消失（见 §2.2）。

---

## 2. 三大根因（全部实锤，附证据形态）

### 2.1 根因 A：功放配置错误（"TERT 秒死"的真凶）
cs35l41 音频路径寄存器被配错（`0x2029/0x2032/0x2030`），功放一上电就硬件重置整机。
修复 = 编译宏对齐 mars 真实拓扑：`CONFIG_TARGET_PRODUCT_CS35L41_TDM`（TDM 直连）+
mars 运行时分支（DT `cirrus,is-mars-pa` ⇒ `SPK_DAI_NAME=cs35l41.1-0042` /
`RCV_DAI_NAME=cs35l41.1-0040`）。**曾计划的 `audio-tert-mask.py`（屏蔽 TERT 链路）最终未动用**
（已在仓备用，los97 兜底，未派发）。

### 2.2 根因 B：模块依赖链雪崩（los95"声卡消失"的真凶）
内建 snd_event 占了驱动名 ⇒ 原厂 `snd_event_dlkm.ko` 装载败 ⇒
**`apr_dlkm` 的 modinfo `depends=q6_notifier_dlkm,snd_event_dlkm` 按名失配** ⇒
apr→q6→native→platform→machine 全链雪崩 ⇒ 机器驱动不注册 ⇒ 无声卡。
依赖链真值（原厂 .ko modinfo 二进制直读）：
```
machine_dlkm  depends= snd_event_dlkm,wsa883x_dlkm,wcd_core_dlkm,wcd938x_dlkm,q6_dlkm,bolero_cdc_dlkm
apr_dlkm      depends= q6_notifier_dlkm,snd_event_dlkm
cs35l41_dlkm  depends= (无)         ← 没有任何模块依赖它！
```
⇒ **snd_event 绝不可内建**；cs35l41 可内建（功放绑定是 ASoC 动态按名，不占 modinfo 链）。

### 2.3 根因 C：cs35l41-i2c.c 才是 snd_event 的真调用点
`cs35l41_i2c_probe()` 里 `snd_event_client_register()` 失败即 `return rc` ⇒
内建 cs35l41 必须链 snd_event ⇒ 被迫连带内建 ⇒ 与 2.2 死锁。
**破局 = 三处打桩**：`snd_event_client_register / snd_event_notify / snd_event_client_deregister`
置空（只失去 PA SSR 子系统重启恢复，无 SSR 场景无损）⇒ 内建 cs35l41 零 snd_event 引用。

### 2.4 附：命名机制（为什么绑定必然成功）
`sound/soc/soc-core.c fmt_single_name()`：I2C 设备 dev_name=`1-0040` + 驱动名 `cs35l41`
⇒ `snprintf("%s.%s", driver, dev_name)` = component/DAI 名 **`cs35l41.1-0040`**（单 DAI 同名）
⇒ 与原厂 mars `machine_dlkm` 的 `COMP_CODEC("cs35l41.1-0040","cs35l41.1-0040")` 精确匹配，
且**与产品宏无关**（`CONFIG_TARGET_PRODUCT_STAR` 只影响听筒调音/VPBR，不碰注册名）。

---

## 3. 最终配方（los96，run 38245465726）

```
GOLD JSON + mi_syms_audio=1 + MARS-STOCKNUM 编号修复
+ patches/cs35l41-build.py：
    ① codecs/Kbuild 拆 TARGET_PRODUCT 门
    ② cs35l41/Kbuild: TDM(+STAR) 宏 + obj-y 内建 cs35l41_dlkm.o
    ③ cs35l41-i2c.c: snd_event 三处打桩          ← 灵魂一笔
    ④ 不动 soc/Kbuild（snd_event 保持原厂 =m）
```
CI 三闸门全过（`编译 Image` / `构建错误闸门` / `验收 cs35l41 已编入 Image`）。
产物：`Image-los96` 43,809,280B md5 `8b100a8ffcbb91682b57927db6937840`。

**刷机与验收**：`flash-tag.sh los96`（打包→刷 boot_a→回读校验→p4-verify）→
`los96-verify.sh`（三连蜂鸣）→ 用户听音确认。

---

## 4. 验收证据（2026-10-12 20:50，USB d6fba222）

| # | 项 | 证据 | 判定 |
|---|---|---|---|
| ① | 声卡 | `/proc/asound/cards` = `0 [lahainamtpsndca]: lahaina-mtp-snd-card` | ✅ |
| ② | DSP1 | 双采样 725→725 稳定不增长（仅开机固件载入段） | ✅ |
| ③ | 开机稳 | `boot_completed=1`；`boot_id=e0bb8131-a577-4920-b3a3-6bfa4be191b7` 无循环 | ✅ |
| ④ | 出声 | `tinyplay rc=0` + AudioFlinger 4 路输出线程跑完 + **用户耳听确认** | ✅ |

附加：蓝牙适配成功（state:ON）；电池 100%/Full（状态栏开机早期"电量为零/未充电"是 UI 误报，
以 `/sys/class/power_supply/battery/status` + healthd 日志为准）。

---

## 5. 运维铁律（血泪换来的）

1. **绝不内建 snd_event**（依赖链雪崩，§2.2）。
2. **别用 SIGSTOP/ctl.stop/kill 处理音频进程**（watchdog→FUSE 孤儿→文件管理器空白）。
3. **别在手机上 `setprop sys.usb.config` 做实验**——adbd 重启会连 WiFi adb tcp 监听一起杀，
   USB+WiFi 双断只能等物理重启（2026-10-12 实测，丢联 6 轮）。
4. **双 adb 通道（USB+WiFi）并存时裸 `adb` 报 more than one device**——刷机前先
   `adb disconnect 192.168.1.145:5555` 留 USB 单通道。
5. **`fastboot boot` 在本机不可用**；只 `fastboot flash boot_a`；活动槽必须 `_a`（别 `set_active b`）。
6. **刷后必核内核身份**：`uname -a`（自编 `runner@` + 2026 年日期）+ `boot_id` 稳定性。
7. 判充电/电量看 sysfs + healthd，别信开机早期状态栏。

---

## 6. 复现步骤（从零到出声）

```bash
# 1) 派发（本容器）
python3 /tmp/ghdisp2.py los.yml '{"config":"mars_factory.config","logdump":"1","wlanblock":"1",
  "ignore_vermagic":"1","mi_syms":"1","kabi":"1","allbuiltin":"1",
  "force_m":"CNSS2,CNSS_GENL,WCNSS_MEM_PRE_ALLOC","force_y":"CNSS_QCA6490",
  "hwid_deexport":"1","modules":"1","firmware_embed":"1","los_commit":"d42d2eb6c",
  "mi_syms_audio":"1"}'
# 2) 产物：bash /tmp/losw/dl-run-all.sh <run_id> los96   → 149 ~/mars-build/artifacts/Image-los96
# 3) 刷机：149 上 bash ~/mars-keep/.../flash-tag.sh los96   （或直接 fastboot flash boot_a boot-Image-los96.img）
# 4) 验收：los96-verify.sh（三连蜂鸣）→ 听音
```
日常使用无需重新编译：Release 里的 `boot-Image-los96.img` 直接刷（见 `docs/FLASH-GUIDE.md`），
刷后把 `99-wlan-mars.sh` 放进 `/data/adb/service.d/` 并 `chmod 755`（**WiFi 的命根子**）。

---

## 7. 归档

| 文件 | md5 | 位置 |
|---|---|---|
| `boot-Image-los96.img`（64,167,936B） | `a18c89f2ced96836bee138ee20ceb33c` | `work/keep-los96/` + 149 `~/mars-build/KEEP/2026-10-12-los96-audio/` + GitHub Release |
| `99-wlan-mars.sh`（7,656B） | `6a5d52475c5dfb4149c15ba074780497` | 同上（自 los96 真机 `/data/adb/service.d/` 抓取） |

全程实验流水见 `docs/mars-handover-CHECKLIST.md`（§39–§45 为音频攻坚段）；
权威版本/配方日志见 `VERSIONS.md`（§O1–§O5）。
