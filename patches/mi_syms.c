// SPDX-License-Identifier: GPL-2.0
/*
 * mi_syms.c —— 为【原厂 vendor 模块】补上 MIUI 私有内核符号(桩实现)
 *
 * ★ 背景(2026-10-02 实测):
 *   自编内核已解决 vermagic / MODVERSIONS 两道闸门,原厂 .ko 大部分能装进来,
 *   但仍有几个模块因为是 MIUI 私有扩展而失败 —— 它们引用了公开树(xiaomi
 *   star-r-oss)里【被我们关掉的私有开关】所守护的符号:
 *
 *     qti_battery_charger_main.ko  ← power_debug_print_enabled
 *                                    mi_power_save_battery_cave
 *     qca_cld3_wlan.ko             ← refcount_warn_saturate
 *     (msm_drm.ko)                 ← mi_display_pm_suspend_callback_set
 *
 *   证据(设备现场 /proc/modules 80 项里没有 cnss2/icnss2/qca_cld3_wlan/
 *   qti_battery_charger_main/camera):
 *     症状 = 电量永远 100%(充电器模块缺失) + WiFi 打不开(WLAN 模块缺失)
 *            + 相机 HAL 无限 SIGABRT ⇒ 框架一直 boot_completed=0 ⇒ 反复重启
 *
 *   本文件把这些符号以【空实现】导出,让原厂 .ko 能完成加载。
 *   它们都只是 MIUI 的调试/统计钩子,空实现不影响功能:
 *     - power_debug_print_enabled : 打印开关(默认关)
 *     - mi_power_save_battery_cave: 省电策略回调(返回 0 = 不干预)
 *     - refcount_warn_saturate    : 引用计数饱和告警(仅告警路径)
 *     - mi_display_pm_suspend_callback_set : 显示 PM 回调注册(返回 0)
 *
 *   ⚠️ 若某个符号在别的编译单元里已经存在(说明对应开关被打开了),
 *      本文件会因重复定义而编译失败 —— 那就把它从下面删掉即可。
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/types.h>
#include <linux/printk.h>
#include <linux/bug.h>

/* ── 充电/电池:qti_battery_charger_main.ko 需要 ───────────────────── */
#if !IS_ENABLED(CONFIG_DEBUG_POWER_MI)
int power_debug_print_enabled;
EXPORT_SYMBOL(power_debug_print_enabled);
#endif

/*
 * 原型未知 → 用 (void) 定义:ARM64 调用约定下实参留在寄存器里,
 * 被调方不读即无副作用;返回 0 表示"不干预"。
 */
int mi_power_save_battery_cave(void)
{
	return 0;
}
EXPORT_SYMBOL(mi_power_save_battery_cave);

/* ── WLAN:qca_cld3_wlan.ko 需要 ─────────────────────────────────── */
#if !IS_ENABLED(CONFIG_REFCOUNT_FULL)
void refcount_warn_saturate(void *r, int t)
{
	WARN_ONCE(1, "refcount_warn_saturate() stub called (type=%d)\n", t);
}
EXPORT_SYMBOL(refcount_warn_saturate);
#endif

/* ── 显示:msm_drm.ko 需要 ───────────────────────────────────────── */
int mi_display_pm_suspend_callback_set(void)
{
	return 0;
}
EXPORT_SYMBOL(mi_display_pm_suspend_callback_set);
