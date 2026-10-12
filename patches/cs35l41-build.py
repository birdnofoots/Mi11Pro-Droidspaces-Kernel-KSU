#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cs35l41-build.py —— 让 LOS 树里的 `techpack/audio/asoc/codecs/cs35l41` 编入产物。

背景（2026-10-11 §41.108 / 收尾⑲）：
  带声卡的开机会卡死，真凶是**原厂 `cs35l41` 功放驱动无限刷 DSP 日志**
  （`cs35l41 1-0042: DSP1: Algorithm ID: …` 几十万行）。
  我们产物里完全没有 cs35l41（`strings Image | grep -ci cs35l41` = 0），
  手机上跑的是原厂 5.4.233 的 `cs35l41_dlkm.ko`（ABI 与我们 5.4.242 头文件不一致，
  `MARS-USEID … name="?" base=-34` 就是 struct 读数错位的实锤）。

为什么树里有源码却没编出来：
  `techpack/audio/asoc/codecs/Kbuild:282` 把 cs35l41 关在 TARGET_PRODUCT 门后：
      ifneq (,$(filter $(TARGET_PRODUCT), venus star mars haydn odin vili))
          obj-y += cs35l41/
      endif
  内核独立编译时 TARGET_PRODUCT 从未设置 ⇒ 子目录根本没被 descend。

  即便 descend，`cs35l41/Kbuild` 的 CDEFINES 里也没有
  `CONFIG_TARGET_PRODUCT_CS35L41_TDM`（mars 走 TDM/DSP_A + 8*rate*width 时钟，
  而不是 I2S 的 2*rate*width）—— 少了它驱动会按 I2S 初始化，功放照样跑飞。

本补丁做三件事（只改构建门 + 编译宏，零控制流）：
  1. `codecs/Kbuild`：无条件 `obj-y += cs35l41/`（去掉 TARGET_PRODUCT 门）。
  2. `cs35l41/Kbuild`：CDEFINES 追加 `-DCONFIG_TARGET_PRODUCT_CS35L41_TDM
     -DCONFIG_TARGET_PRODUCT_STAR`（mars 是 star 血统，VPBR/时钟/DAI 名都走这支）；
     并把 obj 行写死 obj-y（显式对象列表，复用原 Kbuild 的 *_dlkm-y 列表）。
  3. `config/lahainaauto.conf`：`CONFIG_SND_SOC_CS35L41=y`、`CONFIG_SND_EVENT=y`。
     选 `=y`（内建）：内建驱动开机即在，原厂 `cs35l41_dlkm.ko` 再 load 会因
     driver already registered 被拒 ⇒ 自然抢占；不依赖运行时时序。
     `CONFIG_SND_EVENT=y` 是硬依赖：`cs35l41_i2c_probe` 里
     `snd_event_client_register()` 失败会直接 return rc，功放 probe 不了。

★ 2026-10-12 血泪教训（run 110 失败根因，务必记住）：
  Kbuild 是 **Makefile 语法**，绝不能注入 C 注释 `/* ... */`！
  带冒号的 `/* MARK: xxx */` 会被 make 解析成规则目标 ⇒
  `Kbuild:111: *** multiple target patterns.  Stop.` ⇒ 子目录整个不编译 ⇒ Image 零痕迹。
  本版所有注入注释一律 `#` 开头（make 注释）。

产物预期：
  · vmlinux / Image 里出现 cs35l41 符号（`strings Image | grep -ci cs35l41` > 0）；
  · 原厂 cs35l41_dlkm.ko 装不上（dmesg 有 duplicate/already registered）；
  · 验收四条见 docs/mars-NEXT-HANDOVER.md §0.5。

用法：python3 cs35l41-build.py <kernel 目录>
"""
import os
import re
import sys

MARK = 'MARS-CS35L41-BUILD'


def _patch_codecs_kbuild(path):
    """把 TARGET_PRODUCT 门换成无条件 obj-y += cs35l41/。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()
    if MARK in src:
        return 'codecs/Kbuild: already patched'
    pat = re.compile(
        r'ifneq\s*\(\s*,\s*\$\(filter\s+\$\(TARGET_PRODUCT\),[^)]*\)\s*\)\s*\n'
        r'([ \t]*obj-y\s*\+=\s*cs35l41/\s*\n)'
        r'\s*endif',
        re.M,
    )
    m = pat.search(src)
    if not m:
        # 也许它已经无条件了（被之前的补丁打过）
        if re.search(r'^\s*obj-\w\s*\+=\s*cs35l41/', src, re.M):
            return 'codecs/Kbuild: cs35l41 已无条件包含'
        raise RuntimeError('codecs/Kbuild: 未找到 cs35l41 的 TARGET_PRODUCT 门，无法打补丁')
    # ⚠️ 只能用 make 注释 '#'（'/* */' 里的冒号会让 make 报 multiple target patterns）
    repl = (
        '# %s 无条件编入 cs35l41 mars 功放 同源替换原厂 5.4.233 模块\n'
        'obj-y\t+= cs35l41/' % MARK
    )
    src2 = src[:m.start()] + repl + src[m.end():]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src2)
    return 'codecs/Kbuild: TARGET_PRODUCT 门已拆除'


