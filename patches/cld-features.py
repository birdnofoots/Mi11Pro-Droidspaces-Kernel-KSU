#!/usr/bin/env python3
"""cld-features.py <kernel_root> —— 把 QTI qcacld 的 .conf 特性集转成可用的构建开关

背景: CLO 的 qcacld 用 `configs/*.conf`(`CONFIG_X := y` 这种 Makefile 语法 + ifeq 条件)
      驱动它自己的 DLKM 构建; 我们把它挂进内核树编模块时, 这些开关既不是 Kconfig 符号,
      也不是内核 .config 的取值 ⇒ 必须显式传下去, 否则驱动会以"几乎全部特性关闭"的形态编译。

做法:
  1) 解析 default_defconfig / genoa.common / genoa.pci.perf_defconfig (按顺序覆盖)
     规则: `CONFIG_X := y` → y; `:= n` → n; `:= m` → m; 忽略 ifeq/endif/ifneq/注释;
           同一符号后者覆盖前者。
  2) 产出两个东西:
     - <out>/.config.fragment : 形如 CONFIG_X=y / # CONFIG_X is not set  (给内核 .config 合并)
     - <out>/cld_makevars.txt : `CONFIG_X=y` 列表 (给 make 命令行, 覆盖 Kbuild 里的 ccflags-$(CONFIG_X))
  3) 打印统计。
用法: cld-features.py <kernel_root> [输出目录]
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
cfgdir = os.path.join(root, "drivers/staging/qcacld-3.0/configs")
files = ["default_defconfig", "genoa.common", "genoa.pci.perf_defconfig"]

vals = {}
order = []
for fn in files:
    p = os.path.join(cfgdir, fn)
    if not os.path.exists(p):
        print("cld-features: 缺 %s (跳过)" % p)
        continue
    n = 0
    for line in open(p, errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^(ifeq|ifneq|ifdef|ifndef|else|endif)\b", line):
            continue
        m = re.match(r"^(CONFIG_[A-Za-z0-9_]+)\s*:?=\s*([ymn])$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if k not in vals:
            order.append(k)
        vals[k] = v
        n += 1
    print("cld-features: %-28s 解析 %d 行" % (fn, n))

frag = os.path.join(outdir, ".config.fragment")
mv = os.path.join(outdir, "cld_makevars.txt")
with open(frag, "w") as f, open(mv, "w") as g:
    for k in order:
        v = vals[k]
        if v == "n":
            f.write("# %s is not set\n" % k)
        else:
            f.write("%s=%s\n" % (k, v))
        g.write("%s=%s\n" % (k, v))
ys = sum(1 for k in order if vals[k] == "y")
print("cld-features: 共 %d 个开关 (y=%d, m=%d, n=%d) → %s / %s"
      % (len(order), ys, sum(1 for k in order if vals[k] == "m"),
         sum(1 for k in order if vals[k] == "n"), frag, mv))
