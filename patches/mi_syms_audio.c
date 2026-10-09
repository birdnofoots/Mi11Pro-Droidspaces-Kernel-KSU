// SPDX-License-Identifier: GPL-2.0
/*
 * mi_syms_audio.c —— 音频链必需的小米私有符号桩(可选, CI 输入 mi_syms_audio=1)
 *
 * 背景(2026-10-10 实测): 原厂 /vendor/lib/modules/mbhc_dlkm.ko(main 目录那份) 引用
 *   is_early_cons_enabled —— 小米私有(early console 打印开关), LOS 树没有 ⇒ 装不上
 *   ⇒ wcd_mbhc_* 符号缺失 ⇒ wcd938x_dlkm / wcd937x_dlkm / swr_dmic_dlkm / machine_dlkm
 *   全部连锁装不上 ⇒ /proc/asound/cards 为空 ⇒ 手机没声音。
 * 我们恒返回 false(等于"没开 early console"), 对音频无副作用。
 * 备选: 直接用 /vendor/lib/modules/5.4-gki/mbhc_dlkm.ko(那份不引用此符号), 但混用两个目录的
 *   不同编译版本会让 ASoC 卡注册报 -16(control already present), 所以正解是补这个桩、
 *   让 MIUI 自己用同一套 main 模块按原厂顺序装。
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/types.h>

bool is_early_cons_enabled(void)
{
	return false;
}
EXPORT_SYMBOL(is_early_cons_enabled);
