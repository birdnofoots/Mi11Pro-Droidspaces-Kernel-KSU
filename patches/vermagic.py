#!/usr/bin/env python3
"""把自编内核的 VERMAGIC_STRING 硬编码成【原厂模块期望的那个字符串】。

★ 铁证(2026-10-02,来自我们内核那轮启动日志 sda59):
    qmi_helpers: version magic
      '5.4.233-gbb70cde46897 SMP preempt mod_unload modversions aarch64'
      should be
      '5.4.233-qgki SMP preempt mod_unload modversions aarch64'
    hwid: version magic '5.4.233-qgki-gbb70cde46897 ...' should be '5.4.233-qgki ...'
    rmnet_ctl: 同上
  ⇒ 原厂 .ko 全部因为 vermagic 不一致被拒收。
    (注意:TAKEOVER.md §36 里记的"原厂模块 vermagic 是 -qgki"是【错的】;
     实测原厂模块要的是 5.4.233-gbb70cde46897,而 -qgki 是我们自己的。)

★ 配套(缺一不可):
  1) 配置里关掉 CONFIG_MODVERSIONS ⇒ 内核编译掉符号 CRC 校验(check_version());
  2) 本补丁把 VERMAGIC_STRING 写死成原厂那串 ⇒ 通过 vermagic 检查;
  3) 原厂配置里没有 CONFIG_MODULE_SIG* ⇒ 没有签名校验。
  ⇒ 原厂 vendor 模块(wlan/qti_battery_charger_main/音频 codec/相机/触摸…)
    就能加载进自编内核 —— 这是"让手机真正可用"的关键一步。

★ 这只影响模块校验串,不影响 `uname -r`(那个来自 UTS_RELEASE)。
"""
import sys

P = 'include/linux/vermagic.h'
STOCK = '5.4.233-gbb70cde46897 SMP preempt mod_unload modversions aarch64'
BLOCK = (
    '\n/*\n'
    ' * ★ mars 补丁:见 patches/vermagic.py 顶部注释。\n'
    ' *   把模块校验串硬编码成原厂模块期望的值(实测),否则原厂 .ko 全部被拒收。\n'
    ' */\n'
    '#undef VERMAGIC_STRING\n'
    '#define VERMAGIC_STRING "%s"\n' % STOCK
)

try:
    s = open(P).read()
except OSError:
    print('  [失败] 找不到 %s' % P)
    sys.exit(1)

if STOCK in s and 'mars 补丁' in s:
    print('  [跳过] vermagic 补丁已存在')
    sys.exit(0)

open(P, 'a').write(BLOCK)
print('  [ok] %s: VERMAGIC_STRING 硬编码为原厂串' % P)
print('       %s' % STOCK)
