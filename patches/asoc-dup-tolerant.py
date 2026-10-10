#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asoc-dup-tolerant.py <kernel_root> [--trace]
① 默认: 让 ASoC 容忍"重名控件"(-EBUSY), 与小米原厂树的行为对齐(见 §41.88/§41.90)。
   - sound/soc/soc-core.c : snd_soc_add_controls()      —— 普通控件
   - sound/soc/soc-dapm.c : widget 的 dapm kcontrol     —— DAPM 控件(v1 实测这才是第一处致命)
② --trace: 额外在 snd_soc_instantiate_card() 里**每个 `goto probe_end;` 之前**插一行
   `dev_err(card->dev, "MARS-TRACE line=%d ret=%d\\n", __LINE__, ret);`
   ⇒ 诊断内核刷入后 `dmesg | grep MARS-TRACE` 就能看到 -16 到底出自哪一步(不用开 DEBUG_FS)。
   两处改动都幂等(标记 MARS-ASOC-DUP-TOLERANT / MARS-TRACE)。
"""
import os
import re
import sys

MARK = 'MARS-ASOC-DUP-TOLERANT'
TMARK = 'MARS-TRACE'


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


def patch_trace(path):
    """把 snd_soc_instantiate_card() 里每个 `goto probe_end;` 换成:
        if (ret == -EBUSY) { 打点并容忍 } else { 打点并 goto probe_end; }
    用带花括号的复合语句替换, 在有花括号/无花括号的 if 上下文里都合法(C 的单语句规则)。
    ⇒ 一次编译同时做到: ①定位(-16 出自哪一步) ②修复(容忍该步的 -EBUSY 让卡片继续注册)。
    """
    src = open(path, encoding='utf-8', errors='surrogateescape').read()
    if TMARK in src:
        return 'skip(trace)'
    try:
        start = src.index('static int snd_soc_instantiate_card')
        end = src.index('probe_end:', start)
    except ValueError:
        return 'ERROR(func not found)'
    body = src[start:end]

    def repl(m):
        ind = m.group(1)
        return (ind + 'if (ret == -EBUSY) {\n'
                + ind + '\tdev_err(card->dev, "' + TMARK + '-TOLERATE line=%d ret=%d\\n", __LINE__, ret);\n'
                + ind + '} else {\n'
                + ind + '\tdev_err(card->dev, "' + TMARK + '-FAIL line=%d ret=%d\\n", __LINE__, ret);\n'
                + ind + '\tgoto probe_end;\n'
                + ind + '}')

    body2, n = re.subn(r'([ \t]*)goto probe_end;', repl, body)
    if n == 0:
        return 'ERROR(no goto probe_end)'
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(src[:start] + body2 + src[end:])
    return 'patched(trace+tolerate x%d)' % n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    root = args[0] if args else '.'
    do_trace = '--trace' in flags
    results = []
    for rel, fn in (('sound/soc/soc-core.c', patch_core), ('sound/soc/soc-dapm.c', patch_dapm)):
        p = os.path.join(root, rel)
        results.append('%s -> %s' % (rel, fn(p)) if os.path.exists(p) else '%s -> MISSING' % rel)
    if do_trace:
        p = os.path.join(root, 'sound/soc/soc-core.c')
        results.append('trace -> %s' % patch_trace(p))
    print('\n'.join(results))
    return 1 if any('ERROR' in r or 'MISSING' in r for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
