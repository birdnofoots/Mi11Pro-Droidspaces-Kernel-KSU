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
 * ★ 2026-10-06 F24:【L1 内建线 + 只拦 WLAN/CNSS 栈】。
 *   与 F18/#164 的差别只在【变体】:那个跑 star-stock-raw(不翻内建),
 *   这个跑 star-stock(62 项 =m→=y 内建)。
 *   为什么拦这几个名字 = 直接解 L1 线有 logdump 出处的死因:
 *     star-stock 翻内建后 /vendor 同名 .ko 仍被 modprobe ⇒ "already registered" ×N
 *     ⇒ 最后 WLAN 栈卡死(uptime 129.3s):
 *        init: Sending signal 9 to service 'exec 24 (/vendor/bin/modprobe -a -d
 *              /vendor/lib/modules/ qca_cld3_wlan qca_cld3_qca6390)'
 *     ⇒ init 超时 SIGKILL 后系统停住 ⇒ bootloader 判失败。
 *   拒绝这些名字 ⇒ modprobe 立刻拿到错误返回 ⇒ 不卡 ⇒ 不 SIGKILL。
 *   (原 F18 注释保留如下)
 *   依据(run163 真机 logdump,见 CHECKLIST §22.12):
 *     两次自编启动都死在 CNSS/WLAN PCIe 上电重试里 ——
 *       cnss: Failed to register MSM PCI event, err = -19   (原厂: 无)
 *       cnss_pci: of_irq_parse_pci: failed with rc=134       (原厂: 无)
 *       cnss: Retry cnss_bus_init #1/#2                      (原厂: 无)
 *     而原厂从不进入这条路径。
 *   名字用【内核模块名】(来自 .ko 里内嵌 struct module 的 name 字段),
 *   不是文件名 —— 设备 lsmod 实测:
 *       qca_cld3_wlan.ko -> "wlan"     cnss2.ko -> "cnss2"    icnss2.ko -> "icnss2"
 *   ★ 绝不拦 "hwid":camera/fts_touch_spi_k2/qti_battery_charger_main/
 *     icnss2/cnss2 都依赖它,且 LineageOS 把 hwid.ko 列为 mars 的 boot 关键模块。
 * 详细取证见 patches/mod-blacklist.py 顶部注释。
 */
static const char * const mars_mod_blacklist[] = {
	"cnss2",
	"icnss2",
	"wlan",
	"mi_cnss_statistic",
	"wlan_firmware_service_v01",
	/* ★ F24:init.target.rc 历史上是按【文件名】调 modprobe 的:
	 *     exec 24 (/vendor/bin/modprobe -a -d /vendor/lib/modules/ qca_cld3_wlan qca_cld3_qca6390)
	 *   而 check_modinfo() 比的是 mod->name。两种形态都列上,保证必被拒。 */
	"qca_cld3_wlan",
	"qca_cld3_qca6390",
	"cnss_nl",
	"cnss_prealloc",
	"cnss_utils",
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
	/* mars-module-blacklist:黑名单外的全部放行 + 跳过 vermagic 比对 */
	{
		const char *__mn = (info && info->name) ? info->name : (mod ? mod->name : "?");
		if (mars_module_blocked(__mn)) {
			pr_info("mars-blocklist: skip %s\\n", __mn);
			return -EPERM;
		}
		return 0;
	}
"""
s = s[:m2.end()] + inject + s[m2.end():]
open(path, "w").write(s)
assert "mars_mod_blacklist[i]" in s
print("mod-blacklist: 已注入【WLAN/CNSS 黑名单】(%d 项);其余放行,vermagic 比对跳过" % (len(re.findall(r'^\t"', helper, re.M))))