def _grab_objs(src, suffix):
    """从原 Kbuild 抓 `xxx := objs...` / `+= objs...` 的对象列表（复用，防止漏文件）。"""
    objs = []
    for m in re.finditer(r'^\s*[\w./-]*%s[\w-]*\s*[:+]?=\s*(.+?)\s*$' % re.escape(suffix),
                         src, re.M):
        for tok in m.group(1).split():
            if tok.endswith('.o') and tok not in objs:
                objs.append(tok)
    return objs


def _patch_cs35l41_kbuild(path):
    """给 cs35l41/Kbuild 加 TDM 编译宏, 并把 obj 行写死成 obj-y（显式对象列表）。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()
    if MARK in src:
        return 'cs35l41/Kbuild: already patched'
    needle = 'CDEFINES += -DCONFIG_AUDIO_SMARTPA_STEREO'
    if needle not in src:
        raise RuntimeError('cs35l41/Kbuild: 未找到 CDEFINES 锚点')
    ins = (
        needle + '\n'
        + 'CDEFINES += -DCONFIG_TARGET_PRODUCT_CS35L41_TDM  # %s mars TDM DSP_A\n' % MARK
        + 'CDEFINES += -DCONFIG_TARGET_PRODUCT_STAR  # %s star 血统 VPBR DAI 名' % MARK
    )
    src = src.replace(needle, ins, 1)

    # 复用原有对象列表（cs35l41_dlkm-y / cs35l41-y 等），没有才用默认
    objs = _grab_objs(src, '_dlkm-y') or _grab_objs(src, '-y')
    objs = [o for o in objs if 'cs35l41' in o or 'wm_adsp' in o or 'dsp' in o]
    if not objs:
        objs = ['cs35l41.o', 'cs35l41-i2c.o', 'cs35l41-tables.o', 'wm_adsp.o']
    objline = ' '.join(objs)

    # 注释掉原有的 obj-$(CONFIG ...) 行与 *_dlkm-y 行, 避免重复定义
    src = re.sub(
        r'^(\s*)obj-\$\(CONFIG_SND_SOC_CS35L41\)\s*\+=\s*\S+\.o\s*$',
        r'\1# \g<0>  # %s 见下方强制 obj-y' % MARK,
        src, count=1, flags=re.M)
    src = re.sub(
        r'^(\s*)(?:cs35l41_dlkm-y|cs35l41-y)\s*[:+]?=.*$',
        r'\1# \g<0>  # %s' % MARK,
        src, count=1, flags=re.M)

    forced = (
        '\n# %s 强制内建 los89 教训 CONFIG export 进不了深层 kbuild\n' % MARK
        + 'CS35L41_OBJS := %s\n' % objline
        + 'obj-y += cs35l41_dlkm.o\n'
        + 'cs35l41_dlkm-y := $(CS35L41_OBJS)\n'
    )
    src = src.rstrip() + '\n' + forced
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    return 'cs35l41/Kbuild: TDM 宏 + 强制 obj-y 内建 objs=[%s]' % objline


def _patch_snd_event_kbuild(path):
    """snd_event 是 cs35l41_probe 的硬依赖, 同样强制内建。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()
    if MARK in src:
        return 'soc/Kbuild: already patched'
    objs = _grab_objs(src, 'snd_event_dlkm-y') or ['snd_event.o']
    objline = ' '.join(objs)
    src = re.sub(
        r'^(\s*)obj-\$\(CONFIG_SND_EVENT\)\s*\+=\s*\S+\.o\s*$',
        r'\1# \g<0>  # %s 见下方强制 obj-y' % MARK,
        src, count=1, flags=re.M)
    src = re.sub(
        r'^(\s*)snd_event_dlkm-y\s*[:+]?=.*$',
        r'\1# \g<0>  # %s' % MARK,
        src, count=1, flags=re.M)
    forced = (
        '\n# %s snd_event 强制内建 cs35l41_probe 依赖 snd_event_client_register\n' % MARK
        + 'SND_EVENT_OBJS := %s\n' % objline
        + 'obj-y += snd_event_dlkm.o\n'
        + 'snd_event_dlkm-y := $(SND_EVENT_OBJS)\n'
    )
    src = src.rstrip() + '\n' + forced
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    return 'soc/Kbuild: snd_event 强制 obj-y 内建 objs=[%s]' % objline


