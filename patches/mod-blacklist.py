#!/usr/bin/env python3
"""kernel/module.c 模块黑名单（只拦 WLAN，其余全部放行）。

sde59 实锤：WLAN 链 (qca_cld3_*/cnss2/icnss2) 的 probe 会挂住 vendor_modprobe 的 exec。
其余模块（USB/触屏/电池/平台）必须放行 —— 拦了会导致 USB gadget -19 / 无触屏。
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
static const char * const mars_mod_block[] = {
	"qca_cld3_wlan", "qca_cld3_qca6390", "qca_cld3_qca6750",
	"cnss2", "icnss2", "mi_cnss_statistic", "wlan_firmware_service_v01",
	"cnss_utils", "cnss_nl", "cnss_prealloc",
	NULL
};
static bool mars_module_blocked(const char *name)
{
	int i;
	if (!name || !name[0])
		return false;
	for (i = 0; mars_mod_block[i]; i++)
		if (!strcmp(name, mars_mod_block[i]))
			return true;
	return false;
}
'''

m = re.search(r"\n(static\s+)?int\s+check_modinfo\s*\(", s)
if not m:
    print("mod-blacklist: check_modinfo not found")
    sys.exit(1)
s = s[:m.start()] + "\n" + helper + s[m.start():]

# inject at start of check_modinfo body
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
print("mod-blacklist: injected (block-only-WLAN)")
# sanity: must contain block list and NOT allowlist-return-true
assert "mars_mod_block[i]" in s
assert "return true;\n}" in s.replace("return true;\r\n}", "return true;\n}")
print("ok")
