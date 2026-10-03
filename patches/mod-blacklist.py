#!/usr/bin/env python3
"""在 kernel/module.c 注入模块名黑名单（mars-module-blacklist）。"""
import os, re, sys
root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-module-blacklist" in s:
    print("mod-blacklist: skip"); sys.exit(0)

helper = r'''
/* mars-module-blacklist */
static const char * const mars_mod_blacklist[] = {
	"qti_battery_charger_main", "fts_touch_spi_k2",
	"aw8697_haptic", "aw8697_haptics",
	"qca_cld3_wlan", "qca_cld3_qca6390", "qca_cld3_qca6750",
	"cnss2", "icnss2", "mi_cnss_statistic", "wlan_firmware_service_v01",
	NULL
};
static bool mars_module_blocked(const char *name)
{
	int i;
	if (!name) return false;
	for (i = 0; mars_mod_blacklist[i]; i++)
		if (!strcmp(name, mars_mod_blacklist[i])) return true;
	return false;
}
'''

# find load_module
pat = re.compile(r"\n(static\s+)?(long|int|unsigned long)\s+load_module\s*\((.*?)\)\s*\{", re.S)
m = pat.search(s)
if not m:
    print("mod-blacklist: load_module not found"); sys.exit(1)
insert = helper + "\n" + m.group(0) + """
	/* mars-module-blacklist: refuse known-hanging vendor modules */
	if (info && mars_module_blocked(info->name)) {
		pr_err("mars-blacklist: refuse %s\\n", info->name);
		return -EPERM;
	}
"""
s = s[:m.start()] + insert + s[m.end():]
open(path,"w").write(s)
print("mod-blacklist: ok", path)
