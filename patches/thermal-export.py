#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""thermal-export.py —— 让自编内核导出 thermal_class / thermal_message_dev

★★ 根因(star-r-oss 实测,2026-10-06):
  手机 /vendor/lib/modules 里的原厂模块 mi_thermal_interface.ko(114 个原厂
  vendor 模块之一)导入表里有 thermal_class 与 thermal_message_dev;原厂
  vmlinux 也【导出】它们(/proc/kallsyms:thermal_class=D、thermal_message_dev=B,
  均为全局符号)。

  而 MiCode/Xiaomi_Kernel_OpenSource@star-r-oss 的
      drivers/thermal/thermal_core.c
  里这两个符号都是【static、且没有任何 EXPORT_SYMBOL】:

      static struct class thermal_class = { ... };      # 无 Kconfig 门(随 CONFIG_THERMAL)
      #ifdef CONFIG_QTI_THERMAL
      static struct device thermal_message_dev;         # 门 = CONFIG_QTI_THERMAL
      #endif

  运行配置里 CONFIG_THERMAL=y、CONFIG_QTI_THERMAL=y ⇒ 文件【确实被编进内核】,
  但符号是文件局部(static)的 ⇒ 不进 ksymtab ⇒ 原厂 mi_thermal_interface.ko 在
  我们内核上报 "Unknown symbol thermal_class / thermal_message_dev"。

  ⇒ 结论:根因是 (b)【已经编进内核,但没有 EXPORT_SYMBOL】,
          不是 (a) 文件/ Kconfig 没编。

★ 为什么【可以】导出,而不会重蹈 msm_drm 那 40+ 个撞名符号的覆辙:
  那些撞名符号是因为 vendor msm_drm.ko 自己也在导出它们,内核再导出会让
  msm_drm.ko 被 verify_exported_symbols() 以
  "exports duplicate symbol X (owned by kernel)" 拒装。
  但本机原厂 msm_drm.ko(work/msm_drm.ko,4434816 字节)的 __ksymtab 共 55 项,
  【不含】thermal_class / thermal_message_dev(已用 readelf -sW 逐项核对)。
  更强的一般性论证:原厂 mi_thermal_interface.ko 能加载 ⇒ 原厂内核导出过这两个
  符号 ⇒ 原厂 114 个 vendor 模块中【不可能】还有谁导出同名符号(否则它自己会先被
  拒装)⇒ 我们内核导出这两个符号不会与任何原厂模块撞名。

★ 修法(本脚本):
  1) 去掉两个定义上的 `static`;
  2) 在文件尾部补:
         EXPORT_SYMBOL(thermal_class);
         #ifdef CONFIG_QTI_THERMAL
         EXPORT_SYMBOL(thermal_message_dev);
         #endif
  用最朴素的 EXPORT_SYMBOL(不是 _GPL),保证非 GPL 的 vendor 模块也能解析。

★ ⚠️ 必须同步修改 build.yml(见 README「落地位置」):
  在【取消导出】步骤和【断言】步骤的 NAMES 列表里各删掉
  'thermal_class', 'thermal_message_dev' 两个名字,否则:
    · 取消导出步骤会把本脚本刚补上的 EXPORT_SYMBOL 又注释掉;或者
    · 断言步骤会因为 Module.symvers 里出现这两个符号而
      `::error::` 直接 fail 掉构建。

用法:
    python3 thermal-export.py [内核树根目录]     # 默认 "."
"""

import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
path = os.path.join(root, 'drivers/thermal/thermal_core.c')
if not os.path.isfile(path):
    print('::error:: thermal-export: 找不到 %s' % path)
    raise SystemExit(1)

src = open(path, encoding='utf-8', errors='ignore').read()
orig = src

MARK = ('/* === CI: export MIUI thermal symbols '
        '(vendor mi_thermal_interface.ko imports them) === */')

# ── 1) thermal_class: static struct class thermal_class = { ... }; ──────────
m = re.search(r'(?m)^static([ \t]+struct[ \t]+class[ \t]+thermal_class[ \t]*=)', src)
if m:
    src = src[:m.start()] + m.group(1).lstrip() + src[m.end():]
    print('thermal-export: 已去掉 thermal_class 的 static')
elif re.search(r'(?m)^struct[ \t]+class[ \t]+thermal_class[ \t]*=', src):
    print('thermal-export: thermal_class 已是全局(幂等,跳过)')
else:
    print('::error:: thermal-export: 在 %s 里找不到 thermal_class 定义' % path)
    raise SystemExit(1)

# ── 2) thermal_message_dev: static struct device thermal_message_dev; ──────
want_msg = True
m = re.search(r'(?m)^static([ \t]+struct[ \t]+device[ \t]+thermal_message_dev[ \t]*;)', src)
if m:
    src = src[:m.start()] + m.group(1).lstrip() + src[m.end():]
    print('thermal-export: 已去掉 thermal_message_dev 的 static')
elif re.search(r'(?m)^struct[ \t]+device[ \t]+thermal_message_dev[ \t]*;', src):
    print('thermal-export: thermal_message_dev 已是全局(幂等,跳过)')
else:
    want_msg = False
    print('WARN thermal-export: 找不到 thermal_message_dev'
          '(可能 CONFIG_QTI_THERMAL 未开)→ 只导出 thermal_class')

# ── 3) 追加 EXPORT_SYMBOL ─────────────────────────────────────────────────
add = []
if 'EXPORT_SYMBOL(thermal_class)' not in src:
    add.append('EXPORT_SYMBOL(thermal_class);')
if want_msg and 'EXPORT_SYMBOL(thermal_message_dev)' not in src:
    add.append('#ifdef CONFIG_QTI_THERMAL\n'
               'EXPORT_SYMBOL(thermal_message_dev);\n'
               '#endif /* CONFIG_QTI_THERMAL */')
if add:
    block = '\n' + MARK + '\n' + '\n'.join(add) + '\n'
    src = src.rstrip('\n') + '\n' + block
    print('thermal-export: 已追加导出语句(%s)'
          % ', '.join(['thermal_class'] + (['thermal_message_dev'] if want_msg else [])))
else:
    print('thermal-export: 导出语句已存在(幂等,未改动)')

if src != orig:
    open(path, 'w', encoding='utf-8').write(src)

# ── 4) 自检(失败即让构建失败,不要静默放过)──────────────────────────────
chk = open(path, encoding='utf-8', errors='ignore').read()
bad_class = re.search(r'(?m)^static[ \t]+struct[ \t]+class[ \t]+thermal_class', chk)
bad_msg = re.search(r'(?m)^static[ \t]+struct[ \t]+device[ \t]+thermal_message_dev', chk)
ok_class = ('EXPORT_SYMBOL(thermal_class)' in chk) and not bad_class
ok_msg = (not want_msg) or \
         (('EXPORT_SYMBOL(thermal_message_dev)' in chk) and not bad_msg)
if not (ok_class and ok_msg):
    print('::error:: thermal-export 自检失败: '
          'thermal_class=%s thermal_message_dev=%s' % (ok_class, ok_msg))
    raise SystemExit(1)

print('thermal-export: ✅ 完成 —— thermal_class=%s, thermal_message_dev=%s'
      % ('已导出' if ok_class else '未处理',
         '已导出' if (want_msg and ok_msg) else '未处理(跳过)'))
