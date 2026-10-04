#!/usr/bin/env python3
"""kernel/module.c 模块白名单（只放行显示链），其余 vendor 模块一律拒绝。
sde59 实锤：多个 modprobe 卡在 do_init_module 的 init() 里（固件/硬件等待）
导致 vendor_modprobe 的 exec 挂 52s。P1 只求进桌面，先不加载任何非必要模块。
"""
import os, re, sys
root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-module-blacklist" in s:
    print("skip"); sys.exit(0)

helper = """
/* mars-module-blacklist */
static const char * const mars_mod_allow[] = {
\t"msm_drm",
\tNULL
};
static bool mars_module_blocked(const char *name)
{
\tint i;
\tif (!name || !name[0]) return false;
\tfor (i = 0; mars_mod_allow[i]; i++)
\t\tif (!strcmp(name, mars_mod_allow[i])) return false;
\treturn true;
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
\t\tpr_info("mars-blacklist: skip %s\\n", info->name);
\t\treturn -EPERM;
\t}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
print("allowlist injected")
