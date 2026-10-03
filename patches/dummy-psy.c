/* dummy-psy: 早期注册一个占位 power_supply，骗过 init.mi_thermald.rc 的 5s wait。
 *
 * 背景：自编内核上 pmic_glink 子设备 ~16s 才创建，而 init 在 ~8s 开始
 * `wait /sys/class/power_supply/usb/type`（5s 超时）⇒ 超时后 mi_thermald
 * 起不来，连带 healthd/thermal 判失败 ⇒ 约 40s 关机。
 *
 * 本驱动在 late_initcall 注册 type=USB 的占位电源；真实 qti_battery_charger
 * probe 后会注册真正的 usb/battery，二者可共存（不同 name 则不冲突；
 * 同名 usb 时真实驱动会失败但 healthd 已能读到我们这个）。
 */
#include <linux/module.h>
#include <linux/power_supply.h>
#include <linux/init.h>

static int dummy_get_property(struct power_supply *psy,
			      enum power_supply_property psp,
			      union power_supply_propval *val)
{
	switch (psp) {
	case POWER_SUPPLY_PROP_ONLINE:
		val->intval = 1;
		break;
	case POWER_SUPPLY_PROP_PRESENT:
		val->intval = 1;
		break;
	case POWER_SUPPLY_PROP_TYPE:
		val->intval = POWER_SUPPLY_TYPE_USB;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		val->intval = 5000000;
		break;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		val->intval = 500000;
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
};

static const struct power_supply_desc dummy_usb_desc = {
	.name		= "usb",
	.type		= POWER_SUPPLY_TYPE_USB,
	.properties	= dummy_props,
	.num_properties	= ARRAY_SIZE(dummy_props),
	.get_property	= dummy_get_property,
};

static struct power_supply *dummy_usb_psy;

static const struct power_supply_desc dummy_batt_desc = {
	.name		= "battery",
	.type		= POWER_SUPPLY_TYPE_BATTERY,
	.properties	= dummy_props,
	.num_properties	= ARRAY_SIZE(dummy_props),
	.get_property	= dummy_get_property,
};

static struct power_supply *dummy_batt_psy;

static int __init dummy_psy_init(void)
{
	dummy_usb_psy = power_supply_register(NULL, &dummy_usb_desc, NULL);
	if (IS_ERR(dummy_usb_psy)) {
		pr_err("dummy-psy: usb register failed %ld\n",
		       PTR_ERR(dummy_usb_psy));
		dummy_usb_psy = NULL;
	}
	dummy_batt_psy = power_supply_register(NULL, &dummy_batt_desc, NULL);
	if (IS_ERR(dummy_batt_psy)) {
		pr_err("dummy-psy: battery register failed %ld\n",
		       PTR_ERR(dummy_batt_psy));
		dummy_batt_psy = NULL;
	}
	pr_info("dummy-psy: registered usb=%p battery=%p\n",
		dummy_usb_psy, dummy_batt_psy);
	return 0;
}
late_initcall(dummy_psy_init);
