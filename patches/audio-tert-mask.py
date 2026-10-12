#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audio-tert-mask.py —— ★TERT_TDM_RX 扬声器链路屏蔽(los96 备选)★
=====================================================================================
背景(2026-10-12 §O/§O2): TERT_TDM_RX_0/1(mars 双 CS35L41 功放) 一旦有 PCM 流打开
(DAPM 上电功放) 即 <0.5s 硬复位(零日志), 静音波形同样死 ⇒ 与内容无关, 死在功放上电。
在同源 cs35l41(los95) 仍修不好时的保底: 让扬声器 BE 不可播放 ⇒ 任何播放尝试
快速失败 "no backend DAIs enabled"(tinyplay 实测该失败是干净、瞬时、无副作用),
音频栈照常运行 ⇒ system_server 健康 / FUSE 正常 / 文件管理器正常 / 可日用。
(耳机/其它 BE 不受影响; 出声验收④只能走耳机 WCD938x 路径。)

手法: 把 `lahaina.c` 里 TERT_TDM_RX_0/1 的 BE dailink 条目 `.dpcm_playback = 1`
改成 0 —— 单字段手术, 卡注册/其它链路/编号表全部不动。
所有出现处都改(机器表有多个变体数组, 每个都含 TERT 条目)。

用法: python3 audio-tert-mask.py <kernel 目录>
"""
import os
import re
import sys

MARK = 'MARS-tert-mask'

# 条目: .name = LPASS_BE_TERT_TDM_RX_0/1, ... .dpcm_playback = 1,
PAT = re.compile(
    r'(\.name\s*=\s*LPASS_BE_TERT_TDM_RX_[01],.*?\.dpcm_playback\s*=\s*)1',
    re.S)


def patch(root):
    path = os.path.join(root, 'techpack/audio/asoc/lahaina.c')
    if not os.path.isfile(path):
        raise RuntimeError('缺少 ' + path)
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        src = f.read()
    if MARK in src:
        return 'lahaina.c: already patched'
    hits = []

    def repl(m):
        hits.append(m.group(0)[:60])
        return m.group(1) + '0  /* %s 屏蔽扬声器播放方向 */' % MARK

    src2 = PAT.sub(repl, src)
    if not hits:
        raise RuntimeError('lahaina.c: 未找到 TERT_TDM_RX 的 dpcm_playback 锚点')
    with open(path, 'w', encoding='utf-8', errors='replace') as f:
        f.write(src2)
    return 'lahaina.c: %d 处 TERT_TDM_RX dpcm_playback 1->0 (%s)' % (
        len(hits), '; '.join(h[:40] for h in hits[:2]))


def main():
    roots = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not roots:
        print('用法: audio-tert-mask.py <kernel 目录>')
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
