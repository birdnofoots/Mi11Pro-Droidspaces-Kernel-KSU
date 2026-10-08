#!/usr/bin/env python3
# wlan-gate.py —— 把 WLAN 白名单改成【运行时开关】，彻底消除 bootloop 风险
#
# 动机(2026-10-07):
#   WLAN 是最后一块拼图,但历史上"放行 WLAN 栈"的镜像都循环重启过。而白名单是
#   **编译期静态数组**(kernel/module.c 的 mars_mod_allow[]),一旦放行,init 会在每次
#   开机时自动 modprobe 整条链 ⇒ 只要链里有一个模块会崩,就必然 bootloop,
#   只能靠 USB 重插 + fastboot 回刷救机 —— 这会打断"本地编译→dd 刷机→读日志"的自动闭环。
#
#   本补丁把名单拆成两份:
#     · mars_mod_allow[]      —— 已验证能开机的模块,**永远放行**;
#     · mars_mod_allow_gated[]—— 待验证的模块(WLAN 链),**仅当 mars_wlan_allow=1 时放行**。
#   开关通过 core_param 暴露:
#       /sys/module/kernel/parameters/mars_wlan_allow   (默认 0)
#
#   ⇒ 刷进去之后:默认行为与"不放行 WLAN"完全一致 ⇒ 开机安全;
#     想测时 root 写 1,再手动逐个 insmod,每步看 dmesg/是否存活;
#     哪个模块崩了也不怕 —— 重启后开关自动回到 0,系统照常起来。**闭环不中断。**
#
# 用法: python3 patches/wlan-gate.py <kernel 树根>
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
P = os.path.join(ROOT, 'kernel/module.c')

# 待验证(受开关控制)的模块名单 —— 与 init.target.rc:272 的实际加载链一致
GATED = [
    "device_management_service_v01",
    "wlan_firmware_service_v01",
    "mi_cnss_statistic",
    "cnss2",
    "qca_cld3_wlan",
    "qca_cld3_qca6390",
]

NEW = r'''static const char * const mars_mod_allow[] = {
	"msm_drm",
	"hwid",
	"xiaomi_touch",
	"fts_touch_spi_k2",
	"qti_battery_charger_main",
	NULL
};

/* ★ wlan-gate(2026-10-07): 待验证模块 —— 只有 mars_wlan_allow=1 时才放行。
 *   默认 0 ⇒ 开机时 WLAN 链一律被拒(与 run208 同等的安全状态);
 *   想测就 root 写 /sys/module/kernel/parameters/mars_wlan_allow = 1,
 *   再手动 insmod 逐个验证;崩了重启即自动复位,永不 bootloop。 */
static bool mars_wlan_allow;
core_param(mars_wlan_allow, mars_wlan_allow, bool, 0644);

static const char * const mars_mod_allow_gated[] = {
	GATED_ITEMS
	NULL
};

static bool mars_module_blocked(const char *name)
{
	int i;

	if (!name || !name[0])
		return false;
	for (i = 0; mars_mod_allow[i]; i++)
		if (!strcmp(name, mars_mod_allow[i]))
			return false;
	if (mars_wlan_allow) {
		for (i = 0; mars_mod_allow_gated[i]; i++)
			if (!strcmp(name, mars_mod_allow_gated[i]))
				return false;
	}
	return true;
}
'''


def main():
    if not os.path.isfile(P):
        print('SKIP: 没有 %s' % P)
        return 0
    s = open(P, errors='ignore').read()
    if 'wlan-gate(2026-10-07)' in s:
        print('已打过 wlan-gate 补丁,跳过')
        return 0

    # 匹配 mod-blacklist.py 生成的那一整段(数组 + mars_module_blocked 函数)
    m = re.search(
        r'static const char \* const mars_mod_allow\[\] = \{.*?\n\}\n',
        s, re.S)
    if not m:
        print('!! 没找到 mars_mod_allow[] 段 ⇒ 先跑 mod-blacklist.py')
        return 1

    body = NEW.replace('GATED_ITEMS',
                       '\n'.join('\t"%s",' % g for g in GATED))
    s = s[:m.start()] + body + s[m.end():]
    open(P, 'w').write(s)

    # 自证
    chk = open(P, errors='ignore').read()
    assert 'core_param(mars_wlan_allow, mars_wlan_allow, bool, 0644)' in chk, 'core_param 缺失'
    assert 'mars_mod_allow_gated' in chk, 'gated 名单缺失'
    for g in GATED:
        assert '"%s"' % g in chk, '缺 %s' % g
    print('✅ wlan-gate 已注入: %d 个模块受 /sys/module/kernel/parameters/mars_wlan_allow 控制'
          % len(GATED))
    return 0


if __name__ == '__main__':
    sys.exit(main())
