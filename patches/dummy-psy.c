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
	static char *envp[] = { "HOME=/", "PATH=/system/bin:/vendor/bin:/sbin", NULL };
	/* 用 toybox sh 把 stderr 写进 dmesg,方便 logdump 抓原因 */
	char *argv[] = { "/system/bin/sh", "-c",
		"/system/bin/insmod /vendor/lib/modules/fts_touch_spi_k2.ko 2>&1 | while read l; do echo \"fts-insmod: $l\" >/dev/kmsg; done; "
		"echo \"fts-insmod: done $(cat /sys/module/fts_touch_spi_k2/initstate 2>/dev/null)\" >/dev/kmsg",
		NULL };
	int ret;
	/* 每次 work 间隔 3s,第 2 次 ≈ 5~6s 后执行(linker64 就绪)。
	 * 不能用 jiffies 比较 —— INITIAL_JIFFIES 回绕导致判断永远为假。 */
	if (touch_force_load_done || dummy_work_count < 2)
		return;
	touch_force_load_done = true;
	ret = call_usermodehelper(argv[0], argv, envp, UMH_WAIT_PROC);
	pr_info("dummy-psy: fts-insmod helper ret=%d\n", ret);
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
