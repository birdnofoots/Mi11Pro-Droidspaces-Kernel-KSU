#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asoc-pcm-numid-fix.py —— ★真正的修复★：`use_dai_pcm_id` 下把 `.id == 0` 当作"未指定"，
PCM 号回退用 `rtd->num`（唯一），从而消掉同 card 同 device 的撞号。

=========================================================================================
2026-10-11 los78 决定性实测（见 docs/mars-handover-CHECKLIST.md §41.103）
=========================================================================================
dmesg（los61 配方 + `wlan_debug=1`）拿到：

  MARS-USEID link=MSM AFE-PCM RX comp=soc:qcom,msm-stub-codec name="msm-stub-codec" base=1
  MARS-USEID link=MSM AFE-PCM TX comp=soc:qcom,msm-stub-codec name="msm-stub-codec" base=1
  MARS-NUM link=LAHAINA Media1       stream=MultiMedia1  rtd_num=0 num=0 id=0
  MARS-NUM link=MSM AFE-PCM RX       stream=AFE-PROXY RX rtd_num=5 num=0 id=0   ← ★ num 被 id 覆盖成 0
  MARS-NUM link=MSM AFE-PCM TX       stream=AFE-PROXY TX rtd_num=6 num=0 id=0   ← ★ 同上
  MARS-NUM link=AUXPCM Hostless/HDMI/CDC_DMA/SLIMBUS_7…  num=rtd_num（这些 link 的组件里没有 stub codec）
  MARS-TRACE4 pcm_add dup: new=(card=0 dev=0 id=AFE-PROXY RX msm-stub-rx-0)
                           ex =(card=0 dev=0 id=MultiMedia1 (*))
  ⇒ MARS-TRACE3 device.c type=4(PCM) err=-16 ⇒ MARS-TRACE2 device_register_all -16 ⇒ snd_card_register -16
  ⇒ /proc/asound/cards 空（无声）

根因链（完全闭环）：
  `msm-stub-codec`（`stub_dlkm`，AFE-PROXY 等 link 的 codec 组件）**真的设置了 `use_dai_pcm_id = 1`**
  ⇒ soc-core 的 `soc_link_init()` 走 `num = rtd->dai_link->id`；
  而机驱（本内核树的 techpack/audio/asoc/lahaina.c）给 **AFE-PROXY RX/TX** 这类 link **没写 `.id`**（默认 0），
  `MSM_FRONTEND_DAI_MULTIMEDIA1` 又恰好 = 0 ⇒ 三条 link 都要建 device 0 的 PCM ⇒ 第二条就 -EBUSY。
  （原厂能注册：原厂 machine_dlkm.ko 的这张表里这些 link 有各自的非 0 id —— 我们这张 LOS 表没有。）

修法（最小、只动设备号计算，不碰任何控制流/DAPM）：
      if (rtd->dai_link->no_pcm)
              num += component->driver->be_pcm_base;
      else if (rtd->dai_link->id)          /* ← 新增判断 */
              num = rtd->dai_link->id;
      /* id == 0 ⇒ 视为"未指定"，保持 num = rtd->num（唯一） */
  对 `Media1` 无影响（它 id=0 且 rtd->num=0，仍是 0 ✓），AFE-PROXY RX/TX 变成 5/6 ⇒ 不再撞号。
  其余 id 非 0 的 FE link（Media2=1、ULL=2、LowLatency=4、LSM1=41…）行为完全不变。

⚠️ 注意（留给下一个模型）：los78 同时暴露了 **cs35l41 组件的 ABI 可疑**
   （`MARS-USEID … comp=cs35l41.1-0040 name="?" base=-34` —— name 是 NULL、base 是负数，
    而 cs35l41_dlkm 是原厂 5.4.233 模块）。这会让 **BE link** 的 `num += be_pcm_base` 得到可疑值。
   如果本补丁让声卡注册成功后系统仍崩/异常，先查这条（用我们自己 5.4.242 的 cs35l41_dlkm.ko，或抓 panic）。
"""
import os
import sys

MARK = 'MARS-NUMID-FIX'

OLD = ('\t\tif (rtd->dai_link->no_pcm)\n'
       '\t\t\tnum += component->driver->be_pcm_base;\n'
       '\t\telse\n'
       '\t\t\tnum = rtd->dai_link->id;\n')

NEW = ('\t\tif (rtd->dai_link->no_pcm) {\n'
       '\t\t\tnum += component->driver->be_pcm_base;\n'
       '\t\t} else if (rtd->dai_link->id) {\n'
       '\t\t\tnum = rtd->dai_link->id;\n'
       '\t\t} else {\n'
       '\t\t\t/* MARS-NUMID-FIX: .id == 0 视为"未指定"⇒ 保留 num = rtd->num(唯一)。\n'
       '\t\t\t * 否则 AFE-PROXY RX/TX 之类没写 .id 的 link 会和 Media1(id=0) 撞 device 0，\n'
       '\t\t\t * snd_pcm_add() 返回 -EBUSY ⇒ snd_card_register() -16 ⇒ 整卡注册失败(无声)。\n'
       '\t\t\t * Media1 自身 id=0 且 rtd->num=0，行为不变。 */\n'
       '\t\t\tdev_info(card->dev, "MARS-NUMID-FIX: link %s id=0 ⇒ PCM dev 用 rtd->num=%d\\n",\n'
       '\t\t\t\t rtd->dai_link->name, num);\n'
       '\t\t}\n')


def patch(root):
    p = os.path.join(root, 'sound/soc/soc-core.c')
    if not os.path.exists(p):
        return 'soc-core.c MISSING'
    s = open(p, encoding='utf-8', errors='surrogateescape').read()
    if MARK in s:
        return 'skip(已打过)'
    if OLD not in s:
        return 'ANCHOR-MISS'
    s = s.replace(OLD, NEW, 1)
    open(p, 'w', encoding='utf-8', errors='surrogateescape').write(s)
    return 'patched(soc-core.c numid-fix)'


def main():
    roots = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not roots:
        print('用法: asoc-pcm-numid-fix.py <kernel 目录>')
        return 2
    for r in roots:
        print('%s -> %s' % (r, patch(r)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
