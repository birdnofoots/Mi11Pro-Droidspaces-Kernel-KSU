# USB WiFi 购卡与到货验收指南（mars + 一加12 Pro）

> 适用两台手机：
> - **小米 11 Pro（mars / SM8350 / 5.4.242 / los104）**：驱动**内建**，固件内建；
> - **一加12 Pro（SM8650 / 6.1.141）**：KSU 模块 `USB-WiFi-SM8650-6.1.141`（v1.4 起）提供同组驱动 + 固件 + `regulatory.db`。
>
> 目标：**一张卡两台都能用，优先 5GHz**。

## 0. 结论（先看这个）

| 需求 | 买它 |
|---|---|
| **全新、要 5GHz、最省心** | **Panda PAU09**（RT5572） |
| **二手、要 5GHz、性能好** | **Cisco Linksys AE3000** 或 **Netgear WNDA4100**（RT3573，450Mbps 3×3） |
| **2.4G 监听/注入最稳** | **ALFA AWUS036NHA**（AR9271） |
| 预算两张 | PAU09（5G 日常）+ AWUS036NHA（2.4G 注入） |

**绝对不要买**：RTL8812AU / RTL8821AU / RTL8811AU、MT7612U / MT7610U（见 §3）。

---

## 1. 两台手机的驱动底座（兼容性来源）

| 芯片 | 驱动 | mars los104 | 一加模块 v1.4 | 频段 | 监听/注入 |
|---|---|---|---|---|---|
| AR9271 | `ath9k_htc` | 内建 ✅ | 模块 ✅ | 2.4G | ✅ |
| AR9170 | `carl9170` | 内建 ✅ | 模块 ✅ | 2.4G+5G | ✅ |
| RT5572 | `rt2800usb`(RT55XX) | 内建 ✅ | 模块 ✅ | 2.4G+5G | ✅ |
| RT3573 | `rt2800usb`(RT3573) | 内建 ✅ | 模块 ✅ | 2.4G+5G | ✅ |
| RT5370 / RT5372 | `rt2800usb`(RT53XX) | 内建 ✅ | 模块 ✅ | 2.4G | ✅ |
| RT3070 / RT2870 | `rt2800usb` | 内建 ✅ | 模块 ✅ | 2.4G | ✅ |
| RT73 | `rt73usb` | 内建 ✅ | 模块 ✅（v1.4） | 2.4G | 有限 |
| RTL8187 | `rtl8187` | 内建 ✅ | 模块 ✅ | 2.4G | ✅ |
| RTL8188EU / 8192CU | `rtl8xxxu` | 内建 ✅ | 模块 ✅ | 2.4G | 有限 |
| MT7601U | `mt7601u` | 内建 ✅ | 模块 ✅ | 2.4G | 有限 |

> 结论：**上表的芯片两台都能驱动**；带 5G 的只有 AR9170、RT5572、RT3573。

---

## 2. 五张推荐卡

| # | 型号 | 芯片 | 频段 | 速率 | 监听/注入 | 购买建议 |
|---|---|---|---|---|---|---|
| 1 | **Panda PAU09** | RT5572 | 2.4G + **5G** | 300Mbps 2×2 | ✅ | **全新首选**，目前最容易买到的新 5G 卡 |
| 2 | **Cisco Linksys AE3000** | RT3573 | 2.4G + **5G** | 450Mbps 3×3 | ✅ | 二手多、便宜，5G 性能好；体积大 |
| 3 | **Netgear WNDA4100** | RT3573 | 2.4G + **5G** | 450Mbps 3×3 | ✅ | 二手多，带底座，和 AE3000 同芯片 |
| 4 | **Buffalo WLI-UC-G450** | RT3573 | 2.4G + **5G** | 450Mbps 3×3 | ✅ | 日系二手常见，同芯片备选 |
| 5 | **TRENDnet TEW-684UB** | RT3573 | 2.4G + **5G** | 450Mbps 3×3 | ✅ | 同芯片，二手偶见 |

**备选（2.4G 专用，注入最强）**：

| 型号 | 芯片 | 说明 |
|---|---|---|
| **ALFA AWUS036NHA** | AR9271 | Nethunter 圈标配，监听/注入最稳；只有 2.4G |
| Netgear WNDA3100 **v1** | AR9170 | 老双频卡，`carl9170` 驱动；只买 v1（v2/v3 换芯片） |

> 3×3 的 RT3573 卡（AE3000/WNDA4100/G450/684UB）功耗偏高，手机 OTG 供电不足时可能掉线；
> 插上后如果反复 disconnect，换带供电的 OTG 分线器或换 PAU09（2×2，省电）。

---

## 3. 不要买的芯片（两台都不支持）

| 芯片 | 常见卡 | 为什么 |
|---|---|---|
| **RTL8812AU / 8821AU / 8811AU** | ALFA AWUS036ACH/ACS、多数“1300M 双频” | 树外驱动，两套内核都没编 |
| **MT7612U / MT7610U** | ALFA AWUS036ACM、COMFAST 等 | 内核没有 `mt76x2u`/`mt7610u` |
| RTL8192EU | 大量“5G 双频”低价卡 | 芯片本身只有 2.4G |
| TL-WN722N **v2/v3** | TP-Link | v1 才是 AR9271；v2/v3 是 RTL8188EU/MT7601U |

**同名不同版是最大坑**：下单前让卖家拍 `lsusb` 或芯片丝印，按 §4.1 的 VID:PID 核对。

---

## 4. 到货验收（10 分钟）

### 4.1 先核对芯片（不插手机也能做）

