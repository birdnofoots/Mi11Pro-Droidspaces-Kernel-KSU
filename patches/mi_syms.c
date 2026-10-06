// SPDX-License-Identifier: GPL-2.0
/*
 * mi_syms.c —— 为【原厂 vendor 模块】补上 MIUI 私有内核符号(桩实现)
 *
 * ★★ 2026-10-02 实测结论(有据可查,别再走回头路):
 *   1) 自编内核已解决 vermagic / MODVERSIONS 两道闸门 ⇒ 原厂 .ko 大部分能装进来;
 *      但仍有约 38 个模块装不进来,原因是缺下面这些符号。
 *   2) 曾经以为"恢复 27 个 MIUI 私有开关(含 CONFIG_OEM_KERNEL=y、
 *      CONFIG_DEBUG_POWER_MI=y)真实现就会回来" —— **实测不成立**:
 *      run 36952631227 用内核镜像(含 kallsyms)逐个核对,
 *        power_debug_print_enabled         出现 0 次
 *        mi_power_save_battery_cave        出现 0 次
 *        mi_display_pm_suspend_callback_set 出现 0 次
 *        msm_pcie_dsp_link_control         出现 0 次
 *        mhi_force_reset                   出现 0 次
 *      并核对 drivers/pci/controller/dwc/pcie-qcom.c 与
 *      drivers/bus/mhi/core/mhi_main.c 里根本没有 msm_pcie_* / mhi_force_reset。
 *      ⇒ 这些是【公开树里压根不存在的私有实现】,无法靠改配置补出来。
 *   3) 所以本文件的桩必须**无条件导出**(不能加 `#if !IS_ENABLED(CONFIG_OEM_KERNEL)`
 *      之类的保护 —— 那种保护只会让唯一的来源消失)。
 *      唯一保留的条件编译是 refcount_warn_saturate 的 CONFIG_REFCOUNT_FULL,
 *      因为那个符号在内核里存在时会由内核自己导出,加桩会重复定义。
 *
 * 症状对照:
 *   缺 power_debug_print_enabled / mi_power_save_battery_cave
 *     ⇒ qti_battery_charger_main.ko 装不上 ⇒ 电量永远 100% ✗
 *   缺 refcount_warn_saturate
 *     ⇒ qca_cld3_wlan.ko 装不上 ⇒ WiFi 打不开 ✗
 *   缺 msm_pcie_ 系列与 mhi_force_reset
 *     ⇒ cnss2/icnss2(WLAN 的 PCIe 栈)装不上 ⇒ WiFi 也起不来 ✗
 *   缺 mi_display_pm_suspend_callback_set ⇒ msm_drm.ko 装不上(显示靠内建驱动撑着)
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/types.h>
#include <linux/printk.h>
#include <linux/bug.h>

/* ── 充电/电池:qti_battery_charger_main.ko 需要 ───────────────────── */
int power_debug_print_enabled;
EXPORT_SYMBOL(power_debug_print_enabled);

/*
 * 原型未知 → 用 (void) 定义:ARM64 调用约定下实参留在寄存器里,
 * 被调方不读即无副作用;返回 0 表示"不干预"。
 */
int mi_power_save_battery_cave(void)
{
	return 0;
}
EXPORT_SYMBOL(mi_power_save_battery_cave);

/* ── WLAN:qca_cld3_wlan.ko 需要 ───────────────────────────────────
 *    仅当内核自己没有导出该符号时才补桩(MIUI 真实现存在时会重复定义)。
 */
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
 *    语义取舍:
 *     msm_pcie_reg_dump()            : 纯调试 dump ⇒ 空实现无害
 *     msm_pcie_set_target_link_speed : 空实现=保持 bootloader 配好的速率 ⇒ 正常联网不受影响
 *     msm_pcie_dsp_link_control()    : DSP(音频)侧链路控制 ⇒ 返回 0 不干预
 *     mhi_force_reset()              : 只在 WLAN SSR(异常恢复)时调用 ⇒ 只影响"出错后自愈"
 */
