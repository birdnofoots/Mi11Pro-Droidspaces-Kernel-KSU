#!/usr/bin/env python3
"""让自编内核的 vermagic 与原厂一致 —— 这是「原厂 .ko 能装进来」的最后一块拼图。

★ 目标
  现在原厂 vendor 模块一个都装不进我们的内核,日志里全是
    "<module>: disagrees about version of symbol module_layout"
  两道闸:
    (1) vermagic 字符串必须逐字节相同;
    (2) 每个符号的 CRC 必须相同(Modversions)。
  原厂模块的 vermagic(TAKEOVER.md §36 抓到的)是:
    "5.4.233-qgki SMP preempt mod_unload modversions aarch64"
  我们的内核除了 "modversions" 这一节以外都一样(UTS_RELEASE=5.4.233-qgki ✓、
  SMP=y ✓、PREEMPT=y ✓、MODULE_UNLOAD=y ✓、aarch64 ✓)。

★ 做法
  1) 配置里关掉 CONFIG_MODVERSIONS ⇒ 内核【编译掉】符号 CRC 校验
     (kernel/module.c 里 check_version() 整段是 #ifdef CONFIG_MODVERSIONS)。
     于是闸门 (2) 直接消失 —— 原厂模块的 __versions 段会被忽略。
     这一步不用改源码:见 CI 里写 star_droidspaces.config 的地方 / patches/m2y.py。
  2) 但模块自己的 vermagic 里带 "modversions " ⇒ 内核这边也必须带,
     否则 loader 连门都不让进。本补丁就是把 MODULE_VERMAGIC_MODVERSIONS
     从"跟着 CONFIG_MODVERSIONS 走"改成【无条件带 "modversions "】。

★ 附带前提(已核对)
  * 原厂配置里【没有】CONFIG_MODULE_SIG* ⇒ 没有签名校验 ⇒ 原厂未签名/异签模块不会被拒。
  * 我们 Kconfig 里 MODULE_UNLOAD / PREEMPT / SMP 与原厂一致(已逐项 diff)。
"""
import sys

P = 'include/linux/vermagic.h'
OLD = '''#ifdef CONFIG_MODVERSIONS
#define MODULE_VERMAGIC_MODVERSIONS "modversions "
#else
#define MODULE_VERMAGIC_MODVERSIONS ""
#endif'''

NEW = '''/*
 * ★ mars 补丁:无条件带 "modversions " 字样。
 *   我们故意用 CONFIG_MODVERSIONS=n 来跳过符号 CRC 校验(原厂 .ko 的 CRC 与
 *   我们的内核只有 37% 匹配,校验一开它们就全装不进来),但原厂模块的 vermagic
 *   里带 "modversions " ⇒ 内核这边也必须带同样的字样,否则 loader 直接拒收。
 *   详见 patches/vermagic.py。
 */
#define MODULE_VERMAGIC_MODVERSIONS "modversions "'''

s = open(P).read()
if NEW in s:
    print('  [跳过] vermagic 补丁已存在')
    sys.exit(0)
if OLD not in s:
    print('  [失败] %s 里找不到锚点' % P)
    sys.exit(1)
open(P, 'w').write(s.replace(OLD, NEW, 1))
print('  [ok] %s: MODULE_VERMAGIC_MODVERSIONS 无条件为 "modversions "' % P)
