#!/usr/bin/env python3
"""kernel/module.c 模块白名单 —— 与 MIUI 基线 (boot-p1-allowlist.img) 相同集合。
唯一增量：get_hw_* 保持导出（不再去导出），供 fts_touch 取符号。
"""
import os, re, sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-module-blacklist" in s:
    print("mod-blacklist: skip (already applied)")
    sys.exit(0)

helper = r'''
/* mars-module-blacklist */
static const char * const mars_mod_allow[] = {
	"msm_drm",
	"hwid",
	"xiaomi_touch",
	"fts_touch_spi_k2",
	"cyttsp5",
	"cyttsp5_loader",
	"cyttsp5_device_access",
	"cyttsp5_i2c",
	"mi_thermal_interface",
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
	/* mars-module-blacklist */
	if (mars_module_blocked(info->name)) {
		pr_info("mars-blacklist: skip %s\\n", info->name);
		return -EPERM;
	}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
assert "mars_mod_allow[i]" in s
assert "return true;" in s
print("mod-blacklist: allowlist applied (msm_drm+touch chain, same as MIUI baseline)")
