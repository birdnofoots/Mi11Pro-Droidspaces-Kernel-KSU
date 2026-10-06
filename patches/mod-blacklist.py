#!/usr/bin/env python3
"""kernel/module.c 模块装载策略 —— ★ F26(2026-10-06):恢复【白名单】,但扩成精选集合。

★★★ 为什么回到白名单(这是本轮真凶的定位,证据链完整):
   逐补丁 diff 10-04(能进 MIUI,md5 e640d079…)与现在:
     · 10-04 的 mod-blacklist.py = **白名单,只放行 "msm_drm" 一个模块**,
       其余 ~110 个 vendor 模块全部 return -EPERM ⇒ 系统照样进 MIUI(有显示)。
     · 之后改成【全放行 + 无条件 return 0】⇒ run162/163/164/171/172 **全部硬复位循环**。
   ⇒ 差别就是"把 ~100 个用【另一棵树】编译的原厂 .ko 强塞进我们的内核"。
     它们读错结构偏移 ⇒ 静默硬复位(无 panic)。这正是 Droidspaces 官方指南逐字警告的:
       "Do not turn off CONFIG_MODVERSIONS or force-load modules to get past the check.
        The structures really did change, and a stock module would read the wrong offsets."

★ 关键区分(决定本补丁的形态):
   · **vermagic** = 版本字符串比对(各 .ko 还不统一)⇒ 绕过它不会导致内存损坏;
   · **CRC/modversions** = 真正的 ABI 校验 ⇒ 绕过它才危险。
   但本机实测我们的内核与原厂符号 CRC 只有 **33.7%** 相同(run167/run169),所以
   "诚实校验"= 几乎什么都装不上 = 连显示都没有。⇒ 唯一可行的折中:
   **用一个尽量小的白名单** + 只对白名单里的模块放行(保留 return 0 以跳过 vermagic)。

★ 精选名单的依据:
   "msm_drm"                 —— 10-04 已实测证明"只放行它"能进 MIUI(有显示)✓
   "hwid" "xiaomi_touch" "fts_touch_spi_k2" —— 触摸链(fts 依赖 xiaomi_touch/hwid;
                               缺 hwid 会让触屏拿不到 get_hw_id_value,§3.3)
   "qti_battery_charger_main" —— VBUS/充电/USB-PD(缺它 ⇒ "USB cable not connected"
                               + gadget 起不来 = 无 adb;原厂 8.07s 装它)
   ⛔ 故意【不含】WLAN/CNSS 栈(cnss2/icnss2/wlan/…)—— 最复杂的 PCIe 模块,
      风险最高,留到"先能稳定进桌面"之后再单独加。
"""
import os, re, sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-module-blacklist" in s:
    print("mod-blacklist: skip (already applied)")
    sys.exit(0)

helper = r'''
/* mars-module-blacklist
 * ★ F26:精选白名单(mars_mod_allow)。不在名单里的模块一律 -EPERM。
 *   名单里放行的模块走 return 0(跳过 vermagic/CRC 剩余检查)——
 *   这是权衡的结果:诚实校验在本机等于"什么都装不上"(符号 CRC 只 33.7% 相同)。
 *   代价与风险见 CHECKLIST §22.14.O。
 */
static const char * const mars_mod_allow[] = {
	"msm_drm",
	"hwid",
	"xiaomi_touch",
	"fts_touch_spi_k2",
	"qti_battery_charger_main",
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
	return true;
}
'''

m = re.search(r"\n(static\s+)?int\s+check_modinfo\s*\(", s)
if not m:
    print("mod-blacklist: check_modinfo not found")
    sys.exit(1)
s = s[:m.start()] + "\n" + helper + s[m.start():]

m2 = re.search(r"check_modinfo\s*\([^;{]*\)\s*\{", s, re.S)
if not m2:
    print("mod-blacklist: check_modinfo body not found")
    sys.exit(1)
inject = """
	{
		const char *__mn = (info && info->name) ? info->name : (mod ? mod->name : "?");
		if (mars_module_blocked(__mn)) {
			pr_info("mars-blacklist: skip %s\\n", __mn);
			return -EPERM;
		}
		pr_info("mars-allow: %s\\n", __mn);
		return 0;
	}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
assert "mars_mod_allow[i]" in s
# ★ 铁律:防止上次 run165 那种"注释未闭合"事故
assert helper.count("/*") == helper.count("*/"), "注释不配平!"
print("mod-blacklist: 已注入【精选白名单】(%d 项);其余一律拒绝" % len(re.findall(r'^\t"', helper, re.M)))
