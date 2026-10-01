#!/usr/bin/env python3
"""把 defconfig 里的 `=m` 选择性翻成 `=y`(编进内核)。

★ 为什么需要:
  原厂把【触摸 / 充电 / 指纹 / 蓝牙 / NFC / SLIMBUS / MIUI 接口】这些驱动
  都做成模块(=m);而原厂的 .ko 装不进自编内核(Module.symvers 的 CRC 不匹配,
  见 TAKEOVER.md §3 第 13 条)⇒ 这些功能在自编内核上全废:
    失败启动日志里的证据:
      android.hardware.health@2.1-service.qti: Cannot open battery/capacity, fd=-1
      E TouchSensorLargeArea: open /sys/class/touch/touch_dev/palm_sensor failed!
      healthd: No battery devices found
      init: wait /sys/class/power_supply/usb/type 超时 5009ms
  最省事的做法:把它们直接编进内核(=y),不依赖任何用户态加载。

★ 保留为模块(实测必须):
  * CONFIG_ICNSS2 / CONFIG_CNSS2 —— run 36877538492 实测 `CONFIG_ICNSS2=y` 编译失败:
    drivers/soc/qcom/icnss2/qmi.h 里的 static inline 与真声明冲突
    (wlfw_wlan_mode_send_sync_msg)。WLAN 栈暂缓,等模块加载方案(mod6)。
  * CONFIG_MEDIA_TUNER_* —— 电视调谐器,手机用不到,保持模块避免无谓风险。

用法: m2y.py [defconfig 路径]
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else \
    'arch/arm64/configs/vendor/mars_qgki_ds_defconfig'
KEEP = ('CONFIG_ICNSS2', 'CONFIG_CNSS2', 'CONFIG_MEDIA_TUNER_')

lines = open(path).read().splitlines()
out, flipped, kept = [], [], []
for line in lines:
    m = re.match(r'^(CONFIG_[A-Za-z0-9_]+)=m$', line)
    if m and not any(m.group(1).startswith(k) for k in KEEP):
        out.append(m.group(1) + '=y')
        flipped.append(m.group(1))
    else:
        out.append(line)
        if m:
            kept.append(m.group(1))
open(path, 'w').write('\n'.join(out) + '\n')

print('m2y: 翻成内建 %d 项,保持模块 %d 项' % (len(flipped), len(kept)))
print('  翻成内建: ' + ', '.join(flipped))
print('  保持模块: ' + ', '.join(kept))
