/* dummy-psy + touch power —— 只保留「触摸供电 + fts 强制 insmod」，
 * ★ 2026-10-06:【删除假 power_supply 注册】。
 *
 * 为什么删(run162 真机 logdump,8.624s,证据链完整):
 *   sysfs: cannot create duplicate filename '/class/power_supply/battery'
 *   CPU: 0 PID: 5 Comm: kworker/0:0  Workqueue: events pmic_glink_init_work
 *   Call trace:
 *     sysfs_warn_dup → device_add → __power_supply_register
 *     → devm_power_supply_register
 *     → battery_chg_probe+0x414/0x880 [qti_battery_charger_main]
 *     → pmic_glink_init_work
 *   BATTERY_CHG: battery_chg_init_psy: Failed to register battery power supply, rc=-17
 *   qti_battery_charger: probe of soc:qcom,pmic_glink:qcom,battery_charger failed with error -17
 *
 *   本文件旧版在 1.0978s(late_initcall)抢先注册了 .name="usb" 与 .name="battery" 两个假 psy;
 *   而原厂真充电器驱动(qti_battery_charger_main)要等到 8.57s 由 init modprobe 进来,
 *   它注册的第一个 psy 就是 "battery" ⇒ 撞名 -EEXIST ⇒ probe 失败。
 *
 * 原厂活体对照(adb shell,金镜像在跑):
 *   /sys/class/power_supply/ 只有 3 个 battery / usb / wireless,且三者同属
 *   .../soc:qcom,pmic_glink:qcom,battery_charger/power_supply/(battery|usb|wireless)
 *   ⇒ 这三个名字全归真驱动所有,我们一个都不能抢。
 *
 * 后果(为什么必须修):真驱动 probe 失败 ⇒ 整机【没有电池管理/充电/热管理/USB-PD】,
 *   pmic_glink 的 charger 客户端缺席(日志: PMIC_GLINK: No client present for 32778),
 *   负载下会静默硬复位(实测寿命在 12.4s / 18.8s 间漂移,且无任何 panic —— 与
 *   "内核静默掉电型复位"完全吻合)。
 *
 * 为什么可以删掉早期假 psy:原厂的 /sys/class/power_supply/usb 同样是 8.02s 才出现,
 *   而原厂系统照常开机 ⇒ 所谓「init 等 /sys/class/power_supply/usb/type 5s 超时」
 *   只是【症状】,不是拦路虎;真正的原因就是我们自己把真驱动挤掉了(自伤闭环)。
 *
 * 保留部分(与 psy 无关,是真需求):
 *   ① 触摸供电 regulator(touch_avddsource_vreg)常开,每 3s 复查一次;
 *   ② 6s 后用 call_usermodehelper 强制 insmod fts_touch_spi_k2.ko(把 stderr 写进 dmesg,
 *      方便 logdump 抓原因)。
 */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/init.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/regulator/consumer.h>
#include <linux/of.h>
#include <linux/kmod.h>

static struct platform_device *dummy_pdev;
static struct delayed_work dummy_work;
static struct regulator *touch_vreg;
static bool touch_force_load_done;
static int dummy_work_count;

static void touch_force_load(void)
{
	/* ★★ F29(2026-10-06):改用【/vendor/bin/modprobe】自己装,不再靠 MIUI 的 vendor_modprobe.sh。
	 * 证据(F26/F28 真机 logdump):
	 *   · vendor_modprobe.sh 遍历了模块列表,但 fts_touch_spi_k2 / qti_battery_charger_main
	 *     【连一次装载尝试都没有】(mars-allow 里只见到 msm_drm/hwid/xiaomi_touch/fc0013);
	 *   · 我们旧的 helper 用 /system/bin/sh + /system/bin/insmod ⇒ 恒返回 65280(255),
	 *     且它写进 /dev/kmsg 的诊断行一条都没出现 ⇒ 那条路根本走不通;
	 *   · MIUI 自己在 early-init 就是用 /vendor/bin/modprobe 装模块的 ⇒ 它一定可用。
	 * 依赖顺序由 modprobe 的 -a 自己解析(modules.dep: fts→xiaomi_touch,hwid,msm_drm)。 */
	static char *envp[] = { "HOME=/", "PATH=/vendor/bin:/system/bin:/sbin", NULL };
	char *argv[] = {
		"/vendor/bin/modprobe", "-a", "-d", "/vendor/lib/modules/",
		"xiaomi_touch", "fts_touch_spi_k2", "qti_battery_charger_main",
		NULL
	};
	int ret;

	/* 只在第 2/4/8/16/32 次 work(≈6/12/24/48/96s)尝试 —— 覆盖 /vendor 挂载后到框架起来的所有时机;
	 * 成功了也没法从返回值判断(UMH_WAIT_PROC 返回的是内核侧状态,不是进程退出码),
	 * 所以按固定计划试 5 次就停(modprobe 对已装模块是幂等的,重复无害)。 */
	if (touch_force_load_done)
		return;
	if (!(dummy_work_count == 2 || dummy_work_count == 4 || dummy_work_count == 8 ||
	      dummy_work_count == 16 || dummy_work_count == 32))
		return;

	ret = call_usermodehelper(argv[0], argv, envp, UMH_WAIT_PROC);
	pr_info("dummy-psy: modprobe(touch+charger) ret=%d (work_count=%d)\n", ret, dummy_work_count);
	if (dummy_work_count >= 32)
		touch_force_load_done = true;
}

