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
    """soc-dapm.c: 给 widget 加 DAPM kcontrol 时容忍重名(-EBUSY)。
    注意: 该处不是循环(是"只建一个控件"的辅助函数), **不能用 continue**,
    正确做法是释放控件、ret=0、按成功返回, 让声卡继续注册。
    """
    src = open(path, encoding='utf-8', errors='surrogateescape').read()
    if MARK in src:
        return 'skip(dapm)'
    pat = re.compile(
        r'(\t\tret = snd_ctl_add\(card, kcontrol\);\n'
        r'\t\tif \(ret < 0\) \{\n'
        r'\t\t\tdev_err\(dapm->dev,\n'
        r'\t\t\t\t"ASoC: failed to add widget %s dapm kcontrol %s: %d\\n",\n'
        r'\t\t\t\tw->name, name, ret\);\n)'
        r'(\t\t\tgoto exit_free;)')
    m = pat.search(src)
    if not m:
        return 'ERROR(pattern not found)'
    ins = ('\t\t\t/* ' + MARK + ': 与小米原厂行为对齐 —— 重名 DAPM 控件(-EBUSY)\n'
           '\t\t\t * (例 "MultiMedia1 Mixer USB_AUDIO_TX")容忍: 释放该控件并按成功返回,\n'
           '\t\t\t * 否则整张声卡会以 -16 注册失败(实测)。此处不在循环里, 不能用 continue。\n'
           '\t\t\t */\n'
           '\t\t\tif (ret == -EBUSY) {\n'
           '\t\t\t\tsnd_ctl_free_one(kcontrol);\n'
           '\t\t\t\tret = 0;\n'
           '\t\t\t}\n')
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(src[:m.start(2)] + ins + src[m.start(2):])
    return 'patched(dapm)'


def patch_trace(path):
    """纯打点(不改控制流): 把每个 `goto probe_end;` 替换成
        { dev_err(card->dev, "MARS-TRACE line=%d ret=%d\n", __LINE__, ret); goto probe_end; }
    用**裸复合语句块**包裹 ⇒ 在有花括号/无花括号的 if 上下文里都合法(C 单语句规则),
    且不改变任何控制流(只多一行日志) ⇒ 不会像 los67 的"跳过式容忍"那样把内核搞挂。
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
        return (ind + '{\n'
                + ind + '\tdev_err(card->dev, "' + TMARK + ' line=%d ret=%d\\n", __LINE__, ret);\n'
                + ind + '\tgoto probe_end;\n'
                + ind + '}')

    body2, n = re.subn(r'([ \t]*)goto probe_end;', repl, body)
    if n == 0:
        return 'ERROR(no goto probe_end)'
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(src[:start] + body2 + src[end:])
    return 'patched(trace-only x%d)' % n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    root = args[0] if args else '.'
    do_trace = '--trace' in flags
    results = []
    pairs = [('sound/soc/soc-core.c', patch_core)]
    # 注意: --trace 模式下**不打** dapm 的"跳过式容忍"补丁 —— 2026-10-11 los67 实测它会硬挂内核
    # (跳过 kcontrol 后 w->kcontrols[kci] 为 NULL, 后续 DAPM 解引用 ⇒ panic)。纯日志模式只需 soc-core。
    if not do_trace:
        pairs.append(('sound/soc/soc-dapm.c', patch_dapm))
    for rel, fn in pairs:
        p = os.path.join(root, rel)
        results.append('%s -> %s' % (rel, fn(p)) if os.path.exists(p) else '%s -> MISSING' % rel)
    if do_trace:
        p = os.path.join(root, 'sound/soc/soc-core.c')
        results.append('trace -> %s' % patch_trace(p))
    print('\n'.join(results))
    return 1 if any('ERROR' in r or 'MISSING' in r for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
