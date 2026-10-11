#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asoc-pcm-stockmap.py —— ★PCM 编号总修复★（取代 numid-fix/renum 全套）
=========================================================================================
2026-10-12 定论（本补丁取代 asoc-pcm-numid-fix.py + renum 路线）
=========================================================================================
事实链:
1. 原厂 machine_dlkm.ko 的 dai_link 表【同样没给】 AFE-PROXY RX/TX 写 .id(=0),
   所以"原厂靠 .id 编号"不成立(二进制解析实锤)。
2. LOS 源里每条 link 都有 {/* hw:x,N */} 注释 = 原厂 PCM 设备号真值。
   对照表序可证: **原厂编号 = 纯 rtd->num(表顺序)**, id 根本没参与
   (VoiceMMode1 id=50 但原厂号=2; Compress2 id=6 但原厂号=11; MM10/Compress3
   的 id 还都是 9 ⇒ num=id 必撞)。
3. soc-core 的 use_dai_pcm_id 覆盖路径(num=id / num+=be_pcm_base)在原厂
   **从不触发**(stub 源码 msm_dai_stub_component 只写 .name, 两字段=0)。
   但它在我们内核上会触发: 原厂 5.4.233 模块的 component_driver 在 5.4.242
   内核里被读出垃圾值(los78 实测 stub use_dai_pcm_id=1、cs35l41 be_pcm_base=-34)
   ⇒ FE 抢 device 0、BE 号算歪 ⇒ 撞号 ⇒ snd_card_register -16 ⇒ 无声/半残。
⇒ 修法(一步到位):
   ① 一律以 rtd->num 为基(=原厂真实行为);
   ② 按原厂基准表(mars-stock-map.txt, stream_name→设备号)精确归位;
   ③ 唯一性兜底: 号被占/未收录 ⇒ 200+rtd 高位号(互斥变体 32/33/44/45 也靠它)。
   ⇒ 与原厂编号逐条一致 ⇒ HAL(AudioFlinger/MIUI 音频策略)按原厂号开 PCM 不再崩
     (los82 实证"HAL 依赖原厂编号")。
=========================================================================================
"""
import os
import re
import sys

MARK = 'MARS-STOCKNUM'
HERE = os.path.dirname(os.path.abspath(__file__))
MAP_FILE = os.path.join(HERE, 'mars-stock-map.txt')

# soc-core.c soc_link_init() 里编号那段的原文(从 "num = rtd->num;" 到 compress_new 之前)
BLOCK_RE = re.compile(
    r"(\tnum = rtd->num;\n)"
    r"(.*?)"
    r"(\t/\* create compress_device if possible \*/\n)",
    re.S)


def load_map():
    m = []
    if not os.path.exists(MAP_FILE):
        return m
    for ln in open(MAP_FILE, encoding='utf-8'):
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        parts = ln.split()
        if len(parts) >= 2 and parts[-1].lstrip('-').isdigit():
            m.append((ln[:ln.rfind(parts[-1])].strip(), int(parts[-1])))
    return m


def build_block(pairs):
    rows = "\n".join('\t\t\t{ "%s", %d },' % (s.replace('"', '\\"'), n) for s, n in pairs)
    return (
        "\tnum = rtd->num;\n"
        "\n"
        "\t/* MARS-STOCKNUM: 原厂 5.4.233 模块在本内核上, use_dai_pcm_id/be_pcm_base\n"
        "\t * 读出的是结构错位垃圾(stub=1、cs35l41=-34, los78 实测), 会让 PCM 号算歪\n"
        "\t * 撞号(snd_card_register -16)。原厂真实行为 = 纯 rtd->num(lahaina.c 的\n"
        "\t * hw:x,N 注释与表序吻合)。这里: ①一律 rtd->num 为基; ②按原厂基准表归位;\n"
        "\t * ③唯一性兜底(互斥变体同号/未收录 ⇒ 200+rtd)。 */\n"
        "\t{\n"
        "\t\tstatic const struct { const char *sname; int dnum; } mars_stock_pcm_map[] = {\n"
        + rows + "\n"
        "\t\t};\n"
        "\t\tstatic DECLARE_BITMAP(mars_pcm_taken, 512);\n"
        "\t\tunsigned int __mi;\n"
        "\t\tint __want = -1;\n"
        "\n"
        "\t\tfor (__mi = 0; __mi < ARRAY_SIZE(mars_stock_pcm_map); __mi++) {\n"
        "\t\t\tif (dai_link->stream_name &&\n"
        "\t\t\t    !strcmp(dai_link->stream_name,\n"
        "\t\t\t\t   mars_stock_pcm_map[__mi].sname)) {\n"
        "\t\t\t\t__want = mars_stock_pcm_map[__mi].dnum;\n"
        "\t\t\t\tbreak;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tif (__want >= 0 && __want < 512 &&\n"
        "\t\t    !test_and_set_bit(__want, mars_pcm_taken)) {\n"
        "\t\t\tnum = __want;\n"
        "\t\t} else {\n"
        "\t\t\tnum = 200 + rtd->num;\n"
        "\t\t\tif (num < 512)\n"
        "\t\t\t\tset_bit(num, mars_pcm_taken);\n"
        "\t\t\tdev_info(card->dev,\n"
        "\t\t\t\t \"MARS-STOCKNUM: %s stock#%d 占用/未收录 ⇒ dev %d\\n\",\n"
        "\t\t\t\t dai_link->stream_name ? dai_link->stream_name : \"(null)\",\n"
        "\t\t\t\t __want, num);\n"
        "\t\t}\n"
        "\t}\n"
        "\n")


def patch(root):
    p = os.path.join(root, 'sound/soc/soc-core.c')
    if not os.path.exists(p):
        return 'soc-core.c MISSING'
    s = open(p, encoding='utf-8', errors='surrogateescape').read()
    if MARK in s:
        return 'skip(已打过)'
    pairs = load_map()
    if not pairs:
        return 'MAP-EMPTY(基准表为空, 不打补丁)'
    m = BLOCK_RE.search(s)
    if not m:
        return 'ANCHOR-MISS'
    s = s[:m.start()] + build_block(pairs) + m.group(3) + s[m.end():]
    open(p, 'w', encoding='utf-8', errors='surrogateescape').write(s)
    return 'patched(soc-core.c stocknum, map=%d 条)' % len(pairs)


def main():
    roots = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not roots:
        print('用法: asoc-pcm-stockmap.py <kernel 目录>')
        return 2
    for r in roots:
        print('%s -> %s' % (r, patch(r)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