def _patch_lahaina_conf(path):
    """CONFIG_SND_SOC_CS35L41=y / CONFIG_SND_EVENT=y（尽力 export; 真正生效靠 Kbuild 强制）。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()
    if MARK in src:
        return 'lahainaauto.conf: already patched'
    src2, n1 = re.subn(
        r'^export CONFIG_SND_SOC_CS35L41=.*$',
        'export CONFIG_SND_SOC_CS35L41=y  # %s' % MARK,
        src, count=1, flags=re.M)
    # SND_EVENT 保持原样(=m): los95 教训 —— 绝不内建 snd_event(见 patch())
    if n1 != 1 and 'CONFIG_SND_SOC_CS35L41' not in src2:
        src2 += '\nexport CONFIG_SND_SOC_CS35L41=y  # %s\n' % MARK
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src2)
    return 'lahainaauto.conf: CS35L41=y (SND_EVENT 保持 =m)'


def _patch_cs35l41_i2c(root):
    """cs35l41-i2c.c 打桩 snd_event 调用(los96 关键): 
    内建 cs35l41 原本硬链 snd_event_client_register ⇒ 被迫连带内建 snd_event ⇒
    原厂 snd_event_dlkm 装载败 ⇒ apr(q6_notifier,snd_event)→q6→platform→machine
    依赖链雪崩 ⇒ 无声卡(los95 实测)。打桩后 cs35l41 内建零 snd_event 引用 ⇒
    原厂 snd_event_dlkm 正常装载 ⇒ 链完整 ⇒ machine 装卡并按名绑定我们的 TDM 安全驱动。
    代价: 失去 PA SSR(子系统重启)恢复 —— 无 SSR 场景可接受。"""
    path = os.path.join(root, 'techpack/audio/asoc/codecs/cs35l41/cs35l41-i2c.c')
    if not os.path.isfile(path):
        raise RuntimeError('缺少 ' + path)
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()
    if MARK in src:
        return 'cs35l41-i2c.c: already patched'
    subs = [
        ('rc = snd_event_client_register(cs35l41->dev, &cs35l41_ssr_ops, NULL);',
         'rc = 0;  /* %s snd_event 桩(SSR 恢复弃用) */' % MARK),
        ('snd_event_notify(cs35l41->dev, SND_EVENT_UP);',
         '/* %s snd_event 桩 */ (void)0;' % MARK),
        ('snd_event_client_deregister(cs35l41->dev);',
         '/* %s snd_event 桩 */ (void)0;' % MARK),
    ]
    n = 0
    for old, new in subs:
        if old in src:
            src = src.replace(old, new, 1)
            n += 1
        else:
            raise RuntimeError('cs35l41-i2c.c: 未命中桩点: ' + old[:50])
    with open(path, 'w', encoding='utf-8', errors='replace') as f:
        f.write(src)
    return 'cs35l41-i2c.c: snd_event 3 处桩完成'



def patch(root):
    msgs = []
    p = os.path.join(root, 'techpack/audio/asoc/codecs/Kbuild')
    if not os.path.isfile(p):
        raise RuntimeError('缺少 ' + p)
    msgs.append(_patch_codecs_kbuild(p))

    p = os.path.join(root, 'techpack/audio/asoc/codecs/cs35l41/Kbuild')
    if not os.path.isfile(p):
        raise RuntimeError('缺少 ' + p)
    msgs.append(_patch_cs35l41_kbuild(p))

    p = os.path.join(root, 'techpack/audio/asoc/codecs/cs35l41')
    msgs.append(_patch_cs35l41_i2c(root))

    # ★los95 血泪(2026-10-12): 绝不内建 snd_event!
    # 原厂 machine_dlkm/apr_dlkm 的 modinfo depends=snd_event_dlkm(按模块名解析);
    # 内建占名 ⇒ 原厂 snd_event_dlkm 装载败 ⇒ apr→q6→native→platform→machine 依赖链雪崩
    # ⇒ 机器驱动不注册 ⇒ 无声卡(los95 实测)。cs35l41 内建无此问题(无人依赖 cs35l41_dlkm,
    # 功放是 ASoC 动态按名绑定 "cs35l41.1-0040"/"1-0042")。⇒ soc/Kbuild 不动, snd_event 用原厂。

    p = os.path.join(root, 'techpack/audio/config/lahainaauto.conf')
    if not os.path.isfile(p):
        raise RuntimeError('缺少 ' + p)
    msgs.append(_patch_lahaina_conf(p))
    return ' | '.join(msgs)


def main():
    roots = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not roots:
        print('用法: cs35l41-build.py <kernel 目录>')
        return 2
    rc = 0
    for r in roots:
        try:
            print('%s -> %s' % (r, patch(r)))
        except Exception as e:
            print('%s -> ERROR: %s' % (r, e))
            rc = 1
    return rc


if __name__ == '__main__':
    sys.exit(main())
