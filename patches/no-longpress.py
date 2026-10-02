#!/usr/bin/env python3
"""中立化 MIUI 的「长按组合键(Power+Vol-)」相关路径(一共两处)。

★ 背景(2026-10-02 实测,证据链完整):
  自编内核(star-stock + mi_syms 桩)刷入后,【开机后不久必定重启】,
  之后每轮 2.5~3 分钟再复位,无限循环。sde59(logdump 分区)日志:

  第一版(未打补丁):
    [ 9.698201] ------ collect D&R-state processes info before long comb key ------
    [ 9.712180] sd 0:0:0:0: [sda] Synchronizing SCSI cache   ← 有序关机
  第二版(只中立化了 longpress_kthread 里的 machine_restart):
    内核活到 77 秒(vs 11.5 秒),但日志在 [76.04s] 的一大段任务表中间
    【无任何关机信息直接断掉】 ⇒ 不是有序关机,而是卡死/看门狗复位。

  对应源码 drivers/input/misc/qpnp-power-on.c:
    ① collect_d_work_func():一旦读到 PMIC 的 KPDPWR+RESIN 状态位成立,就
         console_verbose();                       // ★ 把 console_loglevel 拉到最高
         show_state_filter_single(TASK_UNINTERRUPTIBLE);
         show_state_filter_single(TASK_RUNNING);  // 打印【全部任务】
       本机 cmdline 有 console=ttyMSM0,115200n8 ⇒ 几千行 × 约 7ms ≈
       数十秒~数分钟的串口打印 ⇒ 系统等同卡死 ⇒ 看门狗复位 ✓(与观测吻合)。
    ② qpnp_pon_config_parse_reset_info():DT 里有 PON_KPDPWR_RESIN 就把
         comb_reset_enable = true;  ⇒ 上面的 ① 才会被 IRQ 处理器调度。

  原厂内核在同一台机器上从不触发(原厂 dmesg 里没有 long comb key 这行,
  用 root 监视 30 分钟 longcomb 计数始终为 0)。

  本补丁把【整条诊断路径】中立化(不只是最后那一步重启):
    · collect_d_work_func() → 只清标志位后返回(不再 console_verbose/打印全部任务)
    · comb_reset_enable    → 永远保持 false(IRQ 处理器不再调度上面那个 work)
  代价:失去 MIUI 的「长按 Power+Vol- 」组合键诊断/快捷行为 ✓
  (关机状态下用【音量下+电源】从 bootloader 进 fastboot 不受影响 ✓)。

用法: no-longpress.py [内核源码根目录,默认当前目录]
⚠️ 任一替换不匹配就报错退出(CI 里不加 continue-on-error),避免静默失效。
"""
import sys
import os

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "drivers/input/misc/qpnp-power-on.c")

# ── ① longpress_kthread:去掉 mi_display_pm_suspend() + machine_restart() ──
OLD1 = """static int longpress_kthread(void *_pon)
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

NEW1 = """static int longpress_kthread(void *_pon)
{
#ifdef CONFIG_MTD_BLOCK2MTD
	struct qpnp_pon *pon = _pon;

	/*
	 * ★ Droidspaces 自编内核:中立化 MIUI 的「长按 Power+Vol- → 重启」。
	 *   原实现 mi_display_pm_suspend() + long_press() + mdelay() +
	 *   machine_restart(NULL),在自编内核上表现为开机不久必重启
	 *   (完整证据链见本仓库 patches/no-longpress.py 顶部注释)。
	 */
	dev_info(pon->dev, "longpress: reboot suppressed (Droidspaces build)\\n");
#endif

	return 0;
}"""

# ── ② collect_d_work_func:去掉 console_verbose() + 打印全部任务 ──
OLD2 = """static void collect_d_work_func(struct work_struct *work)
{
	int rc;
	int tmp_console = console_loglevel;
	uint pon_rt_sts = 0;
	struct qpnp_pon *pon =
		container_of(work, struct qpnp_pon, collect_d_work.work);

	/* check the RT status to get the current status of the line */
	rc = regmap_read(pon->regmap, QPNP_PON_RT_STS(pon), &pon_rt_sts);
	if (rc) {
		dev_err(pon->dev, "Unable to read PON RT status\\n");
		goto err_return;
	}
	if ((pon_rt_sts & QPNP_PON_KPDPWR_RESIN_N_SET) == QPNP_PON_KPDPWR_RESIN_N_SET) {
		console_verbose();
		pr_info("------ collect D&R-state processes info before long comb key ------\\n");
		show_state_filter_single(TASK_UNINTERRUPTIBLE);
		show_state_filter_single(TASK_RUNNING);
		pr_info("------ end collecting D&R-state processes info ------\\n");
		console_loglevel = tmp_console;
	}
err_return:
	pon->collect_d_in_progress = false;
	return;
}"""

NEW2 = """static void collect_d_work_func(struct work_struct *work)
{
	struct qpnp_pon *pon =
		container_of(work, struct qpnp_pon, collect_d_work.work);

	/*
	 * ★ Droidspaces 自编内核:中立化「组合键复位前的 D&R 诊断」。
	 *   原实现先 console_verbose() 把 console_loglevel 拉到最高,再
	 *   show_state_filter_single() 打印【全部任务】;而本机 cmdline 里是
	 *   console=ttyMSM0,115200n8 ⇒ 几千行 × 约 7ms = 数十秒~数分钟串口打印,
	 *   系统等同卡死 ⇒ 看门狗复位(实测日志在 76 秒处没有任何关机信息直接断掉)。
	 *   这里只清标志位就返回。
	 */
	pon->collect_d_in_progress = false;
}"""

# ── ③ 不让 IRQ 处理器有机会调度上面那个 work ──
OLD3 = """		if (cfg->pon_type == PON_KPDPWR_RESIN) {
			comb_reset_time = cfg->s1_timer + cfg->s2_timer;
			comb_reset_enable = true;
		}"""

NEW3 = """		if (cfg->pon_type == PON_KPDPWR_RESIN) {
			comb_reset_time = cfg->s1_timer + cfg->s2_timer;
			/* ★ Droidspaces:永不启用组合键复位诊断(见文件头注释) */
			comb_reset_enable = false;
		}"""

src = open(path).read()
if "Droidspaces" in src and NEW1 in src and NEW2 in src and NEW3 in src:
    print("no-longpress: 已经打过补丁,跳过")
    sys.exit(0)

for name, old, new in (("longpress_kthread", OLD1, NEW1),
                       ("collect_d_work_func", OLD2, NEW2),
                       ("comb_reset_enable", OLD3, NEW3)):
    if new in src:
        print("no-longpress: %s 已是补丁后状态,跳过" % name)
        continue
    if old not in src:
        print("::error::no-longpress: 在 %s 里没找到 %s 的预期代码 —— "
              "上游源码变了,补丁需要同步更新" % (path, name))
        sys.exit(1)
    src = src.replace(old, new, 1)
    print("no-longpress: 已中立化 %s" % name)

open(path, "w").write(src)
print("no-longpress: 完成(重启 + D&R 诊断两条路径都已中立化)")
