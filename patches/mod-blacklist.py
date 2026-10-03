#!/usr/bin/env python3
"""在 kernel/module.c 注入模块名黑名单。
5.4 的 load_module(struct load_info *info, ...) 里 info->name 在
copy_module_from_user 之后才可靠。我们改 hook 在 layout_and_allocate 之后
或者直接在 load_module 里找 name 字符串。
最稳：在 parse 之后检查 info->index.vers 或用 info->hdr.
实测 info 结构有 name 字段（char name[MODULE_NAME_LEN]）。
"""
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

# inject helper before load_module
pat = re.compile(r"\n((static\s+)?(long|int|unsigned long)\s+load_module\s*\()", s)
m = pat.search(s)
if not m:
    print("mod-blacklist: load_module not found"); sys.exit(1)

# find the opening brace of load_module
rest = s[m.start():]
brace = rest.find("{")
if brace < 0:
    print("mod-blacklist: no body"); sys.exit(1)

injection = helper + "\n" + rest[:brace+1] + """
	/* mars-module-blacklist */
	if (mars_module_blocked(info->name)) {
		pr_err("mars-blacklist: refuse %s\\n", info->name);
		return -EPERM;
	}
"""
s = s[:m.start()] + injection + s[m.start()+brace+1:]
open(path,"w").write(s)
print("mod-blacklist: patched; info->name check inserted")