电脑或手机 OTG 插上后：

```bash
lsusb
```

期望的 VID:PID（不同厂商可能用自己 VID，但 PID 一般对得上）：

| 芯片 | 常见 ID |
|---|---|
| AR9271 | `0cf3:9271` |
| AR9170 | `0cf3:9170` |
| RT5572 | `148f:5572` |
| RT3573 | `148f:3573` |
| RT5370 / RT5372 | `148f:5370` / `148f:5372` |
| RT3070 | `148f:3070` |

对不上（例如 `0bda:8812`、`0e8d:7612`）→ **直接退货**。

### 4.2 一加12 Pro 验收

前提：模块 v1.4 已装、已重启；`grep -E "^(ath9k_htc|carl9170|rt2800usb|rt73usb|rtl8187|rtl8xxxu|mt7601u) " /proc/modules` 能看到 7 个。

```bash
# 插卡前
su -c 'ip link' > /data/local/tmp/before.txt

# 插卡后
su -c 'dmesg | tail -60'
su -c 'ip link | grep wlan'          # 对比 before，新接口就是它
su -c 'cat /data/local/tmp/usb_wifi.log'
```

期望看到：

- `usb 1-1: new high-speed USB device ...`
- `usb 1-1: New USB device found, idVendor=148f, idProduct=5572`（或对应芯片）
- 驱动 probe：`ath9k_htc` / `rt2800usb` / `carl9170` 等
- 固件加载成功：`Direct firmware load for ath9k_htc/htc_9271-1.4.0.fw succeeded`
  （RT 系是 `rt2870.bin`）
- 新接口出现（`wlan1` 或 `wlan2`，取决于原厂 P2P 占号）

固件与 `regulatory.db` 在第一次开机时已复制到 `/mnt/vendor/persist/copy/`；`regulatory.db` 要等**一次真正的内核重启**后才会被 `cfg80211` 读到。

### 4.3 mars 验收

```bash
adb shell 'su -c "dmesg | tail -60; ip link | grep wlan"'
```

mars 的固件**已编进内核**（`EXTRA_FIRMWARE`），插上即用，不需要放 `/vendor/firmware`。

### 4.4 5GHz 验证

NAT 容器看不到 `wlan*`，需要 `--net=host` 容器（或 Termux root + `iw`）：

```bash
iw phy | grep -A6 "Band 2"     # 有 5GHz 频段
iw reg get                     # country
iw reg set CN                  # 若显示 00/world
iw dev wlanX info
```

> mars 目前**没有** `regulatory.db`（内核 `CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y`），5GHz 可能只能被动扫描；
> 要主动发 5G 包，需要后续内核把 `regulatory.db` 内建，或临时用 APatch 模块放到 `/vendor/firmware`。

### 4.5 监听/注入验证

```bash
ip link set wlanX down
iw dev wlanX set monitor none
ip link set wlanX up
iw dev wlanX info               # type: monitor
```

注入测试需要另一张卡或一个 AP：

```bash
aireplay-ng --test wlanX        # 需要 aircrack-ng
```

### 4.6 稳定性

- 连续跑 10 分钟 `iperf3` 或大文件下载，看是否掉线；
- 摸外壳温度；3×3 卡发烫明显属正常，但掉线=供电不足；
- `dmesg | grep -i "disconnect\|reset\|-110"` 不应反复出现。

---

## 5. 退货判据

出现任一条就可以退：

1. `lsusb` 芯片与商品页不符（尤其 8812AU/7612U 冒充“Linux 免驱”）；
2. 插上后 `dmesg` 完全没有 probe 记录（先排除模块没装/没重启）；
3. 固件加载失败（`Direct firmware load ... failed`）且重插仍失败；
4. 无法进入 monitor 模式（`iw ... set monitor` 报错）；
5. regdb 生效 + `iw reg set CN` 后仍然没有 Band 2；
6. 反复掉线/过热，换供电仍复现。

---

## 6. 两台手机的已知差异

| 项 | 一加12 Pro | mars |
|---|---|---|
| 驱动 | KSU 模块 v1.4（开机自动 insmod） | los104 内核内建 |
| 固件 | 模块复制到 `/mnt/vendor/persist/copy/` | 编进内核（`EXTRA_FIRMWARE`） |
| `regulatory.db` | 模块已带（真实重启后生效） | **缺**（5G 可能受限） |
| 日志 | `/data/local/tmp/usb_wifi.log` | — |
| 容器使用 | 需 `--net=host` 容器才能看到 `wlanX` | 同左 |

**注意**：`wlan0` 是手机自己的 WiFi，任何操作（monitor/注入）都用新出现的 `wlanX`，别动 `wlan0`。

---

## 7. 购买顺序建议

- **只买一张**：Panda PAU09（全新、5G、省心）；
- **两张组合**：PAU09（5G 日常）+ ALFA AWUS036NHA（2.4G 注入最稳）；
- **预算优先（二手）**：AE3000 或 WNDA4100 + AWUS036NHA。

---

## 8. 命令速查

```bash
# 看芯片
lsusb
# 看识别/固件
dmesg | grep -iE "usb 1-1|ath9k|rt2800|carl9170|firmware"
# 看接口
ip link | grep wlan
# 看驱动绑定
ls -l /sys/bus/usb/drivers/ath9k_htc/ 2>/dev/null
ls -l /sys/bus/usb/drivers/rt2800usb/ 2>/dev/null
# 监控模式
iw dev wlanX set monitor none
# 5GHz
iw phy | grep -A8 "Band 2"
iw reg set CN
```
