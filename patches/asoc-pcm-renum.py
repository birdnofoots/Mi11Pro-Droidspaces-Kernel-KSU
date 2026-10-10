#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asoc-pcm-renum.py —— 给"撞号"的 PCM 换一个空闲 device 号（让声卡能注册成功）。

根因（2026-10-11 静态 + 真机双重实证，见 docs/mars-handover-CHECKLIST.md §41.101）：
  machine_dlkm.ko（源码 = 本内核树 techpack/audio/asoc/lahaina.c）里
  populate_snd_card_dailinks() 拼出的 DAI link 表存在**重复 .id**：
      msm_common_dai_links[]        : .name = MSM_DAILINK_NAME(MultiMedia10), .id = MSM_FRONTEND_DAI_MULTIMEDIA10
      msm_common_misc_fe_dai_links[]: .name = MSM_DAILINK_NAME(Compress3),    .id = MSM_FRONTEND_DAI_MULTIMEDIA10
  两者的 SND_SOC_DAILINK_REG(multimedia10) 完全一样（同一个 CPU DAI）。
  而 FE 组件（use_dai_pcm_id=1）走 soc-core 的
      num = rtd->dai_link->id;      /* 见 soc_link_init() */
  ⇒ 两条 link 建出**同 card 同 device** 的两个 PCM ⇒ snd_pcm_add() 返回 -EBUSY
  ⇒ snd_device_register_all() -16 ⇒ snd_card_register() -16
  ⇒ snd_soc_register_card() -16 ⇒ "probe ... failed with error -16" ⇒ /proc/asound/cards 空（无声）。
  （修好这个之前，用"容忍 -EBUSY"改 ASoC 控件/DAPM 控制流的补丁会挂机/重启循环：los67、los70。）

做法（最小、无损、只动 soc-core.c）：
  在 soc_new_pcm(rtd, num) 之前，如果该 device 号在这张 card 上已被某个已建 PCM 占用，
  就往后找第一个空闲号。**先创建的那条 link 保留原号**（HAL 期望的编号不变），
  重复的那条挪到空位（例如 Compress3 的 PCM）。
"""
import os
import sys

MARK = 'MARS-PCM-RENUM'

HELPER = '''
/*
 * MARS-PCM-RENUM: 该 device 号在本卡上是否已被别的 PCM 占用？
 * （PCM 在 snd_pcm_new() 时就以 SNDRV_DEV_PCM 挂进 card->devices，
 *   所以整卡 register 之前就能查出来；snd_pcm_add() 只在 register 时才查。）
 */
static bool snd_soc_mars_pcm_dev_busy(struct snd_card *snd_card, unsigned int dev)
{
	struct snd_device *devp;
	struct snd_pcm *pcm;

	if (!snd_card)
		return false;
	list_for_each_entry(devp, &snd_card->devices, list) {
		if (devp->type != SNDRV_DEV_PCM || !devp->device_data)
			continue;
		pcm = devp->device_data;
		if ((unsigned int)pcm->device == dev)
			return true;
	}
	return false;
}

'''

NEW_BLOCK = '''\t/* MARS-PCM-RENUM: 撞号就换一个空闲 device —— machine_dlkm 的 link 表有重复 .id
\t * (MultiMedia10 与 Compress3 都是 MSM_FRONTEND_DAI_MULTIMEDIA10)，
\t * 不换号则整卡 register 会 -16 ⇒ 没有 sound card。 */
\t{
\t\tunsigned int d = (num < 0) ? 0u : (unsigned int)num;

\t\twhile (d < 256u &&
\t\t       snd_soc_mars_pcm_dev_busy(card->snd_card, d))
\t\t\td++;
\t\tif ((int)d != num) {
\t\t\tdev_info(card->dev,
\t\t\t\t "MARS-PCM-RENUM: %s device %d -> %u (该号已被占用)\\n",
\t\t\t\t dai_link->stream_name, num, d);
\t\t\tnum = (int)d;
\t\t}
\t}

\t/* create the pcm */
\tret = soc_new_pcm(rtd, num);
'''

OLD_BLOCK = ('\t/* create the pcm */\n'
             '\tret = soc_new_pcm(rtd, num);\n')

ANCHOR = ('static int soc_link_init(struct snd_soc_card *card,\n'
          '\t\t\t struct snd_soc_pcm_runtime *rtd)\n')


def patch(root):
    p = os.path.join(root, 'sound/soc/soc-core.c')
    if not os.path.exists(p):
        return 'soc-core.c MISSING'
    s = open(p, encoding='utf-8', errors='surrogateescape').read()
    if MARK in s:
        return 'skip(已打过)'
    if ANCHOR not in s:
        return 'FUNC-ANCHOR-MISS'
    s = s.replace(ANCHOR, HELPER + ANCHOR, 1)
    if OLD_BLOCK not in s:
        return 'CALL-ANCHOR-MISS'
    s = s.replace(OLD_BLOCK, NEW_BLOCK, 1)
    open(p, 'w', encoding='utf-8', errors='surrogateescape').write(s)
    return 'patched(soc-core.c pcm-renum)'


def main():
    roots = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not roots:
        print('用法: asoc-pcm-renum.py <kernel 目录>')
        return 2
    for r in roots:
        print('%s -> %s' % (r, patch(r)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
