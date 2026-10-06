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
KEEP = (
    'CONFIG_ICNSS2', 'CONFIG_CNSS2', 'CONFIG_MEDIA_TUNER_',
    # ★ 2026-10-03 P1 根因(sde59 logdump @79s, swapper/0 D-state):
    #   fts_driver_init → fts_probe → fts_fw_update → getFWdata
    #     → request_firmware → firmware_fallback_sysfs
    #     → wait_for_completion_killable_timeout   ← 在 kernel_init 里等用户态喂固件
    #   内建驱动在 userspace 起来前 probe ⇒ 永远等不到 firmware helper ⇒ 整机卡死。
    #   保持 =m,让 probe 推迟到模块加载(此时 /vendor/firmware 已可读)。
    'CONFIG_TOUCHSCREEN_ST_FTS',
    # ★ 2026-10-04 p1i7 失败根因: XIAOMI_TOUCHFEATURE 被翻成 =y 后:
    #   1) 内建 xiaomi_touch 占名 ⇒ 原厂 xiaomi_touch.ko 装不上;
    #   2) 其 10 个接口符号又被 NAMES 去导出 ⇒ 内建也不给符号;
    #   3) fts_touch_spi_k2 depends=xiaomi_touch ⇒ modprobe 依赖解析失败,fts 永不装载。
    #   实锤: p1i7 logdump 里 xiaomi_touch_dev_ioctl 在跑(内建框架),但 0 条 fts/hwid。
    #   保持 =m,让原厂 xiaomi_touch.ko 装载并导出 fts 需要的全部符号。
    'CONFIG_TOUCHSCREEN_XIAOMI_TOUCHFEATURE',
)

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
    # ★★★ 2026-10-03 根因修复(决定性):struct module 必须与原厂逐字段一致 ★★★
    #   证据(sde59 logdump + CI faddr2line):
    #     load_module+0x75c   = add_unformed_module  kernel/module.c:3733
    #     do_init_module+0xbc = do_init_module       kernel/module.c:3655
    #   现象:7 个 modprobe 永久卡在 module_mutex / module_wq;msm_drm 加载不上;
    #        cyttsp5/xiaomi_touch/camera/qti_battery_charger/leds_qti_flash/
    #        mi_thermal_interface/fts_touch_spi_k2 全是 msm_drm 的下游 ⇒ 显示全废。
    #   原因:kernel/trace/Kconfig 里
    #          config FTRACE_MCOUNT_RECORD { def_bool y; depends on DYNAMIC_FTRACE }
    #        我们开了 FUNCTION_TRACER/DYNAMIC_FTRACE ⇒ struct module 里多出
    #          unsigned int num_ftrace_callsites; unsigned long *ftrace_callsites;
    #        把其后的 source_list/target_list/exit/refcnt 全部顶偏 16 字节;
    #        而 vendor .ko 内嵌的 struct module 是按【原厂布局】编译的,
    #        且 MODVERSIONS=n 关掉了唯一能拦住它的 module_layout 校验
    #        ⇒ 内核按错误偏移读写原厂模块的引用计数与依赖链表 ⇒ 加载器死锁。
    #   原厂 /proc/config.gz:FUNCTION_TRACER 未设置、DYNAMIC_FTRACE 未设置。
    'CONFIG_FUNCTION_TRACER',
    'CONFIG_DYNAMIC_FTRACE',
    'CONFIG_FUNCTION_GRAPH_TRACER',
    'CONFIG_DYNAMIC_FTRACE_WITH_REGS',
    'CONFIG_FTRACE_MCOUNT_RECORD',
    # ⚠️ 2026-10-03:曾把 CONFIG_FW_LOADER_USER_HELPER_FALLBACK 关掉(想让读不到固件的模块
    #   快速失败,拆掉"模块init↔用户态"的循环等待),但实测那版内核【启动前就死】(连 logdump
    #   记录都没写),而 FALLBACK=y 的 c4fc2d02 能正常跑到 50s 以上。⇒ 已回退。
    #   循环等待改用【把固件回退超时 60s 改小】的方式解决(见 patches/fw-timeout.py)。
)