int __weak msm_pcie_reg_dump(void)
{
	return 0;
}
EXPORT_SYMBOL(msm_pcie_reg_dump);

int __weak msm_pcie_set_target_link_speed(void)
{
	return 0;
}
EXPORT_SYMBOL(msm_pcie_set_target_link_speed);

int __weak msm_pcie_dsp_link_control(void)
{
	return 0;
}
EXPORT_SYMBOL(msm_pcie_dsp_link_control);

int __weak mhi_force_reset(void)
{
	return 0;
}
EXPORT_SYMBOL(mhi_force_reset);

/* ── UFS/内存统计:mi_memory.ko 需要(实测日志:125.126 处 7 个 Unknown symbol) ──
 *   原型未知 ⇒ 一律返回 NULL/0(该模块只是 MIUI 的内存 sysfs 辅助功能,
 *   返回空值最多让那几个 sysfs 属性没数据,不会崩)。
 */
void *get_ufs_data(void) { return NULL; }
EXPORT_SYMBOL(get_ufs_data);

void *get_ufs_hba_data(void) { return NULL; }
EXPORT_SYMBOL(get_ufs_hba_data);

void *get_ufs_sdev_data(void) { return NULL; }
EXPORT_SYMBOL(get_ufs_sdev_data);

int ufs_get_string_desc(void) { return 0; }
EXPORT_SYMBOL(ufs_get_string_desc);

int ufshcd_read_desc(void) { return 0; }
EXPORT_SYMBOL(ufshcd_read_desc);

int ufs_read_desc_param(void) { return 0; }
EXPORT_SYMBOL(ufs_read_desc_param);

unsigned long memblock_mem_size_in_gb(void) { return 0; }
EXPORT_SYMBOL(memblock_mem_size_in_gb);

/* ── ★ v5:MIUI 热控(内建 drivers/thermal/thermal_core.c:2080/2103)要用这两个符号 ──
 *   矛盾点:这两个名字**同时是 vendor msm_drm.ko 的导出**(在 43 个撞名清单里)⇒
 *          内核【绝对不能导出】它们,否则 msm_drm.ko 会被 verify_exported_symbols 拒装 ✗;
 *          但内建 thermal 在 vmlinux 链接期又必须能找到符号 ✗。
 *   解法:**只定义、不导出**(EXPORT_SYMBOL 一个都不加)——
 *         内建代码链接 ✓,内核导出表里没有它们 ✓,vendor 模块照常提供真实现 ✓。
 *   语义:返回 0(成功)、忽略参数 ⇒ thermal 收不到显示事件通知,不影响开机 ✓。
 *   触发背景:v4 去掉内建 techpack 显示驱动后,链接报
 *          ld.lld: undefined symbol: mi_disp_register_client / _unregister
 *          >>> referenced by thermal_core.c:2080 / 2103
 */
int mi_disp_register_client(void *client)
{
	return 0;
}

int mi_disp_unregister_client(void *client)
{
	return 0;
}

/* ── ★ 2026-10-06 修正(静态矩阵实锤,见 CHECKLIST §13):这 2 个桩【只能定义、不能导出】──
 *   fts_touch_spi_k2.ko 需要 last_touch_events_collect / update_fod_press_status;
 *   而这 2 个名字【同时是原厂 xiaomi_touch.ko 的导出】。
 *   2026-10-05 曾在这里 EXPORT_SYMBOL ⇒ 内核对 xiaomi_touch.ko 构成占名 ⇒ 原厂模块被拒装
 *   ⇒ fts 的 modprobe 依赖链(xiaomi_touch)断掉;而且即便 fts 装上,它调到的也只是这里的【空实现】。
 *   现改为「只定义、不导出」(与上面的 mi_disp_register_client 同一手法):
 *   ⇒ 原厂 xiaomi_touch.ko 得以装载,并由它把【真实现】提供给 fts。
 *   ⚠️ 保留定义是为了过链接;若编译报"重复定义",说明真实现已在 vmlinux ⇒ 直接删掉这个桩。
 */
void last_touch_events_collect(void *data, int len)
{
}

void update_fod_press_status(int value)
{
}


