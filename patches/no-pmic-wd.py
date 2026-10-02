#!/usr/bin/env python3
"""关掉 PMIC(PON)看门狗 —— 这是"每 2~2.5 分钟必硬复位"的真凶。

★ 证据链(2026-10-02,全部来自设备):
  1) sde59 内核日志:内核每次活到约 134 秒被硬复位,且**没有任何 panic 输出**
     (133 秒时还在正常配置音频 CSPL);
  2) 同日志开头:  qcom,qpnp-power-on ... pon_hlos@1300: IRQ pmic-wd-bark not found
     ⇒ 我们拿不到 PMIC 看门狗的 bark 中断;
  3) drivers/input/misc/qpnp-power-on.c:
       static irqreturn_t qpnp_pmic_wd_bark_irq(...) { ... panic("PMIC Watch Dog Triggered"); }
     ⇒ bark 一到就 panic;而 PMIC 看门狗的 S1/S2 定时器是【硬件】在跑,
       到点由 PMIC 自己复位 SoC ⇒ 与内核是否 panic 无关;
  4) 134 秒 ≈ PMIC 看门狗标准超时(约 128 秒) + 启动耗时;
  5) 关掉 CONFIG_PANIC_ON_OOPS/PANIC_ON_SSR_NOTIF_TIMEOUT 后**仍然复位**
     ⇒ 印证复位来自 PMIC 硬件而非内核 panic 链;
  6) 原厂内核同一台机器上稳定 ⇒ 原厂能处理/关掉这个看门狗。

★ 处置:probe 结束时直接把 PON 看门狗的使能位清 0(QPNP_PON_WD_EN),
   并把 bark 中断里的 panic() 降级为打印(双保险)。

用法: no-pmic-wd.py [内核源码根目录,默认当前目录]
⚠️ 不匹配就报错退出(CI 不加 continue-on-error),避免静默失效。
"""
import sys
import os

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "drivers/input/misc/qpnp-power-on.c")

# ── ① bark 中断里的 panic 降级为打印 ──────────────────────────────
OLD1 = """	print_pon_reg(pon, PON_PMIC_WD_RESET_S1_TIMER);
	print_pon_reg(pon, PON_PMIC_WD_RESET_S2_TIMER);
	panic("PMIC Watch Dog Triggered");
"""
NEW1 = """	print_pon_reg(pon, PON_PMIC_WD_RESET_S1_TIMER);
	print_pon_reg(pon, PON_PMIC_WD_RESET_S2_TIMER);
	/* ★ Droidspaces:原为 panic("PMIC Watch Dog Triggered"),
	 *   会使内核立即死掉、丢失现场。改成打印,便于定位。 */
	pr_emerg("logdump: PMIC watchdog bark (panic suppressed by Droidspaces)\\n");
"""

# ── ② probe 末尾关闭 PON 看门狗 ─────────────────────────────────
OLD2 = """	pmic_wd_bark_irq = platform_get_irq_byname(pdev, "pmic-wd-bark");
	/* Request the pmic-wd-bark irq only if it is defined */
	if (pmic_wd_bark_irq >= 0) {
		rc = devm_request_irq(pon->dev, pmic_wd_bark_irq,
					qpnp_pmic_wd_bark_irq,
					IRQF_TRIGGER_RISING,
					"qpnp_pmic_wd_bark", pon);
		if (rc < 0) {
			dev_err(pon->dev, "Can't request %d IRQ, rc=%d\\n",
				pmic_wd_bark_irq, rc);
			return rc;
		}
	}
"""
NEW2 = OLD2 + """
	/*
	 * ★★ Droidspaces:关闭 PON(PMIC)看门狗。
	 *   引导器(XBL)把它开着,超时约 128 秒;到点由 PMIC 硬件复位 SoC,
	 *   现象就是"开机约 2~2.5 分钟必硬复位"(实测 134 秒,且日志无 panic)。
	 *   我们的内核拿不到 "pmic-wd-bark" 中断(日志原话: IRQ pmic-wd-bark not found),
	 *   无法按原厂方式处理,因此这里直接把使能位清 0。
	 */
	rc = qpnp_pon_masked_write(pon, QPNP_PON_WD_RST_S2_CTL2(pon),
				   QPNP_PON_WD_EN, 0);
	if (rc)
		dev_err(pon->dev, "Droidspaces: disable PMIC WD failed rc=%d\\n", rc);
	else
		dev_info(pon->dev, "Droidspaces: PMIC watchdog disabled\\n");
"""

src = open(path).read()
if "Droidspaces: PMIC watchdog disabled" in src:
    print("no-pmic-wd: 已经打过补丁,跳过")
    sys.exit(0)
for name, old, new in (("bark panic 降级", OLD1, NEW1),
                       ("probe 关闭 PMIC WD", OLD2, NEW2)):
    if old not in src:
        print("::error::no-pmic-wd: 找不到 %s 的预期代码" % name)
        sys.exit(1)
    src = src.replace(old, new, 1)
    print("no-pmic-wd: 已处理 %s" % name)
open(path, "w").write(src)
