# USB WiFi（OP12P / mars 双机兼容）— 选型与集成说明

> 买卡/到货验收清单见 **[`USB-WIFI-CARDS.md`](USB-WIFI-CARDS.md)**（5 张推荐型号、VID:PID 核对、5GHz/监听验收、退货判据）。


> 目标：买**一个** USB WiFi 网卡，OP12P（SM8650 / 6.1.141）和 mars（SM8350 / 5.4.242）都能用。
> 结论：**AR9271（ath9k_htc）首选**；**RT5370（rt2800usb）** 是便宜的备选；要 5GHz 选 **RT5572（RT55XX）**。
> 下面这些驱动两边内核都支持，mars 已内建，OP12P 已按模块 + 固件打包。

## 1. OP12P 项目里已有的东西（已检查）

路径：`/root/work/oppo_oplus_realme_sm8650`

- `payload_wifi.json`：`"wifi_modules": "true"`
- `.github/workflows/fastbuild_6.1.141.yml` → `启用 USB 无线网卡驱动模块`：
  ```text
  CONFIG_ATH9K_HTC=m
  CONFIG_CARL9170=m
  CONFIG_RT2X00=m
  CONFIG_RT2800USB=m
  CONFIG_RT73USB=m
  CONFIG_RTL8187=m
  CONFIG_RTL8XXXU=m
  CONFIG_MT7601U=m
  ```
- 打包 `wifi-modules-6.1.141.tar.gz`：驱动 `.ko` + 固件：
  ```text
  ath9k_htc/htc_7010-1.4.0.fw
  ath9k_htc/htc_9271-1.4.0.fw
  carl9170-1.fw
  rt2870.bin
  rt73.bin
  mt7601u.bin
  rtlwifi/rtl8188efw.bin
  rtlwifi/rtl8192cufw.bin
  ```
- `load-wifi.sh`：在 Android root shell 里按依赖顺序 `insmod`，只加载模块，不改内核。
- 状态：**尚未刷入 OP12P 真机**（用户确认）；驱动/固件产物已在，待验证。

## 2. mars 的集成（los104）

mars 直接把同一组驱动**内建**（`=y`），固件用 `EXTRA_FIRMWARE` 编进内核（不依赖 `/vendor/firmware` 是否可写）：

```text
CONFIG_WLAN_VENDOR_ATH=y
CONFIG_ATH9K_HTC=y
CONFIG_CARL9170=y
CONFIG_WLAN_VENDOR_RALINK=y
CONFIG_RT2X00=y
CONFIG_RT2800USB=y
CONFIG_RT2800USB_RT33XX=y
CONFIG_RT2800USB_RT35XX=y
CONFIG_RT2800USB_RT3573=y
CONFIG_RT2800USB_RT53XX=y      # ★ RT5370 必须
CONFIG_RT2800USB_RT55XX=y      # RT5572
CONFIG_RT2800USB_UNKNOWN=y
CONFIG_RT73USB=y
CONFIG_WLAN_VENDOR_REALTEK=y
CONFIG_RTL8187=y
CONFIG_RTL8XXXU=y
CONFIG_RTL8XXXU_UNTESTED=y
CONFIG_WLAN_VENDOR_MEDIATEK=y
CONFIG_MT7601U=y
CONFIG_EEPROM_93CX6=y
CONFIG_CRC_ITU_T=y
```

真机 los104 上驱动已注册（无需 `insmod`）：

```text
/sys/bus/usb/drivers/ath9k_htc
/sys/bus/usb/drivers/carl9170
/sys/bus/usb/drivers/mt7601u
/sys/bus/usb/drivers/rt2800usb
/sys/bus/usb/drivers/rt73usb
/sys/bus/usb/drivers/rtl8187
/sys/bus/usb/drivers/rtl8xxxu
```

插上对应网卡后，`dmesg` 会看到 `usbcore: registered new interface driver ...` 之后的
`ath9k_htc`/`rt2800usb` probe，`ip link` 出现 `wlan1`（或 `wlanX`）。

## 3. 选型建议（只买一次）

| 芯片 | 驱动 | 频段 | AP/STA/监听 | 固件 | 建议 |
|---|---|---|---|---|---|
| **AR9271** | `ath9k_htc` | 2.4G | ✅/✅/✅（Nethunter 常用） | `htc_9271-1.4.0.fw` | **首选** |
| **RT5370** | `rt2800usb`（RT53XX） | 2.4G | ✅/✅/✅ | `rt2870.bin` | **便宜备选** |
| **RT5572** | `rt2800usb`（RT55XX） | 2.4G+5G | ✅/✅/✅ | `rt2870.bin` | 要 5GHz 选它 |
| **MT7601U** | `mt7601u` | 2.4G | 可用 | `mt7601u.bin` | 极便宜，功能较少 |
| **RTL8188EU** | `rtl8xxxu`（UNTESTED） | 2.4G | 有限 | `rtl8188efw.bin` | 不推荐当主力 |
| **RTL8812AU** | 树外驱动 | 2.4G+5G | 强 | 多 | **不在两套内核里，别买** |

**一句话**：买 **AR9271**（Nethunter/监听资料最多）或 **RT5370**（最便宜、AP/STA 稳）；
两者都在 OP12P 的 `wifi_modules` 和 mars los104 的驱动集里，买一个两边都能用。要 5GHz 就 RT5572。

## 4. 两边使用差异

- **mars los104**：驱动内建 + 固件内建。插上即可，无需 `insmod`，也无需改 `/vendor`。
- **OP12P**：`wifi_modules=true` 构建后，解包 `wifi-modules-6.1.141.tar.gz` 到
  `/data/local/tmp/wifi`，把 `firmware/*` 放到 `/vendor/firmware`（或 APatch 模块 overlay），
  再 `su -c 'sh /sdcard/load-wifi.sh'` 按依赖顺序 `insmod`。
  注意：OP12P 的 `fastbuild_6.1.141.yml` 已按 mars los104 对齐补上
  `RT33XX/RT35XX/RT3573/RT53XX/RT55XX/UNKNOWN=y` 与 `RTL8XXXU_UNTESTED=y`，
  因此 RT5370（RT53XX）、RT5572（RT55XX）在 OP12P 上也能用（下次带 `wifi_modules=true` 构建生效）。
  **AR9271 不依赖任何子选项，最稳**。

## 5. 验证命令（mars）

```bash
# 驱动是否注册
ls /sys/bus/usb/drivers | grep -E 'ath9k|rt2800|rt73|rtl8187|rtl8|mt7601|carl'

# 插入网卡后
dmesg | tail -30
ip link | grep -E 'wlan|usb'
lsusb

# 容器/Android 都能看到（Android 侧先起 wlanX；容器需要把网卡交给容器/或 host 网络）
```
