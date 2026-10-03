#!/usr/bin/env python3
"""把固件"用户态回退"的等待超时 60s 改小到 5s(机制保留)。

★ 为什么 —— 2026-10-03 从 sde59 现场拿到的铁证(TAKEOVER.md §73):
  开机 49.8~54.7s 的全任务栈里同时出现:
    modprobe D ... request_firmware_work_func / process_one_work   ← 固件落到用户态回退
    modprobe D ... __mutex_lock ... load_module                    ← 模块 init 在等 module_mutex
    init(用户态)卡在等 vendor_modprobe 批量
  ⇒ vendor 那批模块里有一个(基本确定是 cnss2/WLAN)在 init 里 request_firmware,
    直接读 /vendor/firmware 失败后落到【用户态回退】,而用户态 init 正等这批模块装完
    ⇒ 循环等待 ⇒ 该模块 init 永不返回 ⇒ module_mutex 被永久占住
    ⇒ msm_drm(显示)/触摸/电池等 29 个模块全装不上(症状:无显示、无 WiFi)。

★ 为什么改这里而不是关掉回退:
  `CONFIG_FW_LOADER_USER_HELPER_FALLBACK=n` 那版实测【内核启动前就死】(见 §73),
  而只把回退超时改小可以保留回退机制 —— 显卡等"直接读能得到"的固件完全不受影响,
  只有"怎么等都等不到用户态"的模块会在 5 秒后放弃 ⇒ 该模块快速失败 ⇒ 锁释放。

★ 落点(实测这棵树): drivers/base/firmware_loader/fallback_table.c
      struct firmware_fallback_config fw_fallback_config = {
              .loading_timeout = 60,
              .old_timeout     = 60,
      };
  (main.c/fallback.c 里只有 getter/setter,没有初值。) 用目录通配更稳,不写死文件名。

用法: fw-timeout.py [内核源码根目录,默认当前目录]
⚠️ 改到 0 处不报错,但会明确打印(便于在构建日志里核对)。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
d = os.path.join(root, "drivers/base/firmware_loader")
NEW = 2

if not os.path.isdir(d):
    print("fw-timeout: 找不到 %s —— 跳过" % d)
    sys.exit(0)

pat = re.compile(r"(\.(?:loading_timeout|old_timeout)\s*=\s*)(\d+)(\s*,)")
total = 0
for fn in sorted(os.listdir(d)):
    if not fn.endswith(".c"):
        continue
    p = os.path.join(d, fn)
    s = open(p, encoding="utf-8", errors="replace").read()
    if "mars 补丁:固件回退超时" in s:
        print("fw-timeout: %s 已打过,跳过" % fn)
        continue
    hits = pat.findall(s)
    if not hits:
        continue
    s2 = pat.sub(lambda m: "%s%d%s /* ★ mars 补丁:固件回退超时 %s→%d 秒 */"
                 % (m.group(1), NEW, m.group(3), m.group(2), NEW), s)
    open(p, "w", encoding="utf-8").write(s2)
    for m in re.finditer(r"\.(?:loading_timeout|old_timeout)\s*=\s*(\d+)", s):
        print("fw-timeout: %s  %s → %d" % (fn, m.group(0), NEW))
    total += len(hits)

if total == 0:
    print("fw-timeout: 一处都没改到(这棵树可能没有 fallback_table.c)—— 跳过")
else:
    print("fw-timeout: 共改 %d 处,固件回退超时 = %d 秒" % (total, NEW))
