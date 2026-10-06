#!/usr/bin/env python3
"""kernel/module.c 模块装载策略 —— 2026-10-06 改为【全部放行】。

★★ 为什么改(真机取证,run161 的 4s/11s 早期快照):
   原设计是往 check_modinfo() 里注入一份【白名单】(mars_mod_allow[],约 30 个名字),
   不在名单里的模块直接 return -EPERM。后果(实测):
     · vendor 的 111 个模块里绝大多数被拒 ⇒ 到 101 秒日志里
       **一条 "Modules linked in:" 都没有**(原厂同一时刻是 111 个模块);
     · qti_battery_charger_main(负责 VBUS/充电检测)**不在名单里** ⇒
       没有 VBUS ⇒ 内核认为 "USB cable not connected" + 假充电 + gadget 起不来;
     · 名单里却**包含原厂内建**的 dwc3/dwc3_qcom/dwc3_of_simple/phy_msm_ssusb_qmp/
       extcon_usb_gpio ⇒ 硬要装 ⇒ 内核日志报
         "Driver 'extcon-usb-gpio' is already registered, aborting..."
         "dwc3: exports duplicate symbol dwc3_dbg_print (owned by kernel)"
       ⇒ /vendor 那一串全被拒 ⇒ USB 链彻底废掉(无 adb)。
   ⇒ 对照原厂 dmesg:这些报错**一条都没有**,而且原厂有
     "configfs-gadget gadget: high-speed config #1: b"(10.33s 起来)、
     "qti_battery_charger ... battery_chg_probe done"(8.07s)。
   ⇒ 正确做法:**跟原厂一样,不拦任何模块**,由设备自己的
     /vendor/lib/modules/modules.load 决定装哪些(114 条)。

★ 保留的部分(必须保留,不能删):
   注入的代码仍然 return 0,也就是**跳过 vermagic/retpoline 等剩余检查**。
   原因(2026-10-05 实锤):原厂 .ko 的 vermagic 不统一
     hwid: version magic '5.4.233-gbb70cde46897 ...' should be '5.4.233-qgki-gbb70cde46897 ...'
   同一字面比对永远拦死一批;而 CONFIG_MODVERSIONS 已关,符号 CRC 也不查。

★ 只保留一个**内容为空的**黑名单钩子:将来若某个 vendor 模块确实会挂死
   (历史上出现过 module_mutex 被永久占住的情况),往下面 mars_mod_blacklist
   里加名字即可,不必再改结构。
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
 * ★ 2026-10-06 F19/run165:黑名单【清空】(不拦任何模块),并【取消无条件放行】。
 *   权威依据:Droidspaces 官方内核配置指南(GKI 章节)原话:
 *     "Do not turn off CONFIG_MODVERSIONS or force-load modules to get past the
 *      check. The structures really did change, and a stock module would read
 *      the wrong offsets."
 *   过去我们靠本文件末尾那句 `return 0` 跳过 vermagic/CRC 校验,把原厂模块硬塞
 *   进来 ⇒ 模块可能按错误偏移读写内核结构 ⇒ 静默损坏(症状:无声硬复位)。
 *   现在:① 黑名单为空;② 不再 return 0 ⇒ 交回内核原本的 check_modinfo
 *   (vermagic 比对)+ MODVERSIONS CRC 校验。装不上的模块会【明确报错】而不是静默损坏。
 *   —— 这是把"盲刷"变成"可诊断"的关键一步,也激活 CI 的 kABI CRC 体检。
 * 详细取证见 patches/mod-blacklist.py 顶部注释与 CHECKLIST §22.12/§22.13。
static const char * const mars_mod_blacklist[] = {
	/* F19/run165:空 —— 不拦任何模块,让 CRC/vermagic 校验说真话 */
	NULL
};
static bool mars_module_blocked(const char *name)
{
	int i;

	if (!name || !name[0])
		return false;
	for (i = 0; mars_mod_blacklist[i]; i++)
		if (!strcmp(name, mars_mod_blacklist[i]))
			return true;
	return false;
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
	/* mars-module-blacklist:只做黑名单拦截;【不再】无条件 return 0 --
	 * 让内核原本的 vermagic 比对与 MODVERSIONS CRC 校验说真话 */
	{
		const char *__mn = (info && info->name) ? info->name : (mod ? mod->name : "?");
		if (mars_module_blocked(__mn)) {
			pr_info("mars-blocklist: skip %s\\n", __mn);
			return -EPERM;
		}
	}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
assert "mars_mod_blacklist[i]" in s
print("mod-blacklist: F19/run165 -- blacklist emptied + unconditional return 0 removed (real vermagic/CRC checks restored)")
