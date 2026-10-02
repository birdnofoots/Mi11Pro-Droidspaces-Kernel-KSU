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

/* ── WLAN PCIe/MHI 链路:cnss2.ko / icnss2.ko 需要 ──────────────────
 *
 * 这几个函数在【公开树里根本不存在】(已核实:drivers/pci/controller/dwc/
 * pcie-qcom.c 里没有 msm_pcie_*,drivers/bus/mhi/core/mhi_main.c 里没有
 * mhi_force_reset)⇒ 属于 MIUI 私有实现,没法靠改配置补出来 ✗。
 *
 * 语义取舍:
 *   - msm_pcie_reg_dump()          : 纯调试 dump ⇒ 空实现无害 ✓
 *   - msm_pcie_set_target_link_speed: 设链路速率;空实现=保持 bootloader
 *                                     配好的速率不变 ⇒ 正常联网不受影响 ✓
 *   - msm_pcie_dsp_link_control()  : DSP(音频)侧链路控制 ⇒ 返回 0 不干预 ✓
 *   - mhi_force_reset()            : 只在 WLAN SSR(异常恢复)时调用 ⇒
 *                                     空实现只影响"出错后自愈" ✗,不影响正常联网 ✓
 * ⇒ 先让模块能装载、看 WiFi 能否正常起来;若 SSR 相关不稳,再另想办法 ✗。
 */
int msm_pcie_reg_dump(void)
{
	return 0;
}
EXPORT_SYMBOL(msm_pcie_reg_dump);

int msm_pcie_set_target_link_speed(void)
{
	return 0;
}
EXPORT_SYMBOL(msm_pcie_set_target_link_speed);

int msm_pcie_dsp_link_control(void)
{
	return 0;
}
EXPORT_SYMBOL(msm_pcie_dsp_link_control);

int mhi_force_reset(void)
{
	return 0;
}
EXPORT_SYMBOL(mhi_force_reset);