# ★★ 2026-10-02:整项彻底关掉(无论原厂是 =y 还是 =m)。
#    与 unexport-mhi.py 配合:取消导出 cnss2 依赖的 RDDM/调试 MHI 符号后,
#    树内自带的 cnss2.ko(CONFIG_CNSS2=m)会因 undefined 让 modpost 失败,
#    所以把树内 CNSS2 一并关掉。设备 /vendor 里那个“原厂 cnss2.ko”仍在,
#    init 会去装它,但它同样找不到这些符号 ⇒ 立刻 "Unknown symbol" 失败退出
#    (而不是卡在 init 里死占 module_mutex),其余驱动即可正常装载。
# ★★ 2026-10-03:即使 NOFLIP(不翻 =m→=y),这些也必须【强制内建】。
#   实测:设备 /vendor/lib/modules 里没有它们的 .ko(只有 qca_cld3_*/exfat 等),
#   而我们自己编的模块不会装到设备上 ⇒ =m 等于没有。
#   · MAC80211      : 厂商 qca_cld3_wlan.ko 依赖内核内建的 mac80211(原厂就是 =y)
#   · 下面 6 项     : Droidspaces 容器网络(macvlan/ipvlan/vxlan/nftables/NAT)
FORCE_Y = (
    'CONFIG_MAC80211',
    'CONFIG_MACVLAN',
    'CONFIG_IPVLAN',
    'CONFIG_VXLAN',
    'CONFIG_NF_TABLES',
    'CONFIG_NF_TABLES_INET',
    'CONFIG_NFT_NAT',
    'CONFIG_NF_NAT',
    'CONFIG_NETFILTER_XT_TARGET_MASQUERADE',
    'CONFIG_IP_NF_NAT',
    'CONFIG_IP_NF_TARGET_MASQUERADE',
    # ★ 2026-10-06 撤销 2026-10-05 加的 FORCE_Y —— 它反而制造了死锁(静态矩阵实锤,见 CHECKLIST §13):
    #   内建 ⇒ vmlinux 导出 xiaomi_touch 定义的 9 个符号 ⇒ 原厂 xiaomi_touch.ko 被拒装
    #        ⇒ fts_touch_spi_k2 的 modprobe 依赖链(→xiaomi_touch)断掉 ⇒ fts 永不装载;
    #        即便装上,fts 也只能拿到 mi_syms.c 里的【空桩】。
    #   ⇒ 交回上面的 KEEP:保持 =m,让原厂 xiaomi_touch.ko 装载并提供【真实现】。
    #   (同一修复还要求 mi_syms.c 里那 2 个桩「只定义、不导出」—— 已在 2026-10-06 一并改掉。)
)

KILL = ()   # ★ 2026-10-02 22:5x 实测:关掉 CONFIG_CNSS2 会让内核启动前就复位 ⇒ 清空,改用别的办法

lines = open(path).read().splitlines()
out, flipped, kept, killed, forced = [], [], [], [], []
seen = set()
for line in lines:
    m = re.match(r'^(CONFIG_[A-Za-z0-9_]+)=m$', line)
    my = re.match(r'^CONFIG_([A-Za-z0-9_]+)=y$', line)
    mz = re.match(r'^(CONFIG_([A-Za-z0-9_]+))=[ym]$', line)
    if mz and ('CONFIG_' + mz.group(2)) in KILL:
        out.append('# CONFIG_%s is not set' % mz.group(2))
        killed.append('CONFIG_' + mz.group(2))
        seen.add('CONFIG_' + mz.group(2))
        continue
    if my and ('CONFIG_' + my.group(1)) in DISABLE:
        out.append('# CONFIG_%s is not set' % my.group(1))
        killed.append('CONFIG_' + my.group(1))
        seen.add('CONFIG_' + my.group(1))
        continue
    mn = re.match(r'^# (CONFIG_[A-Za-z0-9_]+) is not set$', line)
    cand = None
    if m:
        cand = m.group(1)
    elif mn:
        cand = mn.group(1)
    if cand and cand in FORCE_Y:
        out.append(cand + '=y')
        forced.append(cand)
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

print('m2y: 强制内建 %d 项: %s' % (len(forced), ', '.join(forced)))
print('m2y: 翻成内建 %d 项,保持模块 %d 项,关掉私有开关 %d 项%s'
      % (len(flipped), len(kept), len(killed),
         '  [NOFLIP:按原厂保持 =m]' if NOFLIP else ''))
print('  翻成内建: ' + ', '.join(flipped))
print('  保持模块: ' + ', '.join(kept))
print('  关掉: ' + ', '.join(killed))
