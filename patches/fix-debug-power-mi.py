#!/usr/bin/env python3
"""为 CONFIG_DEBUG_POWER_MI=y 补上公开树缺失的声明/枚举(只去掉两句调试打印)。

★ 背景(2026-10-02,CI run 36951823865 实测报错):
    ../kernel/power/suspend.c:94:2: error: implicit declaration of function
        'pm_system_dbg_info_print'
    ../kernel/power/suspend.c:94:27: error: use of undeclared identifier
        'DEBUG_INFO_RPM_STATS'
    ../kernel/power/suspend.c:95:27: error: use of undeclared identifier
        'DEBUG_INFO_RPM_MASTER_STATS'
    (128/129 行同样两处)
  ⇒ 公开树(MiCode/Xiaomi_Kernel_OpenSource star-r-oss)里没有这些声明。

★ 为什么不能像以前那样直接关掉 CONFIG_DEBUG_POWER_MI:
   它是 power_debug_print_enabled 的来源,而原厂
   /vendor/lib/modules/qti_battery_charger_main.ko 缺这个符号就装不上
   (症状:电量永远显示 100%、充电状态不更新)。
   同理 CONFIG_OEM_KERNEL 等 27 个私有开关也都是当初"为了编译能过"
   一刀切关掉的,实测代价极大 ⇒ 现在改为【保留开关 + 补声明】。

用法: fix-debug-power-mi.py [内核源码根目录,默认当前目录]
⚠️ 不匹配就报错退出(CI 不加 continue-on-error),避免静默失效。
"""
import sys
import os

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/power/suspend.c")

OLD = """#ifdef CONFIG_DEBUG_POWER_MI
	pm_system_dbg_info_print(DEBUG_INFO_RPM_STATS);
	pm_system_dbg_info_print(DEBUG_INFO_RPM_MASTER_STATS);
#endif"""

NEW = """#ifdef CONFIG_DEBUG_POWER_MI
	/*
	 * ★ Droidspaces:公开树里没有 pm_system_dbg_info_print() 的声明,
	 *   也没有 DEBUG_INFO_RPM_STATS / DEBUG_INFO_RPM_MASTER_STATS 这两个枚举,
	 *   所以 CONFIG_DEBUG_POWER_MI=y 会编译失败(见本文件 patches/fix-debug-power-mi.py)。
	 *   但我们必须保留 CONFIG_DEBUG_POWER_MI=y —— 它是
	 *   power_debug_print_enabled 的来源,原厂 qti_battery_charger_main.ko
	 *   缺它就装不上(电量永远 100%)。这里只去掉这两句调试打印。
	 */
#endif"""

src = open(path).read()
if "Droidspaces:公开树里没有 pm_system_dbg_info_print" in src:
    print("fix-debug-power-mi: 已经打过补丁,跳过")
    sys.exit(0)
n = src.count(OLD)
if n == 0:
    print("::error::fix-debug-power-mi: 在 %s 里没找到预期代码块" % path)
    sys.exit(1)
src = src.replace(OLD, NEW)
open(path, "w").write(src)
print("fix-debug-power-mi: 已处理 %d 处调试打印(保留 CONFIG_DEBUG_POWER_MI=y)" % n)
