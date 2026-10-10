#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asoc-dup-tolerant.py <kernel_root>
让 ASoC 容忍"重名控件"(-EBUSY), 与小米原厂树的行为对齐。

背景(2026-10-11 真机取证):
  我们内核上声卡注册失败: `ASoC: failed to register soundcard -16`。
  原厂(GOLD 5.4.233)dmesg 里**同样**有
    `control 2:0:0:MultiMedia1 Mixer USB_AUDIO_TX:0 is already present`
    `msm-pcm-routing: ASoC: failed to add widget ... dapm kcontrol ...: -16`
  但原厂 9.58s **照样** `Sound card lahaina-mtp-snd-card registered`
  ⇒ 同一个 -EBUSY, 原厂只当噪声, LOS 5.4.242 却把它上抛成致命。

本补丁两处(each 幂等, 标记 MARS-ASOC-DUP-TOLERANT):
  1. sound/soc/soc-core.c:  snd_soc_add_controls()      —— 普通控件
  2. sound/soc/soc-dapm.c:  添加 widget 的 dapm kcontrol —— DAPM 控件(实测这才是致命那处)
只在 err == -EBUSY 时跳过该控件并继续, 其它错误照旧上抛。
"""
import os
import re
import sys

MARK = 'MARS-ASOC-DUP-TOLERANT'


def patch_core(path):
    src = open(path, encoding='utf-8', errors='surrogateescape').read()
    if MARK in src:
        return 'skip(core)'
    pat = re.compile(
        r'(err = snd_ctl_add\(card, snd_soc_cnew\(control, data,\s*\n'
        r'\s*control->name, prefix\)\);\s*\n'
        r'\s*if \(err < 0\) \{\s*\n'
        r'\s*dev_err\(dev, "ASoC: Failed to add %s: %d\\n",\s*\n'
        r'\s*control->name, err\);\s*\n)'
        r'(\s*)(return err;)')
    m = pat.search(src)
    if not m:
        return 'ERROR(pattern not found)'
    ind = m.group(2)
    ins = (ind + '/* ' + MARK + ': 与小米原厂行为对齐 —— 重名控件(-EBUSY)只警告不致命 */\n'
           + ind + 'if (err == -EBUSY)\n'
           + ind + '\tcontinue;\n')
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(src[:m.start(2)] + ins + src[m.start(2):])
    return 'patched(core)'


def patch_dapm(path):
    src = open(path, encoding='utf-8', errors='surrogateescape').read()
    if MARK in src:
        return 'skip(dapm)'
    pat = re.compile(
        r'(\t\tret = snd_ctl_add\(card, kcontrol\);\n'
        r'\t\tif \(ret < 0\) \{\n'
        r'\t\t\tdev_err\(dapm->dev,\n'
        r'\t\t\t\t"ASoC: failed to add widget %s dapm kcontrol %s: %d\\n",\n'
        r'\t\t\t\tw->name, name, ret\);\n)'
        r'(\t\t\t)(goto exit_free;)')
    m = pat.search(src)
    if not m:
        return 'ERROR(pattern not found)'
    ins = ('\t\t\t/* ' + MARK + ': 与小米原厂行为对齐 —— 重名 DAPM 控件(-EBUSY)\n'
           '\t\t\t * (例 "MultiMedia1 Mixer USB_AUDIO_TX")只警告并跳过, 否则整张声卡 -16 注册失败。\n'
           '\t\t\t */\n'
           '\t\t\tif (ret == -EBUSY) {\n'
           '\t\t\t\tsnd_ctl_free_one(kcontrol);\n'
           '\t\t\t\tret = 0;\n'
           '\t\t\t\tcontinue;\n'
           '\t\t\t}\n')
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(src[:m.start(2)] + ins + src[m.start(2):])
    return 'patched(dapm)'


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    results = []
    for rel, fn in (('sound/soc/soc-core.c', patch_core), ('sound/soc/soc-dapm.c', patch_dapm)):
        p = os.path.join(root, rel)
        results.append('%s -> %s' % (rel, fn(p)) if os.path.exists(p) else '%s -> MISSING' % rel)
    print('\n'.join(results))
    return 1 if any('ERROR' in r or 'MISSING' in r for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
