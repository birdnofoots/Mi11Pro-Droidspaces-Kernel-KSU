// SPDX-License-Identifier: GPL-2.0-only
/*
 * logdump.c —— 把内核日志周期性写到一块可牺牲的磁盘区域
 *
 * 目的:设备被硬件复位(看门狗/电源)时,内核来不及留下任何日志。
 *      本驱动每 2 秒把整份 log_buf 写到 boot 分区的零填充区,
 *      所以崩溃前最后一次写入必然已经在盘上。
 *
 * 目标(经实测选定):
 *   /dev/block/by-name/boot_b  偏移 128MB,上限 4MB
 * 依据:原厂 boot 镜像真实内容只到约 72MB,之后到 192MB 全是零填充,
 *      写 128MB 处不影响镜像,ABL 只读 header 描述的范围。
 *
 * 读回(需要 root):
 *   adb shell su -c 'dd if=/dev/block/by-name/boot_b bs=4096 skip=32768 count=1024'
 *   | strings | less
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/workqueue.h>
#include <linux/fs.h>
#include <linux/file.h>
#include <linux/delay.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/printk.h>
#include <linux/kmsg_dump.h>
#include <linux/vmalloc.h>

#define LOGDUMP_PATH_BYNAME  "/dev/block/by-name/boot_b"
#define LOGDUMP_PATH_RAW     "/dev/block/sde37"      /* mars: boot_b 的实际节点 */
#define LOGDUMP_OFFSET       (128ULL * 1024 * 1024)  /* 128MB,零填充区 */
#define LOGDUMP_MAXLEN       (4U * 1024 * 1024)      /* 4MB 上限 */
#define LOGDUMP_PERIOD_MS    2000
#define LOGDUMP_MAGIC        "KLOGDMP1"

/* 记录头:magic(8) + seq(4) + len(4) = 16 字节 */
struct logdump_hdr {
	char	magic[8];
	u32	seq;
	u32	len;
} __packed;

static struct delayed_work	logdump_work;
static struct kmsg_dumper	logdump_dumper;
static char			*logdump_buf;
static u32			logdump_seq;
static bool			logdump_opened_once;

/*
 * 收集整份内核日志到 logdump_buf,返回长度(不含结尾 0)。
 * 只能在 kmsg_dumper 回调里调用 kmsg_dump_get_buffer(),所以本函数
 * 由 logdump_dump() 调用。
 */
static size_t logdump_collect(void)
{
	size_t len = 0;

	if (!logdump_buf)
		return 0;

	/*
	 * 5.4 的签名:bool kmsg_dump_get_buffer(dumper, syslog, buf, size, &len)
	 * 每次取一段,取完返回 false。连续调用可拿到后续内容。
	 */
	while (len < LOGDUMP_MAXLEN) {
		size_t n = 0;
		bool more;

		more = kmsg_dump_get_buffer(&logdump_dumper, false,
					    logdump_buf + len,
					    LOGDUMP_MAXLEN - len, &n);
		if (n == 0)
			break;
		len += n;
		if (!more)
			break;
	}
	return len;
}

/*
 * 真正落盘。在 workqueue 上下文执行(可以睡眠)。
 */
static void logdump_write_to_disk(const char *data, size_t len)
{
	struct file *f;
	struct logdump_hdr hdr;
	loff_t pos = LOGDUMP_OFFSET;
	ssize_t ret;

	if (!data || len == 0)
		return;

	/* 优先用 by-name;早期 ueventd 还没建好软链时退回裸节点 */
	f = filp_open(LOGDUMP_PATH_BYNAME, O_WRONLY | O_LARGEFILE, 0);
	if (IS_ERR(f)) {
		f = filp_open(LOGDUMP_PATH_RAW, O_WRONLY | O_LARGEFILE, 0);
		if (IS_ERR(f)) {
			pr_debug("logdump: 打不开目标设备,稍后重试\n");
			return;
		}
	}
	if (!logdump_opened_once) {
		logdump_opened_once = true;
		pr_info("logdump: 已打开落盘目标,偏移 %llu MB\n",
			LOGDUMP_OFFSET >> 20);
	}

	if (len > LOGDUMP_MAXLEN - sizeof(hdr))
		len = LOGDUMP_MAXLEN - sizeof(hdr);

	memcpy(hdr.magic, LOGDUMP_MAGIC, sizeof(hdr.magic));
	hdr.seq = ++logdump_seq;
	hdr.len = (u32)len;

	ret = kernel_write(f, &hdr, sizeof(hdr), &pos);
	if (ret == sizeof(hdr))
		ret = kernel_write(f, data, len, &pos);

	if (ret < 0)
		pr_debug("logdump: 写入失败 %zd\n", ret);

	/* 关键:必须落盘,否则硬复位时数据还在 page cache 里 */
	vfs_fsync(f, 1);
	filp_close(f, NULL);
}

