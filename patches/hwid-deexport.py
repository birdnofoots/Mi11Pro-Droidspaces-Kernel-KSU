#!/usr/bin/env python3
"""hwid-deexport.py <kernel_root> —— 去掉内建 hwid 的 EXPORT_SYMBOL, 让【原厂 hwid.ko】能装上

为什么(2026-10-09 实机取证):
  原厂 WLAN 栈是一条依赖链: cnss2.ko -> hwid.ko / qmi_helpers / v01 服务;
  原厂 lsmod 实证: `hwid 24576 5 camera,fts_touch_spi_k2,qti_battery_charger_main,icnss2,cnss2`。
  allbuiltin 把 hwid 编进了内核(drivers/misc/hwid.c, 9 个 EXPORT_SYMBOL),
  于是原厂 hwid.ko 被 "exports duplicate symbol get_hw_country_version (owned by kernel)" 拒装,
  init 的 modules.load 依赖解析随之跳过 cnss2 ⇒ 开机时整个 WLAN 栈都起不来。

  内建的 hwid 只服务【内建】的 camera/battery 代码(直接调用, 不需要导出),
  所以把导出摘掉是安全的: 原厂 hwid.ko 装上后, 原厂 camera/touch/battery/cnss2 模块
  从这里拿符号, 与原厂系统完全一致。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "drivers/misc/hwid.c")
if not os.path.exists(path):
    print("hwid-deexport: 找不到 %s" % path)
    sys.exit(1)

s = open(path, errors="ignore").read()
if "mars-hwid-deexport" in s:
    print("hwid-deexport: 已处理过, 跳过")
    sys.exit(0)

# 把 EXPORT_SYMBOL / EXPORT_SYMBOL_GPL 注释掉(保留函数定义, 内建调用者照旧)
new, n = re.subn(r'^(EXPORT_SYMBOL(?:_GPL)?\s*\([^)]*\)\s*;)\s*$',
                 r'/* mars-hwid-deexport: \1 去掉导出, 让原厂 hwid.ko 独占这些符号 */',
                 s, flags=re.M)

if n == 0:
    print("hwid-deexport: 没找到 EXPORT_SYMBOL, 可能路径不对")
    sys.exit(1)

open(path, "w").write(new)
chk = open(path, errors="ignore").read()
left = len(re.findall(r'^EXPORT_SYMBOL', chk, flags=re.M))
assert "mars-hwid-deexport" in chk
print("hwid-deexport: 注释掉 %d 个导出, 剩余有效 EXPORT_SYMBOL=%d" % (n, left))
