/* dummy-psy: 早期注册占位 power_supply（带 parent device）。
 * 必须有 parent，否则 __power_supply_register 报
 *   "Expected proper parent device" 且 sysfs 不出现 ⇒ init wait 仍超时。
 */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/init.h>

static int dummy_get_property(struct power_supply *psy,
			      enum power_supply_property psp,
			      union power_supply_propval *val)
{
	switch (psp) {
	case POWER_SUPPLY_PROP_ONLINE:
	case POWER_SUPPLY_PROP_PRESENT:
		val->intval = 1;
		break;
	case POWER_SUPPLY_PROP_TYPE:
		val->intval = psy->desc->type;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		val->intval = 5000000;
		break;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		val->intval = 500000;
		break;
	case POWER_SUPPLY_PROP_CAPACITY:
		val->intval = 80;
		break;
	case POWER_SUPPLY_PROP_STATUS:
		val->intval = POWER_SUPPLY_STATUS_CHARGING;
		break;
	default:
		val->intval = 0;
		break;
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
	.name		= "usb",
	.type		= POWER_SUPPLY_TYPE_USB,
	.properties	= dummy_props,
	.num_properties	= ARRAY_SIZE(dummy_props),
	.get_property	= dummy_get_property,
};

static const struct power_supply_desc dummy_batt_desc = {
	.name		= "battery",
	.type		= POWER_SUPPLY_TYPE_BATTERY,
	.properties	= dummy_props,
	.num_properties	= ARRAY_SIZE(dummy_props),
	.get_property	= dummy_get_property,
};

static struct platform_device *dummy_pdev;
static struct power_supply *dummy_usb_psy, *dummy_batt_psy;

static int __init dummy_psy_init(void)
{
	dummy_pdev = platform_device_register_simple("dummy_psy", -1, NULL, 0);
	if (IS_ERR(dummy_pdev)) {
		pr_err("dummy-psy: pdev failed %ld\n", PTR_ERR(dummy_pdev));
		return PTR_ERR(dummy_pdev);
	}
	dummy_usb_psy = power_supply_register(&dummy_pdev->dev, &dummy_usb_desc, NULL);
	if (IS_ERR(dummy_usb_psy)) {
		pr_err("dummy-psy: usb failed %ld\n", PTR_ERR(dummy_usb_psy));
		dummy_usb_psy = NULL;
	}
	dummy_batt_psy = power_supply_register(&dummy_pdev->dev, &dummy_batt_desc, NULL);
	if (IS_ERR(dummy_batt_psy)) {
		pr_err("dummy-psy: batt failed %ld\n", PTR_ERR(dummy_batt_psy));
		dummy_batt_psy = NULL;
	}
	pr_info("dummy-psy: ok usb=%p batt=%p pdev=%p\n",
		dummy_usb_psy, dummy_batt_psy, dummy_pdev);
	return 0;
}
late_initcall(dummy_psy_init);
