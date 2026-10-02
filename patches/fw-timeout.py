#!/usr/bin/env python3
"""把固件"用户态回退"的超时从 60 秒改小(默认 5 秒)。

★ 为什么(2026-10-03 从 sde59 现场拿到的铁证,见 TAKEOVER.md §73):
  开机 49.8~54.7s 的全任务栈里同时出现:
    modprobe D ... request_firmware_work_func / process_one_work   ← 固件落到用户态回退
    modprobe D ... __mutex_lock ... load_module                    ← 模块 init 在等 module_mutex
    init(用户态)卡在等 vendor_modprobe 批量
  ⇒ vendor 那批模块里有一个(基本确定是 cnss2/WLAN)在 init 里 request_firmware,
    直接读 /vendor/firmware 失败后落到【用户态回退】,而用户态 init 正等这批模块装完
    ⇒ 循环等待 ⇒ 该模块 init 永不返回 ⇒ module_mutex 被永久占住
    ⇒ msm_drm(显示)/触摸/电池等 29 个模块全装不上(症状:无显示、无 WiFi)。

★ 做法:只把 loading_timeout 的默认值 60 改小到 5 秒(回退机制本身保留,
  显卡等"直接读能成功"的固件完全不受影响)。5 秒内等不到用户态喂固件就放弃,
  该模块 init 带着错误返回 ⇒ module_mutex 释放 ⇒ 其余模块正常装载。

用法: fw-timeout.py [内核源码根目录,默认当前目录]
⚠️ 找不到锚点不报错(不同树变量名可能不同),但会明确打印。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
P = os.path.join(root, "drivers/base/firmware_loader/main.c")
NEW_TIMEOUT = 5

if not os.path.exists(P):
    print("fw-timeout: 找不到 %s —— 跳过" % P)
    sys.exit(0)

s = open(P, encoding="utf-8", errors="replace").read()
if "mars 补丁:回退超时" in s:
    print("fw-timeout: 已打过,跳过")
    sys.exit(0)

pat = re.compile(r"(static\s+unsigned\s+int\s+loading_timeout\s*=\s*)(\d+)(\s*;)")
m = pat.search(s)
if not m:
    print("fw-timeout: 没找到 `static unsigned int loading_timeout = N;` —— 跳过(不报错)")
    sys.exit(0)

old_val = m.group(2)
s = s[:m.start()] + ("%s%d%s\t/* ★ mars 补丁:回退超时 %s→%d 秒,"
                     "拆掉 module_mutex 循环等待 */"
                     % (m.group(1), NEW_TIMEOUT, m.group(3), old_val, NEW_TIMEOUT)) + s[m.end():]
open(P, "w", encoding="utf-8").write(s)
print("fw-timeout: loading_timeout %s → %d 秒" % (old_val, NEW_TIMEOUT))
