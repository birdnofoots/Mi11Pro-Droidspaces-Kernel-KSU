#!/usr/bin/env python3
"""check_modinfo 黑名单"""
import os, re, sys
root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-module-blacklist" in s:
    print("skip"); sys.exit(0)

helper = """
/* mars-module-blacklist */
static const char * const mars_mod_blacklist[] = {
\t"qti_battery_charger_main", "fts_touch_spi_k2",
\t"aw8697_haptic", "aw8697_haptics",
\t"qca_cld3_wlan", "qca_cld3_qca6390", "qca_cld3_qca6750",
\t"cnss2", "icnss2", "mi_cnss_statistic", "wlan_firmware_service_v01",
\tNULL
};
static bool mars_module_blocked(const char *name)
{
\tint i;
\tif (!name) return false;
\tfor (i = 0; mars_mod_blacklist[i]; i++)
\t\tif (!strcmp(name, mars_mod_blacklist[i])) return true;
\treturn false;
}
"""

m = re.search(r"\nstatic int check_modinfo\(", s)
if not m:
    m = re.search(r"\nint check_modinfo\(", s)
if not m:
    print("check_modinfo not found"); sys.exit(1)
s = s[:m.start()] + "\n" + helper + s[m.start():]

m2 = re.search(r"check_modinfo\s*\([^)]*\)\s*\{", s)
if not m2:
    print("body not found"); sys.exit(1)
inject = """
\t/* mars-module-blacklist */
\tif (mars_module_blocked(info->name)) {
\t\tpr_err("mars-blacklist: refuse %s\\n", info->name);
\t\treturn -EPERM;
\t}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
print("mod-blacklist ok")
