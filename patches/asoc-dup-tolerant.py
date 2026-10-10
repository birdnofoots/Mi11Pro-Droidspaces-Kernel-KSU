#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asoc-dup-tolerant.py <kernel_root>
让 ASoC 容忍"重名控件"(-EBUSY), 与小米原厂树的行为对齐。

背景(2026-10-11 真机取证):
  我们内核上声卡注册失败: `ASoC: failed to register soundcard -16` /
  `msm_asoc_machine_probe: snd_soc_register_card failed (-16)`。
  而原厂(GOLD, 5.4.233)dmesg 里**同样**有
  `control 2:0:0:MultiMedia1 Mixer USB_AUDIO_TX:0 is already present` +
  `msm-pcm-routing: ASoC: failed to add widget ... : -16`,
  但原厂 9.58s **照样** `Sound card lahaina-mtp-snd-card registered`。
  ⇒ 同一个 -EBUSY, 原厂只当噪声, LOS 5.4.242 的 ASoC 却把它上抛成致命
    (snd_soc_instantiate_card → snd_soc_add_card_controls → snd_soc_add_controls → return err)。
  本补丁: 仅在 `snd_soc_add_controls()` 里把 `-EBUSY` 记为警告并继续, 其它错误照旧上抛。
"""
import os
import re
import sys


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    path = os.path.join(root, 'sound/soc/soc-core.c')
    if not os.path.exists(path):
        print('ERROR: 找不到 %s' % path)
        return 1
    src = open(path, encoding='utf-8', errors='surrogateescape').read()
    if 'MARS-ASOC-DUP-TOLERANT' in src:
        print('already patched, skip')
        return 0
    pat = re.compile(
        r'(err = snd_ctl_add\(card, snd_soc_cnew\(control, data,\s*\n'
        r'\s*control->name, prefix\)\);\s*\n'
        r'\s*if \(err < 0\) \{\s*\n'
        r'\s*dev_err\(dev, "ASoC: Failed to add %s: %d\\n",\s*\n'
        r'\s*control->name, err\);\s*\n)'
        r'(\s*)(return err;)')
    m = pat.search(src)
    if not m:
        print('ERROR: 未匹配到 snd_soc_add_controls 里的错误处理, 请人工核对')
        return 1
    indent = m.group(2)
    ins = (indent + '/* MARS-ASOC-DUP-TOLERANT: 与小米原厂行为对齐 —— 重名控件(-EBUSY)\n'
           + indent + ' * (例 "MultiMedia1 Mixer USB_AUDIO_TX")只警告不致命, 否则声卡注册 -16。\n'
           + indent + ' */\n'
           + indent + 'if (err == -EBUSY)\n'
           + indent + '\tcontinue;\n')
    out = src[:m.start(2)] + ins + src[m.start(2):]
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(out)
    print('patched: %s (inserted %d bytes)' % (path, len(ins)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
