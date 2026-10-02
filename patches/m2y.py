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
import os
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else \
    'arch/arm64/configs/vendor/mars_qgki_ds_defconfig'
KEEP = ('CONFIG_ICNSS2', 'CONFIG_CNSS2', 'CONFIG_MEDIA_TUNER_')

# ★ 2026-10-02 新增开关:M2Y_NOFLIP=1 ⇒ 【不把 =m 翻成 =y】,只做 DISABLE。
#   原因(实测,决定性证据在 sde59 logdump):
#     star-stock 把 62 个 =m 翻成 =y,但设备 /vendor/lib/modules 里【同名 .ko 仍在】,
#     Android init 照旧 modprobe 它们 ⇒ 内核日志出现
#       "Driver 'qcom_llcc_perfmon' is already registered, aborting"
#       "Driver 'stmvl53l5' is already registered, aborting"
#       "Driver 'qcom,sn-nci' is already registered, aborting"
#     最后 WLAN 栈卡死:uptime 129.3s 处
#       init: Sending signal 9 to service 'exec 24 (/vendor/bin/modprobe -a -d
#             /vendor/lib/modules/ qca_cld3_wlan qca_cld3_qca6390)'
#     ⇒ init 超时 SIGKILL 之后整个系统停住 ⇒ bootloader 判失败 ⇒ fastboot/回退。
#   而原厂 config 原样的 star-ds 之所以"能开机"(但触摸/电池/WLAN 全废),
#   是因为那些 vendor .ko 加载失败得【很快】,不卡。
#   ⇒ 正确做法:保持 =m(让 /vendor 的原厂 .ko 去装),不要内建。
NOFLIP = os.environ.get('M2Y_NOFLIP', '').strip().lower() not in ('', '0', 'no', 'false')

# ★★ 必须关掉的原厂开关
#    ★ 2026-10-02 重要修正:原来这里列了 27 个"小米/高通私有 debug/回收/HW 抽象"
#      开关,当初只是为了"一次编译能过"就一刀切关掉(见旧注释),**并没有证据**
#      它们编不过。实测后果:关掉 CONFIG_OEM_KERNEL 之后,原厂 .ko 需要的
#      power_debug_print_enabled / mi_power_save_battery_cave 等符号全没了,
#      而且【PMIC 会在开机后几十秒 ~ 2.5 分钟硬复位】(日志里
#      "IRQ pmic-wd-bark not found" + 无任何关机信息直接断掉),
#      刷了 v3(三个内核侧补丁都打上)依旧每轮重启 ⇒ 复位来自 PMIC 硬件,
#      与内核里那段 MIUI 诊断代码无关。
#      ⇒ 恢复原厂值,只保留真正必要的 CONFIG_MODVERSIONS(关符号 CRC 校验,
#        让原厂 vendor .ko 能装进来)。
#      ⚠️ 若某个开关真的编不过,就把它单独加回本列表(并把报错记在下面)。
DISABLE = (
    # ★ 关键:关掉符号 CRC 校验 ⇒ 原厂 vendor 模块(WLAN/相机/音频/ADSP)才能装进来。
    #   vermagic 里的 "modversions " 字样由 patches/vermagic.py 补上。
    'CONFIG_MODVERSIONS',
    # ★ 2026-10-02 追加:斩断"子系统异常 → panic → 看门狗咬 → PS_HOLD 硬复位"这条链。
    #   实测(sde59 日志):内核能正常跑到 134 秒、无 panic 输出就硬复位;
    #   关掉这两项后,即便有 oops/SSR 超时也只会【打印并继续】⇒ 日志能留下现场,
    #   同时不再每 2 分钟复位一次。诊断期结束可以再打开。
    'CONFIG_PANIC_ON_OOPS',
    'CONFIG_PANIC_ON_SSR_NOTIF_TIMEOUT',
    'CONFIG_QCOM_FORCE_WDOG_BITE_ON_PANIC',
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
    if m and not NOFLIP and not any(m.group(1).startswith(k) for k in KEEP):
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

print('m2y: 翻成内建 %d 项,保持模块 %d 项,关掉私有开关 %d 项%s'
      % (len(flipped), len(kept), len(killed),
         '  [NOFLIP:按原厂保持 =m]' if NOFLIP else ''))
print('  翻成内建: ' + ', '.join(flipped))
print('  保持模块: ' + ', '.join(kept))
print('  关掉: ' + ', '.join(killed))
