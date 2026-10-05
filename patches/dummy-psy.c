/* dummy-psy + touch power: 早期注册 power_supply + 使能触摸供电 */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/init.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/regulator/consumer.h>
#include <linux/of.h>
#include <linux/kmod.h>

static int dummy_get_property(struct power_supply *psy,
			      enum power_supply_property psp,
			      union power_supply_propval *val)
{
	switch (psp) {
	case POWER_SUPPLY_PROP_ONLINE:
	case POWER_SUPPLY_PROP_PRESENT:
		val->intval = 1; break;
	case POWER_SUPPLY_PROP_TYPE:
		val->intval = psy->desc->type; break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		val->intval = 5000000; break;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		val->intval = 500000; break;
	case POWER_SUPPLY_PROP_CAPACITY:
		val->intval = 80; break;
	case POWER_SUPPLY_PROP_STATUS:
		val->intval = POWER_SUPPLY_STATUS_CHARGING; break;
	default:
		val->intval = 0; break;
	}
	return 0;
}

static enum power_supply_property dummy_props[] = {
	POWER_SUPPLY_PROP_ONLINE, POWER_SUPPLY_PROP_PRESENT,
	POWER_SUPPLY_PROP_TYPE, POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_CURRENT_NOW, POWER_SUPPLY_PROP_CAPACITY,
	POWER_SUPPLY_PROP_STATUS,
};

static const struct power_supply_desc dummy_usb_desc = {
	.name = "usb", .type = POWER_SUPPLY_TYPE_USB,
	.properties = dummy_props, .num_properties = ARRAY_SIZE(dummy_props),
	.get_property = dummy_get_property,
};
static const struct power_supply_desc dummy_batt_desc = {
	.name = "battery", .type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = dummy_props, .num_properties = ARRAY_SIZE(dummy_props),
	.get_property = dummy_get_property,
};

static struct platform_device *dummy_pdev;
static struct power_supply *usb_psy, *batt_psy;
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
	/* 每 3s 一次 work,第 5 次 ≈ 12s 后再执行(linker64 就绪)。
	 * 不能用 jiffies 比较 —— INITIAL_JIFFIES 回绕导致判断永远为假。 */
	if (touch_force_load_done || dummy_work_count < 2)
		return;
	touch_force_load_done = true;
	ret = call_usermodehelper(argv[0], argv, envp, UMH_WAIT_PROC);
	pr_info("dummy-psy: fts-insmod helper ret=%d\n", ret);
}

static void dummy_register_all(void)
{
	if (!dummy_pdev) return;
	if (!usb_psy) {
		usb_psy = power_supply_register(&dummy_pdev->dev, &dummy_usb_desc, NULL);
		if (IS_ERR(usb_psy)) { pr_warn("dummy-psy: usb %ld\n", PTR_ERR(usb_psy)); usb_psy = NULL; }
		else pr_info("dummy-psy: usb ok\n");
	}
	if (!batt_psy) {
		batt_psy = power_supply_register(&dummy_pdev->dev, &dummy_batt_desc, NULL);
		if (IS_ERR(batt_psy)) { pr_warn("dummy-psy: batt %ld\n", PTR_ERR(batt_psy)); batt_psy = NULL; }
		else pr_info("dummy-psy: batt ok\n");
	}
}

static void dummy_work_fn(struct work_struct *work)
{
	int ret;
	if (!usb_psy || !batt_psy)
		dummy_register_all();
	/* keep touch regulator enabled */
	if (touch_vreg) {
		ret = regulator_is_enabled(touch_vreg);
		if (ret == 0) {
			ret = regulator_enable(touch_vreg);
			pr_info("dummy-psy: touch_vreg enable ret=%d\n", ret);
		}
	}
	/* 12s 后再 insmod:3s 时 /system/bin/linker64 尚不可用,call_usermodehelper 全部 exit 255 */
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
	dummy_register_all();

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
	pr_info("dummy-psy: init done\n");
	return 0;
}
late_initcall(dummy_psy_init);