static void dummy_work_fn(struct work_struct *work)
{
	int ret;

	/* keep touch regulator enabled */
	if (touch_vreg) {
		ret = regulator_is_enabled(touch_vreg);
		if (ret == 0) {
			ret = regulator_enable(touch_vreg);
			pr_info("dummy-psy: touch_vreg enable ret=%d\n", ret);
		}
	}
	dummy_work_count++;
	touch_force_load();
	schedule_delayed_work(&dummy_work, msecs_to_jiffies(3000));
}

static int __init dummy_psy_init(void)
{
	struct device_node *np;

	dummy_pdev = platform_device_register_simple("dummy_psy", -1, NULL, 0);
	if (IS_ERR(dummy_pdev)) {
		pr_err("dummy-psy: pdev %ld\n", PTR_ERR(dummy_pdev));
		return PTR_ERR(dummy_pdev);
	}

	/* get touch_avddsource_vreg from DT */
	np = of_find_node_by_name(NULL, "touch_avddsource_vreg");
	if (np) {
		touch_vreg = regulator_get(&dummy_pdev->dev, "touch_avddsource_vreg");
		if (IS_ERR(touch_vreg))
			touch_vreg = regulator_get(&dummy_pdev->dev, NULL);
		if (IS_ERR(touch_vreg)) {
			pr_warn("dummy-psy: touch_vreg get failed %ld\n", PTR_ERR(touch_vreg));
			touch_vreg = NULL;
		} else {
			int ret = regulator_enable(touch_vreg);
			pr_info("dummy-psy: touch_vreg enable ret=%d\n", ret);
		}
		of_node_put(np);
	} else {
		pr_warn("dummy-psy: touch_avddsource_vreg not in DT\n");
	}

	INIT_DELAYED_WORK(&dummy_work, dummy_work_fn);
	schedule_delayed_work(&dummy_work, msecs_to_jiffies(2000));
	pr_info("dummy-psy: init done (不注册任何假 power_supply,battery/usb/wireless 交还原厂 qti_battery_charger)\n");
	return 0;
}
late_initcall(dummy_psy_init);


/* ============================================================================
 * ★ 2026-10-07 20:0x 内建 ADSP 引导触发器(adsp-boot)
 *
 * 背景(活体取证):
 *   原厂 ADSP 由 vendor 模块 adsp_loader_dlkm 触发 —— 它绑 DT 节点
 *   /soc/qcom,msm-adsp-loader, 并提供 /sys/kernel/boot_adsp 给 init.rc 写
 *   (init.qcom.rc:87 `write /sys/kernel/boot_adsp/boot 1`)。
 *   但我们内核编译出的镜像上一旦真加载该模块(及其依赖 apr_dlkm), 内核会崩
 *   (实测: allowlist 7 项/10 项能开机, 11 项加了 mmhardware 让 adsp_loader+apr
 *    真正装上后 ⇒ 循环重启)。
 *
 * 本触发器的做法(完全绕开 vendor 模块):
 *   树内的 subsys-pil-tz 驱动已经接管了 lpass 节点(原厂日志里就是它:
 *   "subsys-pil-tz 17300000.qcom,lpass: adsp: loading"), /sys/class/subsys/subsys_adsp
 *   也已存在。所以我们只要在合适时机调 subsystem_get("adsp"), 它就会去加载
 *   adsp 固件 ⇒ ADSP 起来 ⇒ pmic_glink 拿到充电器 client ⇒ qti_battery_charger_main
 *   probe ⇒ power_supply(usb/battery/wireless) 出现 ⇒ "Avail curr from USB"
 *   ⇒ dwc3 退出低功耗 ⇒ UDC 注册 ⇒ USB/adb 通。
 *
 * 时机: 12 秒后(等 ueventd/init 就绪, 否则 firmware_class 的 sysfs fallback
 *       没有任何人应答, adsp.mdt 会加载失败); 失败则每 5 秒重试, 最多 24 次。
 * ==========================================================================*/
#include <soc/qcom/subsystem_restart.h>

static struct delayed_work adsp_boot_work;
static int adsp_tries;

static void adsp_boot_fn(struct work_struct *w)
{
	struct subsys_device *d;

	if (adsp_tries++ > 24) {
		pr_err("adsp-boot: 重试 %d 次后放弃\n", adsp_tries);
		return;
	}
	d = subsystem_get("adsp");
	if (IS_ERR(d)) {
		pr_err("adsp-boot: subsystem_get(adsp) 失败 rc=%ld (第 %d 次)\n",
		       PTR_ERR(d), adsp_tries);
		schedule_delayed_work(&adsp_boot_work, msecs_to_jiffies(5000));
		return;
	}
	pr_info("adsp-boot: 已触发 ADSP 引导(handle=%pK), 等 adsp: loading\n", d);
}

static int __init adsp_boot_init(void)
{
	pr_info("adsp-boot: 注册成功(12s 后触发 subsystem_get(\"adsp\"))\n");
	INIT_DELAYED_WORK(&adsp_boot_work, adsp_boot_fn);
	schedule_delayed_work(&adsp_boot_work, msecs_to_jiffies(12000));
	return 0;
}
late_initcall(adsp_boot_init);
