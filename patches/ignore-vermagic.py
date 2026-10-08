#!/usr/bin/env python3
"""ignore-vermagic.py <kernel_root> —— 让内核【忽略 vermagic 不一致】(与小米原厂内核行为一致)

★★ 2026-10-09 铁证(从手机 272 个原厂模块里统计):
    224 个 vermagic = "5.4.233-gbb70cde46897 SMP preempt mod_unload modversions aarch64"(无 qgki)
     48 个 vermagic = "5.4.233-qgki-gbb70cde46897 ..."(含 qgki)
    关键模块(msm_drm/cnss2/qca_cld3_wlan/qti_battery_charger_main/hwid/fts_touch_spi_k2)
    全部属于【无 qgki】那组,而我们的 vermagic 补丁硬编码的是【含 qgki】⇒ 全被拒装。
    两个组不可能同时匹配同一个字符串,而**原厂内核 dmesg 里 version magic 错误数 = 0** ⇒
    原厂内核根本不执行这道校验(Xiaomi 自己 patch 掉了)。所以正确做法不是"猜字符串",
    而是像原厂一样【忽略 vermagic 不一致】(仍打印 warning)。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/module.c")
s = open(path, errors="ignore").read()
if "mars-ignore-vermagic" in s:
    print("ignore-vermagic: skip (already applied)")
    sys.exit(0)

# 1) 直接把 same_magic 的失败分支改成"只警告"
pat = re.compile(r"(\}\s*else if \(!same_magic\(modmagic, vermagic, info->index\.vers\)\) \{)(.*?)(\n\s*\})", re.S)
m = pat.search(s)
if not m:
    print("ignore-vermagic: 没找到 same_magic 检查")
    sys.exit(1)
repl = ('} else if (!same_magic(modmagic, vermagic, info->index.vers)) {\n'
        '\t\t/* mars-ignore-vermagic: 原厂内核不做 vermagic 校验(实测两套 vermagic 并存且 dmesg 0 错误) */\n'
        '\t\tpr_warn("%s: version magic \'%s\' != \'%s\' (mars: ignored)\\n",\n'
        '\t\t\tinfo->name, modmagic, vermagic);\n'
        '\t}')
s = s[:m.start()] + repl + s[m.end():]

# 2) try_to_force_load 也放行(万一 vermagic 字段整个缺失)
s = s.replace('\t\terr = try_to_force_load(mod, "bad vermagic");',
              '\t\t/* mars-ignore-vermagic */ err = 0;', 1)
open(path, "w").write(s)
chk = open(path, errors="ignore").read()
assert "mars-ignore-vermagic" in chk
print("ignore-vermagic: 已注入(vermagic 不匹配只警告,不再拒装)")
