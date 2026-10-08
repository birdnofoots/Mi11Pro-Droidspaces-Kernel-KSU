// SPDX-License-Identifier: GPL-2.0
/*
 * mi_syms_los.c —— LOS 5.4.242 树上【精确】需要的内核符号桩
 *   来源: 把手机 /vendor 的 272 个原厂模块逐个做"未定义符号 − 内核导出 − 其他 vendor 模块导出"
 *         的差集计算,只剩 2 个模块有缺口:
 *           mi_memory.ko : get_ufs_data / get_ufs_hba_data / get_ufs_sdev_data /
 *                          ufs_get_string_desc / ufshcd_read_desc / ufs_read_desc_param /
 *                          memblock_mem_size_in_gb
 *           msm_drm.ko   : mi_display_pm_suspend_callback_set   ← 缺它 ⇒ 显示模块装不上(黑屏)
 *   另加 qti_battery_charger_main.ko 需要的 power_debug_print_enabled / mi_power_save_battery_cave
 *   (老配方 mi_syms.c 里那批 msm_pcie_ 前缀 / mhi_force_reset 桩,在 LOS 树上内核已导出,绝不能重复导出)
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/types.h>

/* ── 充电/电池: qti_battery_charger_main.ko ── */
int power_debug_print_enabled;
EXPORT_SYMBOL(power_debug_print_enabled);

int mi_power_save_battery_cave(void)
{
	return 0;
}
EXPORT_SYMBOL(mi_power_save_battery_cave);

/* ── 显示: msm_drm.ko 必需 ── */
int mi_display_pm_suspend_callback_set(void)
{
	return 0;
}
EXPORT_SYMBOL(mi_display_pm_suspend_callback_set);

/* ── mi_memory.ko: UFS/内存统计(原型未知 ⇒ 返回 NULL/0) ── */
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

/* ── allbuiltin(=m 全翻 =y) 时,内建 Xiaomi 胶水(thermal/mi_disp)会引用这些"原厂 msm_drm.ko 私有"符号 ──
 *   老配方 mi_syms.c 的经验: 这两个 display 符号【只能定义、不能导出】,否则原厂 msm_drm.ko 会被拒装;
 *   allbuiltin 下原厂 msm_drm.ko 本来就装不进来(与内建显示代码重名),所以这里只做"过链接"的空实现。
 */
int mi_disp_register_client(void *client)
{
	return 0;
}

int mi_disp_unregister_client(void *client)
{
	return 0;
}

int dsi_display_primary_request_fod_hbm(void)
{
	return 0;
}

/* ── WLAN: 原厂 qca_cld3_wlan.ko 还缺这两个符号(原本由原厂 mi_cnss_statistic.ko 导出) ──
 *   若走"只放行 qca_cld3_wlan + qca_cld3_qca6390(不放行 mi_cnss_statistic)"的定向门禁,
 *   就必须由内核补这两个桩,否则模块装不上(Unknown symbol)。
 *   类型按原厂模块里的实际大小对齐: wow_suspend_type = 1 字节对象; 唤醒函数返回 0。
 */
u8 wow_suspend_type;
EXPORT_SYMBOL(wow_suspend_type);

unsigned long cnss_statistic_wow_wakeup(void)
{
	return 0;
}
EXPORT_SYMBOL(cnss_statistic_wow_wakeup);
