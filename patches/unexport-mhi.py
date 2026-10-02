#!/usr/bin/env python3
"""取消导出 cnss2/qca_cld3_wlan 依赖的【RDDM/调试类 MHI 符号】。

★ 为什么(2026-10-02 实测,证据在 sde59):
  我们的内核用 MiCode/Xiaomi_Kernel_OpenSource@star-r-oss 构建,比手机原厂内核旧。
  vendor 模块 cnss2.ko(vermagic 完全匹配)在它的 init 里调用
    mhi_sync_power_up() / mhi_power_down() / mhi_scan_rddm_cookie() ...
  而在我们内核上,PCIe/MHI 端点起不来 ⇒ mhi_sync_power_up() 永不返回
  ⇒ modprobe 进程长期处于 D 状态,并且【死占 module_mutex】⇒ 之后所有 modprobe
  都卡在 `mutex_lock → do_init_module → load_module`。
  后果:/proc/modules 少 29 个模块 —— 含 msm_drm(显示本体)、cyttsp5*/fts_touch_
  spi_k2/xiaomi_touch(触摸)、qti_battery_charger_main(电池)、cnss2/icnss2/wlan。
  症状:卡在开机动画、屏幕/触摸/WiFi 全无,但内核本身健康(能稳定跑 11 分钟)。

★ 做法:把 cnss2 需要的这几个 RDDM/调试符号**取消导出**(函数本体保留,内核自己
  照常用,只是不再对模块导出)⇒ cnss2.ko 加载时立刻得到 "Unknown symbol" 而
  失败退出(而不是卡住)⇒ module_mutex 释放 ⇒ 其余模块正常装载。

★ 代价:WiFi 用不了(cnss2/qca_cld3_wlan/icnss2 都装不上),但换回**可用的系统**:
  显示、触摸、电池、USB adb 全部正常 ⇒ 之后可以在能拿到 shell 的前提下再修 WiFi。

用法: unexport-mhi.py [内核源码根目录,默认当前目录]
⚠️ 一个都没找到也不报错(不同树符号名可能不同),但会明确打印出来。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."

# cnss2.ko 未定义符号里,属于 RDDM / 调试通道的(几乎只有 WLAN 栈在用)
SYMS = (
    "mhi_scan_rddm_cookie",
    "mhi_dump_sfr",
    "mhi_force_rddm_mode",
    "mhi_download_rddm_img",
    "mhi_debug_reg_dump",
)

hits = []
for dirpath, _dirnames, filenames in os.walk(root):
    if "/.git" in dirpath:
        continue
    for fn in filenames:
        if not fn.endswith(".c"):
            continue
        p = os.path.join(dirpath, fn)
        try:
            s = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        orig = s
        for sym in SYMS:
            pat = re.compile(r"^(\s*)EXPORT_SYMBOL(_GPL)?\(\s*%s\s*\)\s*;" % re.escape(sym), re.M)
            def repl(m):
                hits.append((sym, p))
                return ("%s/* ★ mars 补丁:取消导出 %s —— 让 cnss2 快速失败而不是\n"
                        "%s *   卡死并死占 module_mutex(见 patches/unexport-mhi.py) */\n"
                        "%s//EXPORT_SYMBOL%s(%s);"
                        % (m.group(1), sym, m.group(1), m.group(1),
                           m.group(2) or "", sym))
            s = pat.sub(repl, s)
        if s != orig:
            open(p, "w", encoding="utf-8").write(s)

if hits:
    print("unexport-mhi: 已取消导出 %d 处:" % len(hits))
    for sym, p in hits:
        print("   %-26s %s" % (sym, p))
else:
    print("unexport-mhi: 一个符号都没找到(这棵树里可能不叫这些名字)—— 跳过")
