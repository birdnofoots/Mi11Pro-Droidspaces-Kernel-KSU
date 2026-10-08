#!/usr/bin/env python3
"""wlan-block.py <kernel_root> —— 只挡 WLAN 链, 其余模块照原厂放行(带运行时开关)

为什么需要它(2026-10-09):
  LOS 5.4.242 树 + 原厂 config 时, 绝大多数驱动都是 DLKM(=m), 若用旧 recipe 的
  【5 项白名单】会把 ~105 个原厂模块全挡掉 ⇒ 很可能起不来(旧的 5 项白名单能进 MIUI 是因为
  那棵老树把驱动都内建了)。本补丁改成【只黑名单 WLAN 链】:
    · 其余模块走正常流程(vermagic 已对齐原厂 + MODVERSIONS=n) ⇒ 与原厂一致的启动路径;
    · WLAN 链默认拒绝(返回 -EEXIST 让 kmod modprobe 视为"已加载"继续走); 
    · 运行时开关 /sys/module/kernel/parameters/mars_wlan_allow 置 1 即放行(用于单独测 WLAN)。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
allow = [a.strip() for a in sys.argv[2:] if a.strip()]   # 可选定向例外名单
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-wlan-block" in s:
    print("wlan-block: skip (already applied)")
    sys.exit(0)

allow_tbl = ""
if allow:
    allow_tbl = ("\n/* 定向门禁: 只放行这些 WLAN 模块(其余 WLAN 链照挡) */\n"
                 "static const char * const mars_wlan_allow_names[] = {\n"
                 + "".join('\t"%s",\n' % a for a in allow)
                 + "\tNULL\n};\n"
                 "\nstatic bool mars_wlan_in_allow_names(const char *name)\n"
                 "{\n\tint i;\n\n"
                 "\tfor (i = 0; mars_wlan_allow_names[i]; i++)\n"
                 "\t\tif (!strcmp(name, mars_wlan_allow_names[i]))\n"
                 "\t\t\treturn true;\n"
                 "\treturn false;\n}\n")

helper = r'''
/* mars-wlan-block
 * 只挡 WLAN 链(cnss2/qca_cld3_*)+ 其 QMI 前置服务; 其余模块一律照常加载。
 * mars_wlan_allow=1(cmdline 或 /sys/module/kernel/parameters/mars_wlan_allow) 即放行。
 */
static bool mars_wlan_allow;
core_param(mars_wlan_allow, mars_wlan_allow, bool, 0644);

static const char * const mars_wlan_block[] = {
	"cnss2",
	"qca_cld3_wlan",
	"qca_cld3_qca6390",
	"qca_cld3_qca6750",
	"wlan_firmware_service_v01",
	"device_management_service_v01",
	"mi_cnss_statistic",
	"icnss2",
	NULL
};
''' + allow_tbl + r'''
static bool mars_wlan_is_blocked(const char *name)
{
	int i;

	if (mars_wlan_allow || !name || !name[0])
		return false;
''' + ("\tif (mars_wlan_in_allow_names(name))\n\t\treturn false;\n" if allow else "") + r'''	for (i = 0; mars_wlan_block[i]; i++)
		if (!strcmp(name, mars_wlan_block[i]))
			return true;
	return false;
}
'''

m = re.search(r"\n(static\s+)?int\s+check_modinfo\s*\(", s)
if not m:
    print("wlan-block: check_modinfo not found")
    sys.exit(1)
s = s[:m.start()] + "\n" + helper + s[m.start():]

m2 = re.search(r"check_modinfo\s*\([^;{]*\)\s*\{", s, re.S)
if not m2:
    print("wlan-block: check_modinfo body not found")
    sys.exit(1)
inject = """
	{
		const char *__mn = (info && info->name) ? info->name : (mod ? mod->name : "?");
		if (mars_wlan_is_blocked(__mn)) {
			pr_info("mars-wlan-block: refuse %s\\n", __mn);
			/* -EEXIST: kmod modprobe 视为"已加载"继续走依赖链 */
			return -EEXIST;
		}
	}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
chk = open(path, errors="ignore").read()
assert "mars_wlan_is_blocked" in chk
assert "core_param(mars_wlan_allow" in chk
assert helper.count("/*") == helper.count("*/"), "注释不配平!"
print("wlan-block: 已注入(黑名单 %d 项 + mars_wlan_allow 运行时开关%s)"
      % (len(re.findall(r'^\t"', helper, re.M)),
         (", 定向放行: " + " ".join(allow)) if allow else ""))
