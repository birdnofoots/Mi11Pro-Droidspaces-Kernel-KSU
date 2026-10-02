#!/usr/bin/env python3
"""中立化 MIUI 的「长按组合键(Power+Vol-) → 重启」行为。

★ 背景(2026-10-02 实测,证据链完整):
  自编内核(star-stock + mi_syms 桩)刷入后,【开机约 9.7 秒必定重启】,
  之后每轮 2.5~3 分钟(关机流程卡住)再复位,无限循环。
  从 sde59(logdump 分区)取回的内核日志显示:

    [ 9.698201] ------ collect D&R-state processes info before long comb key ------
    [ 9.698260] longpress       D 15232  128  2
    [ 9.712180] sd 0:0:0:0: [sda] Synchronizing SCSI cache      ← 关机开始
    [11.537583] Modules linked in:

  对应源码 drivers/input/misc/qpnp-power-on.c:
    * qpnp_pon_irq_handler() 的 PON_KPDPWR_RESIN 分支,一旦
      (pon_rt_sts & QPNP_PON_KPDPWR_RESIN_N_SET) == ... 就
      schedule_delayed_work(&pon->collect_d_work, ...)  → 打印上面的 D&R;
    * longpress_kthread() 被 kpdpwr-bark IRQ 唤醒后:
        mi_display_pm_suspend(); long_press(); ... mdelay(...);
        machine_restart(NULL);      ← 重启

  原厂内核在同一台机器上从不触发(原厂 dmesg 里没有这行,系统可稳定运行),
  但自编内核每轮必触发。本补丁不去猜 PMIC 那条状态位为何不同,而是
  直接让这条 MIUI 捷径失效 —— 进 fastboot 仍可在关机状态下用
  【音量下 + 电源】从 bootloader 进入,不受影响。

用法: no-longpress.py [内核源码根目录,默认当前目录]
⚠️ 不匹配就报错退出(CI 里不加 continue-on-error),避免静默失效。
"""
import sys
import os

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "drivers/input/misc/qpnp-power-on.c")

OLD = """static int longpress_kthread(void *_pon)
{
#ifdef CONFIG_MTD_BLOCK2MTD
	struct qpnp_pon *pon = _pon;
	ktime_t time_to_S2, time_S2;

	dev_err(pon->dev, "Long press :Start to run longpress_kthread ");
	mi_display_pm_suspend();

	long_press();

	time_S2 = pon->pon_cfg->s2_timer;
	time_to_S2 = time_S2 - ktime_ms_delta(ktime_get(), pon->time_kpdpwr_bark);

	if (time_to_S2 > 0)
		mdelay(time_to_S2);

	machine_restart(NULL);
#endif

	return 0;
}"""

NEW = """static int longpress_kthread(void *_pon)
{
#ifdef CONFIG_MTD_BLOCK2MTD
	struct qpnp_pon *pon = _pon;

	/*
	 * ★ Droidspaces 自编内核:中立化 MIUI 的「长按 Power+Vol- → 重启」。
	 *   原实现会 mi_display_pm_suspend() + long_press() + mdelay() +
	 *   machine_restart(NULL),在自编内核上表现为【开机约 9.7 秒必重启】
	 *   (见本仓库 patches/no-longpress.py 顶部的完整证据链)。
	 *   这里只留一行提示,不再重启。
	 */
	dev_info(pon->dev, "longpress: reboot suppressed (Droidspaces build)\\n");
#endif

	return 0;
}"""

src = open(path).read()
if NEW in src:
    print("no-longpress: 已经打过补丁,跳过")
    sys.exit(0)
if OLD not in src:
    print("::error::no-longpress: 在 %s 里没找到预期的 longpress_kthread() —— "
          "上游源码变了,补丁需要同步更新" % path)
    sys.exit(1)
src = src.replace(OLD, NEW, 1)
open(path, "w").write(src)
print("no-longpress: 已中立化 longpress_kthread() 里的 machine_restart()")
