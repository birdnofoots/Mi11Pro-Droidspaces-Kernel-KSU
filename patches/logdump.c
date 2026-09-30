// SPDX-License-Identifier: GPL-2.0-only
/*
 * logdump.c (v3) —— 把内核日志周期性写到一块可牺牲的磁盘区域
 *
 * v1 失败:用 kmsg_dump() 触发,而它只在 panic/oops 上下文生效,workqueue 里是空操作
 * v2 失败:用 filp_open("/dev/block/...") 走路径,但那些节点是 ueventd(用户态)建的,
 *          内核早期解析不到;且状态函数在打不开设备时直接 return ⇒ 失败毫无痕迹
 * v3 修法:
 *   1. blk_lookup_devt("sde37",0) 拿 dev_t → blkdev_get_by_dev() 打开,不依赖 /dev
 *   2. 写盘用 __getblk + memcpy + mark_buffer_dirty + sync_dirty_buffer
 *   3. 只写日志"最后 256KB"(崩溃现场在末尾),降低 I/O
 *   4. 失败尽量留痕:状态记录 + pr_err(固定前缀 logdump:)
 *
 * 目标:mars 的 boot_b = /dev/block/sde37,偏移 128MB(日志)/ 131MB(状态)
 *       依据:boot 镜像真实内容只到 ~72MB,128MB 之后是零填充,写入安全
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/workqueue.h>
#include <linux/blkdev.h>
#include <linux/buffer_head.h>
#include <linux/kmsg_dump.h>
#include <linux/vmalloc.h>
#include <linux/string.h>
#include <linux/delay.h>

#define TARGET_DISK	"sde37"
#define LOG_OFFSET	(128ULL * 1024 * 1024)
#define STAT_OFFSET	(131ULL * 1024 * 1024)
#define TAIL_LEN	(256U * 1024)
#define SEC_SIZE	4096
#define PERIOD_MS	2000
#define MAGIC_LOG	"KLOGDMP3"
#define MAGIC_STAT	"KLOGSTT3"

struct logdump_hdr {
	char	magic[8];
	u32	seq;
	u32	len;
} __packed;

static struct delayed_work	logdump_work;
static struct kmsg_dumper	logdump_dumper;
static char			*logdump_buf;
static u32			logdump_seq;

static struct block_device *logdump_get_bdev(void)
{
	dev_t devt;
	struct block_device *bdev;

	devt = blk_lookup_devt(TARGET_DISK, 0);
	if (!devt) {
		pr_err("logdump: 找不到块设备 %s\n", TARGET_DISK);
		return NULL;
	}
	bdev = blkdev_get_by_dev(devt, FMODE_READ | FMODE_WRITE, NULL);
	if (IS_ERR(bdev)) {
		pr_err("logdump: 打开 %s 失败 %ld\n", TARGET_DISK, PTR_ERR(bdev));
		return NULL;
	}
	return bdev;
}

static int logdump_write_at(struct block_device *bdev, u64 off,
			    const void *data, size_t len)
{
	size_t done = 0;

	while (done < len) {
		struct buffer_head *bh;
		sector_t blk = (sector_t)((off + done) / SEC_SIZE);

		bh = __getblk(bdev, blk, SEC_SIZE);
		if (!bh)
			return -ENOMEM;
		memcpy(bh->b_data, (const char *)data + done, SEC_SIZE);
		set_buffer_uptodate(bh);
		mark_buffer_dirty(bh);
		sync_dirty_buffer(bh);
		brelse(bh);
		done += SEC_SIZE;
	}
	return 0;
}

static void logdump_write_status(int errcode, size_t len)
{
	struct block_device *bdev;
	char rec[24];
	u32 l32 = (u32)len;

	memcpy(rec, MAGIC_STAT, 8);
	memcpy(rec + 8, &logdump_seq, 4);
	memcpy(rec + 12, &errcode, 4);
	memcpy(rec + 16, &l32, 4);

	bdev = logdump_get_bdev();
	if (!bdev) {
		pr_err("logdump: 状态写不了(拿不到设备) errcode=%d\n", errcode);
		return;
	}
	logdump_write_at(bdev, STAT_OFFSET, rec, sizeof(rec));
	blkdev_put(bdev, FMODE_READ | FMODE_WRITE);
}

static size_t logdump_collect(void)
{
	size_t total = 0;

	if (!logdump_buf)
		return 0;

	kmsg_dump_rewind(&logdump_dumper);
	while (total < 4U * 1024 * 1024) {
		size_t n = 0;
		bool more;

		more = kmsg_dump_get_buffer(&logdump_dumper, false,
					    logdump_buf + total,
					    4U * 1024 * 1024 - total, &n);
		if (n == 0)
			break;
		total += n;
		if (!more)
			break;
	}
	return total;
}

static void logdump_work_fn(struct work_struct *w)
{
	struct block_device *bdev;
	size_t total, len;
	const char *tail;
	struct logdump_hdr hdr;
	int ret;

	total = logdump_collect();
	if (total == 0) {
		logdump_write_status(-ENODATA, 0);
		goto out;
	}

	len = total > TAIL_LEN ? TAIL_LEN : total;
	tail = logdump_buf + (total - len);

	memcpy(hdr.magic, MAGIC_LOG, 8);
	hdr.seq = ++logdump_seq;
	hdr.len = (u32)len;

	bdev = logdump_get_bdev();
	if (!bdev) {
		logdump_write_status(-ENODEV, len);
		goto out;
	}

	ret = logdump_write_at(bdev, LOG_OFFSET, &hdr, sizeof(hdr));
	if (ret == 0)
		ret = logdump_write_at(bdev, LOG_OFFSET + sizeof(hdr), tail, len);
	blkdev_put(bdev, FMODE_READ | FMODE_WRITE);

	if (ret)
		pr_err("logdump: 写日志失败 %d\n", ret);

out:
	queue_delayed_work(system_wq, &logdump_work,
			   msecs_to_jiffies(PERIOD_MS));
}

static int __init logdump_init(void)
{
	logdump_buf = vmalloc(4U * 1024 * 1024);
	if (!logdump_buf) {
		pr_err("logdump: 缓冲区分配失败\n");
		return -ENOMEM;
	}

	if (kmsg_dump_register(&logdump_dumper))
		pr_err("logdump: kmsg_dump_register 失败(不致命)\n");

	INIT_DELAYED_WORK(&logdump_work, logdump_work_fn);
	queue_delayed_work(system_wq, &logdump_work, msecs_to_jiffies(5000));

	pr_info("logdump: v3 已启用 目标 %s 偏移 %lluMB 周期 %dms\n",
		TARGET_DISK, LOG_OFFSET >> 20, PERIOD_MS);
	return 0;
}

late_initcall(logdump_init);

MODULE_DESCRIPTION("periodic kernel log dumper (v3, bdev by devt)");
MODULE_LICENSE("GPL v2");
