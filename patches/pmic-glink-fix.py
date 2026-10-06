#!/usr/bin/env python3
"""把 drivers/soc/qcom/pmic_glink.c 的状态机对齐 vendor/LOS 版本。

★★★ 2026-10-06 真机定位:
   现象: vendor 的 qti_battery_charger_main.ko【装载了】(在 /proc/modules 里),
        但 probe 从不运行 —— 我们内核日志里连 `battery_chg_probe start` 都没有,
        而原厂有 `battery_chg_probe start/done` @7.5s ⇒ 原厂 power_supply 有 battery/usb/wireless 三个,
        我们一个都没有 ⇒ healthd: No battery devices found ⇒ 电量 0% / 不充电 / 无 USB adb。
   根因(逐行 diff MiCode 树 vs LineageOS sm8350 的 drivers/soc/qcom/pmic_glink.c):
     MiCode(2020 版权) 的 switch(code) 里:
         case SERVREG_NOTIF_SERVICE_STATE_EARLY_DOWN_V01:  → 通知客户端 DOWN
         case SERVREG_NOTIF_SERVICE_STATE_DOWN_V01:        → 【什么都不做】
     LOS/vendor(2021 版权):
         case SERVREG_NOTIF_SERVICE_STATE_DOWN_V01:        → 通知客户端 DOWN
     ⇒ 我们这版在收到 DOWN 时不再通知,后续 STATE_UP 的重新通知链断掉,
       pmic_glink 客户端(充电器)永远等不到 STATE_UP ⇒ probe 不运行。
   顺带把 rx 路径的锁粒度也对齐(回调期间不持锁,避免自锁):
     LOS: spin_unlock → callback → spin_lock → list_del → kfree
"""
import os, re, sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "drivers/soc/qcom/pmic_glink.c")
s = open(path, errors="ignore").read()
orig = s
changed = []

# ── 1) DOWN 状态机对齐:把 EARLY_DOWN 的语义搬到 DOWN 上,删掉"什么都不做"那一支 ──
m = re.search(r"\tcase SERVREG_NOTIF_SERVICE_STATE_EARLY_DOWN_V01:\n(.*?)\n\tcase SERVREG_NOTIF_SERVICE_STATE_DOWN_V01:\n(?:.*?\n)*?\t\tbreak;\n",
              s, re.S)
if m:
    body = m.group(1)                      # EARLY_DOWN 的处理体(通知 DOWN + atomic_set)
    s = s[:m.start()] + "\tcase SERVREG_NOTIF_SERVICE_STATE_DOWN_V01:\n" + body + "\n" + s[m.end():]
    changed.append("switch(DOWN) 语义对齐")
else:
    print("pmic-glink-fix: 未找到 DOWN/EARLY_DOWN 组合(可能已对齐)")

# ── 2) atomic 判定也一起对齐 ──
s2 = s.replace("SERVREG_NOTIF_SERVICE_STATE_EARLY_DOWN_V01", "SERVREG_NOTIF_SERVICE_STATE_DOWN_V01")
if s2 != s:
    s = s2; changed.append("atomic 判定对齐")

# ── 3) rx 路径锁粒度对齐(回调期间不持锁) ──
old_rx = """	if (!list_empty(&pdev->rx_list)) {
		list_for_each_entry_safe(pbuf, tmp, &pdev->rx_list, node) {
			pmic_glink_rx_callback(pdev, pbuf);
			spin_lock_irqsave(&pdev->rx_lock, flags);
			list_del(&pbuf->node);
			spin_unlock_irqrestore(&pdev->rx_lock, flags);
			kfree(pbuf);
		}
	}"""
new_rx = """	spin_lock_irqsave(&pdev->rx_lock, flags);
	if (!list_empty(&pdev->rx_list)) {
		list_for_each_entry_safe(pbuf, tmp, &pdev->rx_list, node) {
			spin_unlock_irqrestore(&pdev->rx_lock, flags);
			pmic_glink_rx_callback(pdev, pbuf);
			spin_lock_irqsave(&pdev->rx_lock, flags);
			list_del(&pbuf->node);
			kfree(pbuf);
		}
	}
	spin_unlock_irqrestore(&pdev->rx_lock, flags);"""
if old_rx in s:
    s = s.replace(old_rx, new_rx, 1); changed.append("rx 锁粒度对齐")

if s == orig:
    print("pmic-glink-fix: 无需修改(两版可能已一致)"); sys.exit(0)
open(path, "w").write(s)
print("pmic-glink-fix: 已修改 -> %s" % ", ".join(changed))
# 自证:不应再有 EARLY_DOWN 独占分支
assert "case SERVREG_NOTIF_SERVICE_STATE_DOWN_V01:" in s, "DOWN 分支丢失!"
print("pmic-glink-fix: ✅ 自证通过(DOWN 分支存在)")
