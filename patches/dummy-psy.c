/* dummy-psy: 占位 power_supply（带 parent + 自愈重注册）。
 * init.mi_thermald.rc 有两处 wait usb/type；真实 qti_battery 会把我们顶掉再失败
 * ⇒ 文件会消失。用定时器在丢失时重新注册。
 */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/init.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>

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
	POWER_SUPPLY_PROP_ONLINE,
	POWER_SUPPLY_PROP_PRESENT,
	POWER_SUPPLY_PROP_TYPE,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_CURRENT_NOW,
	POWER_SUPPLY_PROP_CAPACITY,
	POWER_SUPPLY_PROP_STATUS,
};

static const struct power_supply_desc dummy_usb_desc = {
	.name = "usb", .type = POWER_SUPPLY_TYPE_USB,
	.properties = dummy_props,
	.num_properties = ARRAY_SIZE(dummy_props),
	.get_property = dummy_get_property,
};
static const struct power_supply_desc dummy_batt_desc = {
	.name = "battery", .type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = dummy_props,
	.num_properties = ARRAY_SIZE(dummy_props),
	.get_property = dummy_get_property,
};

static struct platform_device *dummy_pdev;
static struct power_supply *usb_psy, *batt_psy;
static struct delayed_work dummy_work;

static void dummy_register_all(void)
{
	if (!dummy_pdev)
		return;
	if (!usb_psy) {
		usb_psy = power_supply_register(&dummy_pdev->dev, &dummy_usb_desc, NULL);
		if (IS_ERR(usb_psy)) {
			pr_warn("dummy-psy: usb reg %ld\n", PTR_ERR(usb_psy));
			usb_psy = NULL;
		} else {
			pr_info("dummy-psy: usb registered %p\n", usb_psy);
		}
	}
	if (!batt_psy) {
		batt_psy = power_supply_register(&dummy_pdev->dev, &dummy_batt_desc, NULL);
		if (IS_ERR(batt_psy)) {
			pr_warn("dummy-psy: batt reg %ld\n", PTR_ERR(batt_psy));
			batt_psy = NULL;
		} else {
			pr_info("dummy-psy: batt registered %p\n", batt_psy);
		}
	}
}

static void dummy_work_fn(struct work_struct *work)
{
	/* 如果被真实驱动顶掉，重新占位 */
	if (!usb_psy || !batt_psy)
		dummy_register_all();
	schedule_delayed_work(&dummy_work, msecs_to_jiffies(2000));
}

static int __init dummy_psy_init(void)
{
	dummy_pdev = platform_device_register_simple("dummy_psy", -1, NULL, 0);
	if (IS_ERR(dummy_pdev)) {
		pr_err("dummy-psy: pdev fail %ld\n", PTR_ERR(dummy_pdev));
		return PTR_ERR(dummy_pdev);
	}
	dummy_register_all();
	INIT_DELAYED_WORK(&dummy_work, dummy_work_fn);
	schedule_delayed_work(&dummy_work, msecs_to_jiffies(2000));
	pr_info("dummy-psy: init done\n");
	return 0;
}
late_initcall(dummy_psy_init);
