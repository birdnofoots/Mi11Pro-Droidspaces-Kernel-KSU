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
	/* USB gadget stack for adb without touch */
	"dwc3", "dwc3_qcom", "dwc3_of_simple",
	"phy_msm_ssusb_qmp", "extcon_usb_gpio",
	"usb_common", "libcomposite", "configfs",
	"xhci_hcd", "xhci_plat_hcd", "dwc3-msm",
	/* WLAN: 放行,让无线 adb 有通路(固件超时已 1s,不会挂死) */
	"cnss2", "icnss2", "qca_cld3_wlan", "qca_cld3_qca6390",
	"qca_cld3_qca6750", "mi_cnss_statistic",
	"device_management_service_v01", "wlan_firmware_service_v01",
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
	{
		const char *__mn = (info && info->name) ? info->name : (mod ? mod->name : "?");
		if (mars_module_blocked(__mn)) {
			pr_info("mars-blacklist: skip %s\\n", __mn);
			return -EPERM;
		}
		pr_info("mars-allow: %s\\n", __mn);
	}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
assert "mars_mod_allow[i]" in s
assert "return true;" in s
print("mod-blacklist: allowlist applied (msm_drm+touch chain, same as MIUI baseline)")
