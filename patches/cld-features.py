#!/usr/bin/env python3
"""cld-features.py <kernel_root> [输出目录] [内核 .config] —— 把 QTI qcacld 的 .conf 特性集转成可用的构建开关

背景: CLO 的 qcacld 用 `configs/*.conf`(`CONFIG_X := y` 这种 Makefile 语法 + ifeq 条件)
      驱动它自己的 DLKM 构建; 我们把它挂进内核树编模块时, 这些开关既不是 Kconfig 符号,
      也不是内核 .config 的取值 ⇒ 必须显式传下去, 否则驱动会以"几乎全部特性关闭"的形态编译。

做法:
  1) 解析 default_defconfig / genoa.common / genoa.pci.perf_defconfig (按顺序覆盖)
     **并且真正求值 ifeq/ifneq/ifdef/ifndef/else**(按 Makefile 语义, 支持 $(findstring a,b)
     和 $(VAR) 展开)。条件里引用的 CONFIG_* 用内核真实 .config(第 3 个参数)做种子,
     否则用已解析到的值。
     血泪教训: 老版本忽略条件, 把 default_defconfig 里 `ifeq ($(CONFIG_ROME_IF),ipci)`
     分支的 `CONFIG_HIF_IPCI := y`、usb/sdio 分支的开关全当成"打开" ⇒ HIF_PCI 与
     HIF_IPCI 同时定义 ⇒ regtable_pcie.h / regtable_ipcie.h 在同一 TU 里互相重定义。
  2) 产出两个东西:
     - <out>/.config.fragment : 形如 CONFIG_X=y / # CONFIG_X is not set  (给内核 .config 合并)
     - <out>/cld_makevars.txt : `CONFIG_X=y` 列表 (给 make 命令行, 覆盖 Kbuild 里的 ccflags-$(CONFIG_X))
  3) 打印统计。
用法: cld-features.py <kernel_root> [输出目录] [kernel/.config]
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
kconfig = sys.argv[3] if len(sys.argv) > 3 else ""
cfgdir = os.path.join(root, "drivers/staging/qcacld-3.0/configs")
files = ["default_defconfig", "genoa.common", "genoa.pci.perf_defconfig"]

# ---- 种子: 内核真实 .config(条件里的 CONFIG_ARCH_LAHAINA / CONFIG_CNSS2 等靠它) ----
vals = {}
if kconfig and os.path.exists(kconfig):
    n_seed = 0
    for line in open(kconfig, errors="ignore"):
        line = line.strip()
        m = re.match(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$", line)
        if m:
            vals[m.group(1)] = m.group(2)
            n_seed += 1
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            vals[line.split()[1]] = "n"
            n_seed += 1
    print("cld-features: 内核 .config 种子 %d 个符号 (%s)" % (n_seed, kconfig))
# 目标平台固定: mars = SM8350/LAHAINA + PCIe WLAN(cnss2 pld_pcie)
vals.setdefault("CONFIG_ROME_IF", "pci")
vals.setdefault("CONFIG_ARCH_LAHAINA", "y")
vals.setdefault("CONFIG_HIF_PCI", "y")

order = []


def expand(s):
    """展开 $(VAR) 与 $(findstring a,b); 展开不干净的返回 None(视为不可判定)"""
    for _ in range(6):
        if "$(findstring" not in s:
            break
        s = re.sub(r"\$\(findstring\s+([^,()]+),([^()]*)\)",
                   lambda m: m.group(1) if m.group(1) in m.group(2) else "", s)
    s = re.sub(r"\$\(([A-Za-z0-9_]+)\)", lambda m: vals.get(m.group(1), ""), s)
    return None if "$(" in s else s.strip()


def split_args(inner):
    """ifeq (A,B) 的 A,B(支持嵌套括号/逗号)"""
    d = 0
    for i, ch in enumerate(inner):
        if ch in "([":
            d += 1
        elif ch in ")]":
            d -= 1
        elif ch == "," and d == 0:
            return inner[:i], inner[i + 1:]
    return inner, ""


def cond_value(line):
    """求值一个条件行; 判断不了就当作 False(保守, 只少开特性不多开)"""
    m = re.match(r"^(ifeq|ifneq|ifdef|ifndef)\s*(.*)$", line)
    if not m:
        return None, False
    kind, rest = m.group(1), m.group(2).strip()
    if kind in ("ifdef", "ifndef"):
        v = expand(rest) if "$(" in rest else rest
        defined = bool(v) and vals.get(v, "") not in ("", "n")
        return kind, (defined if kind == "ifdef" else not defined)
    if rest.startswith("(") and rest.endswith(")"):
        a, b = split_args(rest[1:-1])
    else:  # ifeq "a" "b"
        parts = re.findall(r'"([^"]*)"', rest)
        if len(parts) != 2:
            return kind, False
        a, b = parts
    ea, eb = expand(a), expand(b)
    if ea is None or eb is None:
        return kind, False
    eq = (ea == eb)
    return kind, (eq if kind == "ifeq" else not eq)


# 条件栈: 每层 (parent_active, cur_active, taken)
stack = []


def active():
    return all(f[1] for f in stack)


for fn in files:
    p = os.path.join(cfgdir, fn)
    if not os.path.exists(p):
        print("cld-features: 缺 %s (跳过)" % p)
        continue
    n = 0
    for raw in open(p, errors="ignore"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(ifeq|ifneq|ifdef|ifndef)\b(.*)$", line)
        if m:
            _, c = cond_value(line)
            stack.append((active(), c, c))
            continue
        if re.match(r"^else\b", line):
            if not stack:
                continue
            parent, _, taken = stack.pop()
            rest = line[4:].strip()
            if rest:
                _, c = cond_value(rest)
                c = c and not taken
            else:
                c = not taken
            stack.append((parent, c, taken or c))
            continue
        if re.match(r"^endif\b", line):
            if stack:
                stack.pop()
            continue
        m = re.match(r"^(CONFIG_[A-Za-z0-9_]+)\s*:?=\s*(\S+)\s*$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if v not in ("y", "m", "n"):
            vals[k] = v  # 记进上下文(如 CONFIG_ROME_IF = pci), 但不写进输出
            continue
        if not active():
            continue
        if k not in order:
            order.append(k)
        vals[k] = v
        n += 1
    print("cld-features: %-28s 生效 %d 行" % (fn, n))

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
for k in ("CONFIG_HIF_PCI", "CONFIG_HIF_IPCI", "CONFIG_HIF_USB", "CONFIG_HIF_SDIO",
          "CONFIG_HIF_SNOC", "CONFIG_PLD_PCIE_CNSS_FLAG", "CONFIG_ROME_IF"):
    print("  %-32s = %s" % (k, vals.get(k, "(未设置)")))
