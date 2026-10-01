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

# ★★ 必须关掉的原厂开关:公开树(star-r-oss)里【没有它们依赖的实现】。
#    逐个由编译错误发现:
#      CONFIG_DEBUG_POWER_MI=y ⇒ kernel/power/suspend.c:94 调
#        pm_system_dbg_info_print() 且用 DEBUG_INFO_RPM_STATS /
#        DEBUG_INFO_RPM_MASTER_STATS,公开树头文件里没有声明 ⇒ 编译失败。
#    其余是同类"小米/高通私有 debug/回收/HW 抽象"开关,公开树大概率没有实现,
#    先一起关掉换一次干净的编译;之后按需再逐个打开。
DISABLE = (
    'CONFIG_DEBUG_POWER_MI',
    'CONFIG_MI_RECLAIM',
    'CONFIG_BOOTUP_RECLAIM',
    'CONFIG_CAM_RECLAIM',
    'CONFIG_MIHW',
    'CONFIG_MILLET',
    'CONFIG_MIGT',
    'CONFIG_MIUI_ZRAM_MEMORY_TRACKING',
    'CONFIG_MI_ZRAM_WRITEBACK_CONTROL',
    'CONFIG_ZRAM_WRITEBACK',
    'CONFIG_MI_UFS_FFU',
    'CONFIG_UFSGKI',
    'CONFIG_UFS_WB',
    'CONFIG_TLB_CONF_HANDLER',
    'CONFIG_HYFI_BRIDGE_HOOKS',
    'CONFIG_PASSTHROUGH_SYSTEM',
    'CONFIG_OEM_KERNEL',
    'CONFIG_PERF_CRITICAL_RT_TASK',
    'CONFIG_QGKI_SHOW_S2IDLE_WAKE_IRQ',
    'CONFIG_QCOM_SYSMON_SUBSYSTEM_STATS',
    'CONFIG_PACKAGE_RUNTIME_INFO',
    'CONFIG_SF_BINDER',
    'CONFIG_CLD',
    'CONFIG_QTI_PLH',
    'CONFIG_QTI_PLH_SCMI_CLIENT',
    'CONFIG_QTI_SCMI_PLH_PROTOCOL',
    'CONFIG_MTD_LAZYECCSTATS',
)

lines = open(path).read().splitlines()
out, flipped, kept, killed = [], [], [], []
seen = set()
for line in lines:
    m = re.match(r'^(CONFIG_[A-Za-z0-9_]+)=m$', line)
    my = re.match(r'^CONFIG_([A-Za-z0-9_]+)=y$', line)
    if my and ('CONFIG_' + my.group(1)) in DISABLE:
        out.append('# CONFIG_%s is not set' % my.group(1))
        killed.append('CONFIG_' + my.group(1))
        seen.add('CONFIG_' + my.group(1))
        continue
    if m and not any(m.group(1).startswith(k) for k in KEEP):
        out.append(m.group(1) + '=y')
        flipped.append(m.group(1))
    else:
        out.append(line)
        if m:
            kept.append(m.group(1))
# 原厂配置里没写、但我们要显式关掉的(例如默认 y 的私有开关)
for opt in DISABLE:
    if opt not in seen and any(l.startswith(opt + '=') for l in out):
        out = ['# %s is not set' % opt if l.startswith(opt + '=') else l for l in out]
        killed.append(opt)
open(path, 'w').write('\n'.join(out) + '\n')

print('m2y: 翻成内建 %d 项,保持模块 %d 项,关掉私有开关 %d 项'
      % (len(flipped), len(kept), len(killed)))
print('  翻成内建: ' + ', '.join(flipped))
print('  保持模块: ' + ', '.join(kept))
print('  关掉: ' + ', '.join(killed))
