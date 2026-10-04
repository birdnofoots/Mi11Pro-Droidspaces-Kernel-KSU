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

/* 强制装载触屏链并打日志 —— modprobe 对内建模块会静默跳过,这里显式 request_module */
static void touch_force_load(void)
{
	static const char * const names[] = {
		"hwid", "xiaomi_touch", "fts_touch_spi_k2",
		"cyttsp5", "cyttsp5_loader", "cyttsp5_device_access", "cyttsp5_i2c",
		NULL
	};
	int i, ret;
	if (touch_force_load_done)
		return;
	touch_force_load_done = true;
	for (i = 0; names[i]; i++) {
		ret = request_module(names[i]);
		pr_info("dummy-psy: request_module(%s) ret=%d\n", names[i], ret);
	}
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