/*
 * 状态记录:写在日志区之后 3MB 处(即偏移 131MB)。
 * 万一日志没写成功,这里能留下原因,下次不用再猜。
 * 格式:"KLOGSTAT" + seq(4) + errcode(4) + len(4)
 */
#define LOGDUMP_STAT_OFFSET  (LOGDUMP_OFFSET + 3ULL * 1024 * 1024)

static void logdump_write_status(int errcode, size_t len)
{
	struct file *f;
	char rec[24];
	loff_t pos = LOGDUMP_STAT_OFFSET;
	int n;

	memcpy(rec, "KLOGSTAT", 8);
	memcpy(rec + 8, &logdump_seq, 4);
	memcpy(rec + 12, &errcode, 4);
	{
		u32 l32 = (u32)len;
		memcpy(rec + 16, &l32, 4);
	}

	f = filp_open(LOGDUMP_PATH_BYNAME, O_WRONLY | O_LARGEFILE, 0);
	if (IS_ERR(f))
		f = filp_open(LOGDUMP_PATH_RAW, O_WRONLY | O_LARGEFILE, 0);
	if (IS_ERR(f))
		return;   /* 连状态都写不了,只能放弃 */

	n = kernel_write(f, rec, 20, &pos);
	(void)n;
	vfs_fsync(f, 1);
	filp_close(f, NULL);
}

static void logdump_dump(struct kmsg_dumper *dumper,
			 enum kmsg_dump_reason reason)
{
	size_t len = logdump_collect();

	if (len)
		logdump_write_to_disk(logdump_buf, len);
}

/*
 * 注意:v1 用 kmsg_dump() 触发,结果什么都没写出来 ——
 * kmsg_dump() 是给 panic/oops 用的,从 workqueue 调用会被静默忽略。
 * 正确做法:kmsg_dump_rewind() 重置游标,然后直接收集。
 */
static void logdump_work_fn(struct work_struct *w)
{
	size_t len;

	kmsg_dump_rewind(&logdump_dumper);
	len = logdump_collect();

	if (len) {
		logdump_write_to_disk(logdump_buf, len);
		logdump_write_status(0, len);
	} else {
		logdump_write_status(-ENODATA, 0);
	}

	queue_delayed_work(system_wq, &logdump_work,
			   msecs_to_jiffies(LOGDUMP_PERIOD_MS));
}

static int __init logdump_init(void)
{
	logdump_buf = vmalloc(LOGDUMP_MAXLEN);
	if (!logdump_buf) {
		pr_err("logdump: 分配缓冲区失败\n");
		return -ENOMEM;
	}

	logdump_dumper.dump = logdump_dump;
	if (kmsg_dump_register(&logdump_dumper)) {
		pr_err("logdump: 注册 dumper 失败\n");
		vfree(logdump_buf);
		logdump_buf = NULL;
		return -EBUSY;
	}

	INIT_DELAYED_WORK(&logdump_work, logdump_work_fn);
	/* 等根文件系统/ueventd 起来一点再开始 */
	queue_delayed_work(system_wq, &logdump_work, msecs_to_jiffies(3000));

	pr_info("logdump: 已启用(每 %d ms 写一次)\n", LOGDUMP_PERIOD_MS);
	return 0;
}

late_initcall(logdump_init);

MODULE_DESCRIPTION("periodic kernel log dumper for hard-reset debugging");
MODULE_LICENSE("GPL v2");
