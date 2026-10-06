// SPDX-License-Identifier: GPL-2.0-only
/*
 * logdump.c —— 把内核日志写进一块可牺牲的裸分区(抓「硬复位 / 挂死」现场)
 *
 * 背景:v3 及更早的三次尝试都写不出任何东西,原因(已定位):
 *   1) kmsg_dump_get_buffer() 只在 dumper->active(即 kmsg_dump 回调上下文)里
 *      有效 —— 从普通 workqueue 调用必定返回 len=0;
 *   2) 失败时的「状态记录」又走 filp_open(/dev/...),而 /dev 节点是 ueventd
 *      (用户态)创建的 ⇒ 内核线程打不开 ⇒ 连"失败痕迹"都留不下;
 *   3) 回调里直接做块层 I/O 会睡眠(submit_bh/sync_dirty_buffer),在 panic /
 *      restart 上下文里不安全,可能什么都没写成还把自己挂住。
 *
 * 设计(v4,2026-10-02):
 *   1) 周期路径 —— 每 2 秒一次 delayed_work(workqueue,可以睡眠):
 *        a. 采集:用【未注册的 kmsg_dumper 实例】自己置 active=true +
 *           kmsg_dump_rewind() + kmsg_dump_get_buffer(),直接拿到 log_buf 最新内容
 *           (不调用 kmsg_dump(),所以不会连带触发原厂 mtdoops 的 2MB 写)
 *        b. 兜底 1:do_syslog(SYSLOG_ACTION_READ_ALL) + set_fs(KERNEL_DS)
 *        c. 兜底 2(每 15 轮一次):kmsg_dump(KMSG_DUMP_OOPS) —— 会调用我们注册的
 *           回调(把快照排队落盘),顺带也让原厂 mtdoops 把日志写进 sda15 的
 *           LAST KMSG 区(那是一条独立的、刷回原厂就能读的通道)
 *        d. 落盘:bio 直写块设备 —— 不依赖 /dev 节点、不依赖 ueventd、
 *           不经过任何文件系统(EROFS / dm-verity 都无关)
 *   2) 崩溃路径 —— kmsg_dumper 回调(panic / restart):
 *        - 回调里【只做拷贝】:把日志收进静态快照缓冲(这一步就是 memcpy 的
 *          等价物,因为 kmsg_dump_get_buffer 只能在回调里取数据),然后
 *          schedule_work()
 *        - 真正的落盘在 workqueue 里做(那里可以睡眠)
 *
 * 目标:/dev/block/sde59(= by-name/logdump,64MB 裸分区)
 *   偏移 0      : 日志(头 512B + 正文,正文上限 1MB = 保留 log_buf 最新的一半)
 *   偏移 2MB    : 状态记录(每轮覆盖两次:本轮开始 / 本轮结束)
 *                 ⇒ 即使日志没写成,"状态记录"也能证明驱动跑过、卡在哪一步
 *
 * 读回(刷回原厂、有 root 之后):
 *   adb shell su -c "dd if=/dev/block/by-name/logdump of=/data/local/tmp/x.bin bs=1M count=4"
 *   adb pull /data/local/tmp/x.bin
 *   然后搜 KLOGDMP4 / KLOGSTT4(或直接用 scripts/read-logdump.py 解析)
 */

#define pr_fmt(fmt) "logdump: " fmt

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/workqueue.h>
#include <linux/kthread.h>
#include <linux/delay.h>
#include <linux/sched/debug.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/blkdev.h>
#include <linux/bio.h>
#include <linux/fs.h>
#include <linux/genhd.h>
#include <linux/vmalloc.h>
#include <linux/mm.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/math64.h>
#include <linux/ktime.h>
#include <linux/timekeeping.h>
#include <linux/kmsg_dump.h>
#include <linux/syslog.h>
#include <linux/uaccess.h>
#include <linux/printk.h>
#include <linux/reboot.h>
#include <linux/crc32.h>	/* 自救时重算 GPT 的两处 CRC32 */
#include <linux/umh.h>
#include <linux/fcntl.h>

/* ── 目标分区 ───────────────────────────────────────────────────────── */
#define LOGDUMP_DEV_NAME	"sde"
#define LOGDUMP_DEV_PART	59	/* /dev/block/sde59 = by-name/logdump,64MB */

#define LOGDUMP_LOG_OFFSET	(0ULL)			/* 日志本体 */
#define LOGDUMP_STAT_OFFSET	(8ULL * 1024 * 1024)	/* 状态记录(v4.10:2MB→8MB,给 2MB 正文让位) */

/* ── 缓冲布局 ───────────────────────────────────────────────────────── */
#define LOGDUMP_STATUS_MAX	4096			/* 状态记录用 1 页 */
#define LOGDUMP_HDR_MAX		512			/* 日志头 */
/* v4.10:正文上限提到整条 ring(2MB),保住早期 init/modprobe 那几行 */
#define LOGDUMP_TEXT_MAX	(512 * 1024)	/* v4.13:回到 512KB,减轻启动期 I/O */

#define LOGDUMP_BUF_SIZE	(LOGDUMP_STATUS_MAX + LOGDUMP_HDR_MAX + LOGDUMP_TEXT_MAX)
#define LOGDUMP_OFF_HDR		LOGDUMP_STATUS_MAX
#define LOGDUMP_OFF_TEXT	(LOGDUMP_OFF_HDR + LOGDUMP_HDR_MAX)

#define LOGDUMP_SNAP_SIZE	(LOGDUMP_HDR_MAX + LOGDUMP_TEXT_MAX)
#define LOGDUMP_OFF_SNAP_TEXT	LOGDUMP_HDR_MAX

#define LOGDUMP_PERIOD_MS	500
#define LOGDUMP_MAX_BIO_PAGES	32			/* 每个 bio 最多 32 页(128KB) */
#define LOGDUMP_KMSGDMP_EVERY	15			/* 兜底 2 的间隔(轮) */

/*
 * ★★★ 启动失败 ⇒ 自动进 fastboot(全自动调试的关键)
 *   实测:启动失败时用户态会在 ~106 秒调用 reboot 重启(无限循环)。
 *   这里由内核自己判断"启动失败",在用户态重启之前【主动 kernel_restart("bootloader")】
 *   ⇒ 设备自动停在 FASTBOOT 界面,主机就能自动刷回原厂、读日志、再刷下一版,
 *     全程不需要人按键。
 *   判据:
 *     1) uptime > LOGDUMP_BOOT_TIMEOUT_MS 仍没在日志里见到 "Boot completed";或
 *     2) surfaceflinger SIGABRT 崩溃 ≥3 次 且 uptime > 45 秒(崩溃循环)
 */
#define LOGDUMP_BOOT_TIMEOUT_MS	300000
/*
 * ★ 2026-10-03 诊断:【开机早期快照】。
 *   现场(sde59):init 在 ~2.3s 启动一个 exec 服务后一直等到 295s
 *   (init: Exec service is hung? Waited 292.817 without SIGCHLD),
 *   导致 post-fs-data/surfaceflinger/显示全部排在后面 ⇒ 画面永远停在引导器 splash。
 *   而内核环形缓冲只有 256KB(log_buf_len=256K),开机早期的 init 服务启动行
 *   在几十秒后就被冲掉了 ⇒ 读不到"卡在哪个服务"。
 *   做法:在 uptime 到 LOGDUMP_EARLY_MS 时,把当前正文另存一份到 36MB 偏移
 *   (原厂 logdump 只写开头,刷回原厂后这份快照仍在,可 dd 读回)。
 *
 * ★★ 2026-10-06 真机取证后【再提前】+【加一段】:
 *   run157 自编内核首次真机启动成功(进 MIUI),但没有 USB/WiFi/触屏 ⇒ 无任何通道,
 *   只能靠本分区取回日志。读回后发现:20s 那份快照里最早的日志行是 12.36s ——
 *   因为启动中期(kernel_init 之后)有一次约 500KB 的"全任务 + 每 CPU rq 状态"转储,
 *   把 log_buf_len=256K 的环缓冲整个冲掉了;而 **vendor 模块装载发生在 5~10s**
 *   (原厂对照:dwc3 1.79s、qti_battery_charger 8.02s、gadget 10.33s),
 *   正好落在被冲掉的窗口里 ⇒ "哪个模块没装上、报什么错"完全看不见。
 *   现在改成三段快照:
 *     4s  → 36MB(0~4s:PHY/regulator/dwc3 探针、early init)
 *     11s → 40MB(4~11s:★模块装载期,含 4.6s 采集脚本打的 /proc/modules)
 *     55s → 32MB(现场快照,原样保留)
 */
#define LOGDUMP_EARLY_MS	4000
#define LOGDUMP_EARLY_OFFSET	(36ULL * 1024 * 1024)
#define LOGDUMP_EARLY2_MS	11000
#define LOGDUMP_EARLY2_OFFSET	(40ULL * 1024 * 1024)
/*
 * ★ 2026-10-03 诊断用:开箱现场快照 + 自动回 fastboot。
 *   现象:内核能启动但卡在 ~50s(module_mutex 被某个 vendor 模块 init 永久占住,
 *   msm_drm/触摸/电池等 29 个模块全装不上 ⇒ 无显示、无 WiFi)。
 *   窗口问题:正文只覆盖最后 ~10 秒,而恢复流程要先刷回原厂(原厂 logdump 会覆盖分区开头),
 *   所以把"卡死那一刻(55s)"的正文【额外写一份到 32MB 偏移】⇒ 刷回原厂后仍可读。
 *   同时把 auto_fastboot 打开:300 秒后自己重启进 fastboot ⇒ 救机脚本自动刷回原厂,
 *   全程不需要人工按键。
 */
#define LOGDUMP_SNAP2_OFFSET	(32ULL * 1024 * 1024)
#define LOGDUMP_SNAP2_MS	55000
#define LOGDUMP_SF_CRASH_LIMIT	3
#define LOGDUMP_SF_CRASH_UPTIME	45000

#define LOGDUMP_MAGIC		"KLOGDMP4"
#define LOGDUMP_STAT_MAGIC	"KLOGSTT4"

/* 采集途径(写进状态记录,便于判断哪条路是通的) */
#define LOGDUMP_SRC_PERIODIC	1	/* 周期:自己置 active + get_buffer */
#define LOGDUMP_SRC_SYSLOG	2	/* 周期:do_syslog 兜底 */
#define LOGDUMP_SRC_CALLBACK	3	/* 崩溃回调快照(workqueue 落盘) */
#define LOGDUMP_SRC_KMSGDMP	4	/* 兜底:kmsg_dump(OOPS) 触发 */

/* 日志头(占用 512 字节区的前若干字节,其余补零) */
struct logdump_hdr {
	char	magic[8];	/* KLOGDMP4 */
	u32	seq;
	u32	len;		/* 正文有效长度 */
	u32	source;		/* LOGDUMP_SRC_* */
	u32	reason;		/* kmsg_dump_reason */
	u64	uptime_ms;
	u32	sum;		/* 正文的简单校验和 */
	u32	pad;
} __packed;

/* 状态记录(占用 512 字节,其余补零) */
struct logdump_stat {
	char	magic[8];	/* KLOGSTT4 */
	u32	seq;
	u32	count;		/* 第几次周期心跳 */
	s32	errcode;	/* 写日志的返回值,0=成功 */
	u32	len;
	u32	source;
	u32	reason;
	u64	uptime_ms;
	u64	jif;
	char	text[96];	/* ASCII,便于 strings 直读 */
} __packed;

static char			*logdump_buf;	/* 周期路径缓冲 */
static char			*logdump_snap;	/* 崩溃回调快照缓冲 */
static struct block_device	*logdump_bdev;
static struct kmsg_dumper	 logdump_dumper;	/* 已注册:崩溃回调 */
static struct kmsg_dumper	 logdump_reader;	/* 未注册:周期采集 */
static struct delayed_work	 logdump_work;
static struct work_struct	 logdump_dump_work;
static DEFINE_MUTEX(logdump_mutex);		/* 串行化两条落盘路径 */
static DEFINE_SPINLOCK(logdump_snap_lock);
static bool			 logdump_snap_pending;
static size_t			 logdump_snap_len;
static u32			 logdump_snap_seq;
static u32			 logdump_snap_reason;
static u32			 logdump_seq;
static u32			 logdump_count;
static struct task_struct	*logdump_thread;
/* 用于"日志停涨 ⇒ Dump 所有任务状态"的判据 */
static size_t			 logdump_prev_len;
static size_t			 logdump_prev2_len;
static u64			 logdump_len_same_since_ms;
static u64			 logdump_last_dump_ms;
static bool			 logdump_boot_done;	/* 见到 "Boot completed" */
static bool			 logdump_auto_fb_done;	/* 已经触发过自动进 fastboot */
static bool			 logdump_early_done;	/* 早期快照已写 */
static bool			 logdump_early2_done;	/* 模块装载期快照已写(2026-10-06) */
static bool			 logdump_snap2_done;	/* 55s 现场快照已写 */
static bool			 logdump_statedump_done;	/* v4.10:任务转储只做一次 */
/* v4.10 诊断:由 kernel/module.c 追加的调试钩子 */
extern struct task_struct	*moddbg_mutex_owner(void);
extern void			 moddbg_dump(void);
static int			 logdump_sf_crashes;
static size_t			 logdump_sf_scan_off;	/* v4.8:已统计过的正文长度 */
static bool			 logdump_first_ok;
/*
 * v4.9:自动进 fastboot 开关【默认关】。
 *       理由(2026-10-02 实测):判据是"内核日志里出现字符串 Boot completed",
 *       而 Android 13 / MIUI 14 的内核日志里【根本不存在这个字符串】
 *       (grep logdump-v6.txt → 0 命中) ⇒ logdump_boot_done 永远为假 ⇒
 *       uptime>300s 必定 kernel_restart("bootloader") ⇒ 每次启动 5 分钟后
 *       自己冲进 fastboot,表现为"黑屏 → 小绿人"循环。
 *       调试期需要时用 cmdline logdump.logdump_auto_fastboot=1 打开。
 */
static bool			 logdump_auto_fastboot = false;  /* v4.13:默认关!它的成功判据是日志里出现
								 *   "Boot completed",而 MIUI 内核日志里根本没这字符串
								 *   ⇒ 开机成功了也会在 300s 被它重启。诊断期用
								 *   cmdline logdump.logdump_auto_fastboot=1 打开。 */
module_param(logdump_auto_fastboot, bool, 0644);
/*
 * ★★ 关键:块设备的【逻辑块大小】。UFS 上是 4096(实测
 *    /sys/block/sde/queue/logical_block_size = 4096)。
 *    往块设备提交 bio 时,长度不是逻辑块大小整数倍 ⇒ sd/UFS 直接回 -EIO。
 *    v4 第一版就栽在这里:37 个失败写入 100% 都不是 4096 的倍数,
 *    唯一成功的那次(seq=1)长度 135168 = 4096×33。
 *    ⇒ 所有写入都按这个值向上对齐。
 */
static unsigned int		 logdump_align = 512;

static u64 logdump_uptime_ms(void)
{
	return div_u64(ktime_to_ns(ktime_get()), 1000000);
}

/* ══════════════════════════════════════════════════════════════════════
 * ★★★ v4.7:由【内核自己】spawn 一个 root shell,把用户态日志抓下来
 *
 *  为什么必须这么做:
 *    MIUI 的用户态日志只进 logd 的 buffer(不落内核日志),而
 *    surfaceflinger 自杀的真正原因('no suitable EGLConfig found')就在那里。
 *    sda15 的 "LAST LOGCAT" 段只有 header 没有正文;logd 的 logpersist 在
 *    user 版被砍;Magisk 补丁在这台机器上拿不到 root(用户实测)。
 *    ⇒ 内核主动 spawn 用户态进程是唯一可靠路径(内核是我们的)。
 *
 *  两个前提都满足:
 *    1) CONFIG_SECURITY_SELINUX_DEVELOP=y ⇒ 可以把 SELinux 切成 permissive;
 *       (内核 spawn 的进程落在 kernel 域,enforcing 下会被 SELinux 拒)
 *    2) /system/bin/sh 在 /system 挂好后就存在(约 1.9 秒),logd 4.1 秒起来。
 *
 *  cmdline 可控开关(默认都开,方便关掉对比):
 *    logdump.logdump_force_permissive=0
 *    logdump.logdump_spawn_helper=0
 * ══════════════════════════════════════════════════════════════════════ */
static bool logdump_force_permissive = true;
static bool logdump_spawn_helper = true;
module_param(logdump_force_permissive, bool, 0644);
module_param(logdump_spawn_helper, bool, 0644);

/*
 * selinux_enforcing 在 5.4 里是全局 int(security/selinux/hooks.c)。
 * 用 weak 引用:万一那棵树里它是 static 或者改名了,链接【不会失败】,
 * 地址为 0,我们就走 selinuxfs 那条路。
 */
extern int selinux_enforcing __attribute__((weak));

static bool logdump_perm_done;
static bool logdump_helper_done;
static int  logdump_helper_tries;
static u64  logdump_helper_last_ms;

static void logdump_set_permissive(void)
{
	struct file *f;
	loff_t pos = 0;

	if (&selinux_enforcing) {
		selinux_enforcing = 0;
		pr_emerg("logdump: selinux_enforcing 已置 0(permissive)\n");
	} else {
		pr_warn("logdump: 没有 selinux_enforcing 符号,改试 selinuxfs\n");
	}
	f = filp_open("/sys/fs/selinux/enforce", O_WRONLY, 0);
	if (!IS_ERR(f)) {
		kernel_write(f, "0", 1, &pos);
		filp_close(f, NULL);
		pr_emerg("logdump: 已写 /sys/fs/selinux/enforce=0\n");
	} else {
		pr_warn("logdump: 打开 selinuxfs enforce 失败 %ld\n", PTR_ERR(f));
	}
}

/*
 * v4.10:采集脚本改成把结果【写进 /dev/kmsg】。
 *   旧版写 /data/local/tmp/dbg —— init 卡在 early-init 时 /data 根本没挂,
 *   什么都拿不到。写 kmsg 则会被 logdump 自己采集落盘。
 *   重点:/proc/modules(能显示 COMING=Loading 的模块)
 *        /proc/<pid>/stack(每个 modprobe/kworker 的完整内核栈,不受 512KB 截断影响)
 */
static const char *logdump_helper_cmd =
	"L(){ printf 'KDBG %s\\n' \"$1\" > /dev/kmsg 2>/dev/null; }; "
	"L '=== MODULES(/proc/modules) ==='; "
	"cat /proc/modules 2>&1 | while IFS= read -r l; do L \"$l\"; done; "
	"L '=== TASK STACKS ==='; "
	"for p in /proc/[0-9]*; do "
	  "c=$(cat $p/comm 2>/dev/null) || continue; "
	  "case \"$c\" in "
	    "modprobe|vendor_modprobe|init|ueventd|logd|surfaceflinger|kworker*) "
	      "L \"--- ${p#/proc/} $c $(grep -m2 -E '^(Name|State):' $p/status 2>/dev/null | tr '\\n' ' ') wchan=$(cat $p/wchan 2>/dev/null)\"; "
	      "cat $p/stack 2>/dev/null | while IFS= read -r l; do L \"$l\"; done ;; "
	  "esac; "
	"done; "
	"L '=== HELPER DONE ==='";

static void logdump_spawn_userspace(void)
{
	char *argv[] = { "/system/bin/sh", "-c", (char *)logdump_helper_cmd, NULL };
	char *envp[] = { "HOME=/", "PATH=/sbin:/system/sbin:/system/bin:/system/xbin", NULL };
	int ret;

	logdump_helper_tries++;
	ret = call_usermodehelper(argv[0], argv, envp, UMH_WAIT_EXEC);
	if (ret == 0)
		logdump_helper_done = true;
	pr_emerg("logdump: spawn 采集脚本 try=%d ret=%d%s\n",
		 logdump_helper_tries, ret, ret == 0 ? "(成功)" : "(失败)");
}

static bool logdump_memstr(const char *hay, size_t hlen, const char *needle)
{
	size_t nlen = strlen(needle), i;

	if (!nlen || hlen < nlen)
		return false;
	for (i = 0; i + nlen <= hlen; i++)
		if (!memcmp(hay + i, needle, nlen))
			return true;
	return false;
}

/*
 * ★ v4.8:逐行统计"真正的 SF 崩溃"。
 *   只有同一行里同时出现 "surfaceflinger" 和 "received signal" 才算
 *   —— 也就是 init 那行:
 *     init: Service 'surfaceflinger' (pid 1323) received signal 6
 *   相机之类的 `... received signal 6` 不含 surfaceflinger ⇒ 不计数;
 *   logcat 镜像里含 surfaceflinger 的行不含 received signal ⇒ 不计数。
 */
static int logdump_count_sf_crash(const char *text, size_t len)
{
	int n = 0;
	size_t i = 0;

	while (i < len) {
		size_t j = i;

		while (j < len && text[j] != '\n')
			j++;
		if (logdump_memstr(text + i, j - i, "surfaceflinger") &&
		    logdump_memstr(text + i, j - i, "received signal"))
			n++;
		i = j + 1;
	}
	return n;
}

static u32 logdump_sum(const char *p, size_t len)
{
	u32 s = 0;
	size_t i;

	for (i = 0; i < len; i++)
		s = s * 31 + (u8)p[i];
	return s;
}

/* ── 块设备:按 devt 打开(完全不走 /dev 节点)─────────────────────── */
static struct block_device *logdump_get_bdev(void)
{
	dev_t devt;
	struct block_device *bdev;

	if (logdump_bdev)
		return logdump_bdev;

	devt = blk_lookup_devt(LOGDUMP_DEV_NAME, LOGDUMP_DEV_PART);
	if (!devt) {
		pr_err("blk_lookup_devt(%s,%d) 没找到(块设备还没就绪?)\n",
		       LOGDUMP_DEV_NAME, LOGDUMP_DEV_PART);
		return NULL;
	}

	bdev = blkdev_get_by_dev(devt, FMODE_READ | FMODE_WRITE, NULL);
	if (IS_ERR(bdev)) {
		pr_err("blkdev_get_by_dev(%u:%u) 失败 %ld\n",
		       MAJOR(devt), MINOR(devt), PTR_ERR(bdev));
		return NULL;
	}

	logdump_bdev = bdev;

	/* 逻辑块大小:写入长度必须是它的整数倍,否则 -EIO */
	logdump_align = bdev_logical_block_size(bdev);
	if (logdump_align < 512)
		logdump_align = 512;
	if (logdump_align > PAGE_SIZE)
		logdump_align = PAGE_SIZE;

	pr_info("已打开 %s%d(devt %u:%u,容量 %llu 字节,逻辑块 %u 字节)\n",
		LOGDUMP_DEV_NAME, LOGDUMP_DEV_PART, MAJOR(devt), MINOR(devt),
		(unsigned long long)i_size_read(bdev->bd_inode), logdump_align);
	return bdev;
}

/*
 * 用 bio 直写块设备。
 * 只在 workqueue 上下文调用(submit_bio_wait 会睡眠)。
 */
static int logdump_write(loff_t offset, void *buf, size_t len)
{
	struct block_device *bdev;
	loff_t devsz;
	size_t done = 0;

	if (!len)
		return 0;

	bdev = logdump_get_bdev();
	if (!bdev)
		return -ENODEV;

	/*
	 * ★ 长度必须按逻辑块大小向上对齐(尾部补零),否则驱动回 -EIO。
	 *   128KB(LOGDUMP_MAX_BIO_PAGES*PAGE_SIZE)本身是 4096 的整数倍,
	 *   所以除最后一块外每块都天然对齐。
	 */
	len = ALIGN(len, logdump_align);

	devsz = i_size_read(bdev->bd_inode);
	if (offset < 0 || (u64)offset + len > (u64)devsz) {
		pr_err("写越界:offset=%lld len=%zu 分区容量=%lld\n",
		       (long long)offset, len, (long long)devsz);
		return -EINVAL;
	}
	if (offset & (logdump_align - 1)) {
		pr_err("偏移没对齐:offset=%lld align=%u\n",
		       (long long)offset, logdump_align);
		return -EINVAL;
	}

	while (done < len) {
		size_t chunk = min_t(size_t, len - done,
				     (size_t)LOGDUMP_MAX_BIO_PAGES * PAGE_SIZE);
		unsigned int nr = DIV_ROUND_UP(chunk, PAGE_SIZE);
		struct bio *bio = bio_alloc(GFP_NOIO, nr);
		size_t i;
		int ret;

		if (!bio)
			return -ENOMEM;

		bio_set_dev(bio, bdev);
		bio->bi_iter.bi_sector = (offset + done) >> 9;
		bio->bi_opf = REQ_OP_WRITE | REQ_SYNC;

		for (i = 0; i < chunk; i += PAGE_SIZE) {
			void *va = (char *)buf + done + i;
			size_t n = min_t(size_t, chunk - i, PAGE_SIZE);
			struct page *pg = vmalloc_to_page(va);

			if (!pg ||
			    !bio_add_page(bio, pg, n, (unsigned long)va & ~PAGE_MASK)) {
				bio_put(bio);
				return -EFAULT;
			}
		}

		ret = submit_bio_wait(bio);
		bio_put(bio);
		if (ret)
			return ret;
		done += chunk;
	}

	/* 关键:落盘。硬复位时数据可能还在设备缓存里 */
	return blkdev_issue_flush(bdev, GFP_NOIO, NULL);
}

/*
 * 采集内核日志。d 必须是【当前处于 dump 上下文】的 dumper,或者我们手动
 * 置位 active 的 dumper(周期路径就是后者)。
 */
static size_t logdump_collect(struct kmsg_dumper *d, char *buf, size_t max)
{
	size_t len = 0;

	if (!d || !buf || !max)
		return 0;

	/*
	 * ★ 核心修复:kmsg_dump_get_buffer() 第一步就是
	 *     if (!dumper->active) goto out;
	 *   而 active 只在 kmsg_dump() 内部被置位 —— 所以从 workqueue 直接
	 *   调用永远拿不到数据(这就是 v1~v3 全是 0 的根因)。
	 *   这里自己置位 + rewind,取完再复位。
	 */
	d->active = true;
	kmsg_dump_rewind(d);
	(void)kmsg_dump_get_buffer(d, true, buf, max, &len);
	d->active = false;

	return len;
}

/* 兜底:走 syslog 内核接口(set_fs 让 KERNEL_DS 下的 copy_to_user 成立) */
static size_t logdump_collect_syslog(char *buf, size_t max)
{
	mm_segment_t old_fs;
	int n;

	if (!buf || !max)
		return 0;

	old_fs = get_fs();
	set_fs(KERNEL_DS);
	n = do_syslog(SYSLOG_ACTION_READ_ALL, (char __user *)buf, (int)max,
		      SYSLOG_FROM_PROC);
	set_fs(old_fs);

	if (n <= 0)
		return 0;
	return (size_t)n;
}

/* 写一条状态记录(证明"驱动跑过") */
static void logdump_write_status(u32 count, u32 seq, int errcode, size_t len,
				 u32 source, u32 reason, const char *tag)
{
	struct logdump_stat *st;
	int ret;

	if (!logdump_buf)
		return;

	st = (struct logdump_stat *)logdump_buf;	/* 复用缓冲第 0 页 */
	memset(st, 0, LOGDUMP_STATUS_MAX);
	memcpy(st->magic, LOGDUMP_STAT_MAGIC, sizeof(st->magic));
	st->seq = seq;
	st->count = count;
	st->errcode = errcode;
	st->len = (u32)len;
	st->source = source;
	st->reason = reason;
	st->uptime_ms = logdump_uptime_ms();
	st->jif = get_jiffies_64();
	scnprintf(st->text, sizeof(st->text),
		  "%s cnt=%u seq=%u src=%u len=%u err=%d uptime=%llums",
		  tag, count, seq, source, (u32)len, errcode,
		  (unsigned long long)st->uptime_ms);

	/* 整页写出(4096 字节,天然是逻辑块大小的整数倍) */
	ret = logdump_write(LOGDUMP_STAT_OFFSET, logdump_buf, LOGDUMP_STATUS_MAX);
	if (ret)
		pr_err("写状态记录失败 ret=%d\n", ret);
}

/*
 * 写一份日志:buf 里 [text_off - 512, text_off) 是头区,[text_off, ...) 是正文。
 * text_off 必须是 512 的整数倍且头区在同一块 vmalloc 缓冲内。
 */
static int logdump_write_log(char *buf, size_t text_off, size_t len, u32 seq,
			     u32 source, u32 reason)
{
	struct logdump_hdr *h;
	size_t total;
	int ret;

	if (!buf || !len)
		return -EINVAL;

	if (len > LOGDUMP_TEXT_MAX)
		len = LOGDUMP_TEXT_MAX;

	h = (struct logdump_hdr *)(buf + text_off - LOGDUMP_HDR_MAX);
	memset(h, 0, LOGDUMP_HDR_MAX);
	memcpy(h->magic, LOGDUMP_MAGIC, sizeof(h->magic));
	h->seq = seq;
	h->len = (u32)len;
	h->source = source;
	h->reason = reason;
	h->uptime_ms = logdump_uptime_ms();
	h->sum = logdump_sum(buf + text_off, len);

	/* 尾部补零:既要避免上一轮更长的内容残留,也要满足逻辑块对齐 */
	total = ALIGN(LOGDUMP_HDR_MAX + len, logdump_align);
	if (total > LOGDUMP_HDR_MAX + len)
		memset(buf + text_off + len, 0, total - LOGDUMP_HDR_MAX - len);

	ret = logdump_write(LOGDUMP_LOG_OFFSET, h, total);
	/* ★ 开机早期快照(4s):保住 PHY/regulator/dwc3 探针那几行(刷回原厂后仍可读) */
	if (!logdump_early_done && logdump_uptime_ms() >= LOGDUMP_EARLY_MS) {
		/* v4.10:写成功才置位;失败下一轮重试(否则 6s 现场永远丢) */
		if (!logdump_write(LOGDUMP_EARLY_OFFSET, h, total)) {
			logdump_early_done = true;
			pr_emerg("logdump: 已写入开机早期快照(%llums, 36MB 偏移)\n",
				 (unsigned long long)logdump_uptime_ms());
		}
	}
	/* ★ 模块装载期快照(11s):抓住 4~11s —— 必须在启动中期那次大转储(实测 12.36s 起)
	 *   冲掉环缓冲之前落盘,否则 /proc/modules 与 modprobe 的错误行永远读不到。 */
	if (!logdump_early2_done && logdump_uptime_ms() >= LOGDUMP_EARLY2_MS) {
		if (!logdump_write(LOGDUMP_EARLY2_OFFSET, h, total)) {
			logdump_early2_done = true;
			pr_emerg("logdump: 已写入模块装载期快照(%llums, 40MB 偏移)\n",
				 (unsigned long long)logdump_uptime_ms());
		}
	}
	/* ★ 卡死瞬间(≥55s)把同一份正文另存到 32MB,刷回原厂后仍能读回现场 */
	if (!logdump_snap2_done && logdump_uptime_ms() >= LOGDUMP_SNAP2_MS) {
		logdump_snap2_done = true;
		if (logdump_write(LOGDUMP_SNAP2_OFFSET, h, total))
			pr_err("现场快照写入失败\n");
		else
			pr_emerg("logdump: 已在 %llums 写入现场快照(32MB 偏移)\n",
				 (unsigned long long)logdump_uptime_ms());
	}
	if (ret) {
		pr_err("写日志失败 seq=%u len=%zu src=%u ret=%d\n",
		       seq, len, source, ret);
	} else if (!logdump_first_ok) {
		logdump_first_ok = true;
		pr_info("首次落盘成功:seq=%u len=%zu src=%u\n", seq, len, source);
	} else {
		pr_debug("写日志成功 seq=%u len=%zu src=%u\n", seq, len, source);
	}

	return ret;
}

/* 把崩溃回调排下的快照落盘(必须在 workqueue 上下文、持 logdump_mutex) */
static void logdump_flush_snapshot(void)
{
	unsigned long flags;
	bool pending;
	size_t len;
	u32 seq, reason;

	spin_lock_irqsave(&logdump_snap_lock, flags);
	pending = logdump_snap_pending;
	len = logdump_snap_len;
	seq = logdump_snap_seq;
	reason = logdump_snap_reason;
	logdump_snap_pending = false;
	spin_unlock_irqrestore(&logdump_snap_lock, flags);

	if (!pending || !len)
		return;

	logdump_write_status(logdump_count, seq, 0, len, LOGDUMP_SRC_CALLBACK,
			     reason, "snap-begin");
	logdump_write_log(logdump_snap, LOGDUMP_OFF_SNAP_TEXT, len, seq,
			  LOGDUMP_SRC_CALLBACK, reason);
	logdump_write_status(logdump_count, seq, 0, len, LOGDUMP_SRC_CALLBACK,
			     reason, "snap-done");
	pr_emerg("崩溃快照已落盘:seq=%u reason=%u len=%zu\n",
		 seq, reason, len);
}

/*
 * ★ 崩溃路径回调:只做"拷贝 + 排队",绝不在这里做块层 I/O。
 *   (panic/restart 上下文可能原子化,submit_bio_wait 会睡眠)
 */
static void logdump_dump(struct kmsg_dumper *dumper, enum kmsg_dump_reason reason)
{
	size_t len;

	if (!logdump_snap)
		return;

	len = logdump_collect(dumper, logdump_snap + LOGDUMP_OFF_SNAP_TEXT,
			      LOGDUMP_TEXT_MAX);
	if (!len)
		return;

	spin_lock(&logdump_snap_lock);
	logdump_snap_len = len;
	logdump_snap_seq = ++logdump_seq;
	logdump_snap_reason = (u32)reason;
	logdump_snap_pending = true;
	spin_unlock(&logdump_snap_lock);

	pr_emerg("dump 回调 reason=%d:已拷入静态快照 len=%zu,排队到 workqueue 落盘\n",
		 (int)reason, len);
	schedule_work(&logdump_dump_work);

	/*
	 * RESTART / HALT / POWEROFF 是【进程上下文】里发起的(reboot 系统调用 /
	 * init 的 powerctl),睡眠是安全的 ⇒ 直接等落盘完成,避免"排了队但设备
	 * 已经复位、work 还没跑完"(v4 第一版尾部丢失就是这个竞态 + 对齐问题)。
	 * ⚠️ PANIC / OOPS 上下文绝不做这件事:那时其它 CPU 已停、workqueue 可能
	 *    永远不会被调度,flush_work() 就是死锁。
	 */
	if (reason >= KMSG_DUMP_RESTART) {
		pr_emerg("dump 回调:等 workqueue 落盘完成(进程上下文,可睡眠)\n");
		flush_work(&logdump_dump_work);
	}
}

static void logdump_dump_work_fn(struct work_struct *w)
{
	mutex_lock(&logdump_mutex);
	logdump_flush_snapshot();
	mutex_unlock(&logdump_mutex);
}

/*
 * ★★★ 日志停涨检测 —— 我们遇到的是"内核硬挂、日志戛然而止"。
 *   如果内核其实还活着(只是某个任务卡死/拿不到锁),那么把【所有任务的状态和栈】
 *   打进内核日志,下一轮采集就会一起落盘 ⇒ 直接看到是谁卡在哪里。
 *   实测 2026-10-02:换成内建 GPU 固件后,内核算到 4.3~4.4 秒就再没有任何输出。
 */
static void logdump_check_stuck(void)
{
	u64 now = logdump_uptime_ms();

	if (logdump_prev_len != logdump_prev2_len) {
		/* 还在长 ⇒ 正常 */
		logdump_len_same_since_ms = now;
		return;
	}
	if (now < 3000 || !logdump_len_same_since_ms)
		return;
	if (now - logdump_len_same_since_ms < 1500)
		return;
	if (now - logdump_last_dump_ms < 2000)
		return;
	/* v4.10:任务转储只做一次 —— 反复转储会把 ring 冲爆,早期日志就没了 */
	if (logdump_statedump_done)
		return;

	logdump_last_dump_ms = now;
	logdump_statedump_done = true;
	pr_emerg("logdump: 日志已 %llums 无增长(len=%zu, uptime=%llums)⇒ Dump 全部任务状态\n",
		 now - logdump_len_same_since_ms, logdump_prev_len, now);
	/*
	 * v4.10 诊断:先打印 module_mutex 持有者与所有模块状态。
	 * 模块加载死锁时,这是唯一能直接指出"谁拿着锁/谁卡在 COMING"的信息。
	 */
	{
		struct task_struct *o = moddbg_mutex_owner();

		/* 防御:owner 低位已被 mask,但若是野指针就别解引用 */
		if ((unsigned long)o < 0xffff000000000000UL)
			o = NULL;
		pr_emerg("MODDBG: module_mutex owner=%px comm=%s pid=%d state=%ld\n",
			 o, o ? o->comm : "-", o ? task_pid_nr(o) : 0,
			 o ? (long)o->state : 0L);
		if (o)
			sched_show_task(o);
	}
	moddbg_dump();
	show_state_filter(0);
}

/* ══════════════════════════════════════════════════════════════════════════
 * ★★ 2026-10-06:自编内核自救 —— 「没有通道就自己切回另一个槽」
 * ══════════════════════════════════════════════════════════════════════════
 * 现场(run157 真机):自编内核能启动进 MIUI,但
 *   · 没有 USB —— 内核日志 `USB cable not connected` + `gcc_usb30_prim_gdsc: disabling`,
 *     gadget 永不启动(wait:根因在 VBUS/充电链,不是 dwc3 本身)
 *   · 没有 WiFi —— 配方故意拦掉 WLAN 模块(mod-blacklist 只拦 qca_cld3_* 、cnss2、icnss2)
 *   · 没有触屏 —— 见 §18
 *   ⇒ 主机【完全没有通道】,只能等人工"音量下+电源进 fastboot + 插拔 USB"。
 *
 * 为什么不能靠别人:
 *   · 用户态看门狗(/data/adb/post-fs-data.d)由 APatch 执行;自编内核不带 APatch
 *     ⇒ 钩子根本不跑。
 *   · ABL 自带的重试回退不认这种失败:Android 能起来 ⇒ 该槽被标 successful ⇒
 *     slot-retry-count 永不扣 ⇒ 永远不回退。
 *   ⇒ 只能由内核自己动手。
 *
 * 落点:ABL 的槽位元数据在 GPT 分区表项【属性字段第 7 字节】(属性 bits 48..55)
 *     bits48-49 priority(2bit) | bit50 ACTIVE | bits51-53 retry(3bit)
 *     bit54 successful | bit55 unbootable
 *   双源背书:lk2nd `platform/msm_shared/include/partition_parser.h`
 *            + AOSP `hardware/qcom/bootctrl` `gpt-utils.h`(AB_FLAG_OFFSET = 54)。
 *   本机实测(与 `fastboot getvar all` 逐项相符,读数见 §18.6):
 *     boot_a 属性 0x0077000000000000 → AB 字节 0x77 = prio3|ACTIVE|retry6|successful|bootable
 *     boot_b 属性 0x0032000000000000 → AB 字节 0x32 = prio2|inactive|retry6|!successful|bootable
 *
 * 触发:uptime ≥ LOGDUMP_RESCUE_MS 且日志里【没有任何 USB 枚举痕迹】
 *   ("USB_STATE=CONFIGURED" / "configfs-gadget" / "MARS_USB_ENUM_OK")。
 *   好内核 10 秒内一定打出这些行(原厂对照:10.33s `configfs-gadget ... config #1`)
 *   ⇒ 不会误触发;每轮启动最多动作一次。
 *
 * 动作:ACTIVE 挪到另一个槽、把那个槽 retry 拉满 7、清它的 unbootable;
 *   把当前槽标成 unbootable(免得下次又启动这个坏内核)⇒ 改完重算两处 CRC32
 *   写回主/备 GPT ⇒ kernel_restart(NULL) 立即重启。
 *
 * ★ 防乒乓:目标槽若已经是 unbootable,就【不动作】(只记日志)。这样"两槽都是
 *   坏内核"时会停下来等人工,而不是无限对切。
 * ★ 安全:只改属性字节,不改任何 LBA ⇒ 内核内存里的分区表不用 partprobe;
 *   重启后由 ABL 重新读 GPT。写坏也只影响"下次从哪个槽启动",不会动数据分区。
 */
#define LOGDUMP_RESCUE_MS	90000
#define LOGDUMP_GPT_LBA		4096		/* sde 逻辑块 4096(下面用实际值兜底) */
#define LOGDUMP_GPT_ATTR_BYTE	54		/* 表项内属性字段第 7 字节 = bits48..55 */
#define LOGDUMP_GPT_ACTIVE	0x04
#define LOGDUMP_GPT_RETRY_MASK	0x38		/* bits51..53 */
#define LOGDUMP_GPT_RETRY_FULL	0x38
#define LOGDUMP_GPT_UNBOOTABLE	0x80

static bool logdump_rescue_slot = true;
module_param(logdump_rescue_slot, bool, 0644);
MODULE_PARM_DESC(logdump_rescue_slot,
	"没有 USB 枚举时自动把 ACTIVE 槽切到另一个槽并重启(自编内核自救)");

static bool logdump_rescue_done;
/*
 * ★ 必须"看到就锁存":日志环缓冲只有 256KB,启动中期一次任务转储就能把
 *   10 秒时那条 USB 枚举行冲掉 —— 若等到 90 秒再去日志里找,会误判成"没枚举"
 *   而把好内核切走。logdump 每 100ms 一轮,一定能在它出现时就抓住。
 */
static bool logdump_usb_seen;

static u32 logdump_crc32(u32 crc, const void *p, size_t len)
{
	return crc32_le(crc, p, len);
}

/* 把 GPT 头里的 4 字节 CRC 字段清零后,按 header_size 重算并写回 */
static void logdump_gpt_fix_hdr_crc(u8 *h)
{
	u32 hsize, crc;

	memcpy(&hsize, h + 12, 4);
	if (hsize < 92 || hsize > LOGDUMP_GPT_LBA)
		hsize = 92;
	memset(h + 16, 0, 4);
	crc = logdump_crc32(0xFFFFFFFFu, h, hsize) ^ 0xFFFFFFFFu;
	memcpy(h + 16, &crc, 4);
}

/* 按 UTF-16LE 比较分区名(表项 +56,最多 36 个 UTF-16 字符) */
static bool logdump_gpt_name_is(const u8 *entry, const char *name)
{
	size_t i, n = strlen(name);

	for (i = 0; i < n; i++) {
		if (entry[56 + i * 2] != (u8)name[i] || entry[56 + i * 2 + 1] != 0)
			return false;
	}
	return entry[56 + n * 2] == 0 && entry[56 + n * 2 + 1] == 0;
}

/*
 * 返回 true 表示"已经完成切槽并准备重启"(调用方负责 kernel_restart)。
 * 只在 kthread 上下文调用(会睡眠)。
 */
static bool logdump_slot_rescue(void)
{
	struct file *f;
	u8 *hdr = NULL, *hdr2 = NULL, *ent = NULL;
	loff_t pos;
	u64 pe_lba, alt_lba;
	u32 nparts, esize, ent_len;
	int i, cur = -1, tgt = -1;
	bool ok = false;

	f = filp_open("/dev/block/sde", O_RDWR | O_LARGEFILE, 0);
	if (IS_ERR(f)) {
		pr_err("logdump-rescue: 打不开 /dev/block/sde (%ld)\n", PTR_ERR(f));
		return false;
	}

	hdr = kmalloc(LOGDUMP_GPT_LBA, GFP_KERNEL);
	hdr2 = kmalloc(LOGDUMP_GPT_LBA, GFP_KERNEL);
	if (!hdr || !hdr2)
		goto out;

	pos = LOGDUMP_GPT_LBA;
	if (kernel_read(f, hdr, LOGDUMP_GPT_LBA, &pos) != LOGDUMP_GPT_LBA ||
	    memcmp(hdr, "EFI PART", 8)) {
		pr_err("logdump-rescue: 主 GPT 头读不到/签名不对\n");
		goto out;
	}
	memcpy(&pe_lba, hdr + 72, 8);
	memcpy(&nparts, hdr + 80, 4);
	memcpy(&esize, hdr + 84, 4);
	memcpy(&alt_lba, hdr + 32, 8);
	if (!pe_lba || !nparts || esize < 128 || esize > 4096 || nparts > 512) {
		pr_err("logdump-rescue: GPT 头字段异常(pe_lba=%llu nparts=%u esize=%u)\n",
		       (unsigned long long)pe_lba, nparts, esize);
		goto out;
	}
	ent_len = nparts * esize;
	if (ent_len > 256 * 1024) {
		pr_err("logdump-rescue: 表项太大 %u\n", ent_len);
		goto out;
	}
	ent = kmalloc(ent_len, GFP_KERNEL);
	if (!ent)
		goto out;

	pos = pe_lba * LOGDUMP_GPT_LBA;
	if (kernel_read(f, ent, ent_len, &pos) != ent_len) {
		pr_err("logdump-rescue: 表项读不出\n");
		goto out;
	}

	for (i = 0; i < nparts; i++) {
		u8 *e = ent + i * esize;
		u8 ab;

		if (e[0] == 0 && e[1] == 0)
			continue;
		if (logdump_gpt_name_is(e, "boot_a"))
			cur = i;
		else if (logdump_gpt_name_is(e, "boot_b"))
			tgt = i;
		ab = e[LOGDUMP_GPT_ATTR_BYTE];
		(void)ab;
	}
	if (cur < 0 || tgt < 0) {
		pr_err("logdump-rescue: 找不到 boot_a/boot_b(cur=%d tgt=%d)\n", cur, tgt);
		goto out;
	}

	{
		u8 *ea = ent + cur * esize, *eb = ent + tgt * esize;
		u8 a = ea[LOGDUMP_GPT_ATTR_BYTE], b = eb[LOGDUMP_GPT_ATTR_BYTE];
		bool a_active = (a & LOGDUMP_GPT_ACTIVE) != 0;
		int from, to;
		u8 *efrom, *eto;

		/* 以 ACTIVE 位判断当前槽(与 fastboot getvar current-slot 一致) */
		if (a_active) { from = cur; to = tgt; efrom = ea; eto = eb; }
		else          { from = tgt; to = cur; efrom = eb; eto = ea; }

		pr_emerg("logdump-rescue: 现状 boot_a=0x%02x boot_b=0x%02x(ACTIVE 在 %s)\n",
			 a, b, from == cur ? "a" : "b");

		if (eto[LOGDUMP_GPT_ATTR_BYTE] & LOGDUMP_GPT_UNBOOTABLE) {
			pr_emerg("logdump-rescue: 目标槽已是 unbootable ⇒ 不动作(防乒乓,等人工)\n");
			goto out;
		}

		/* 当前槽:清 ACTIVE + 标 unbootable —— 下次别再启动这个坏内核 */
		efrom[LOGDUMP_GPT_ATTR_BYTE] &= (u8)~LOGDUMP_GPT_ACTIVE;
		efrom[LOGDUMP_GPT_ATTR_BYTE] |= LOGDUMP_GPT_UNBOOTABLE;
		/* 目标槽:置 ACTIVE + 清 unbootable + retry 拉满 7 */
		eto[LOGDUMP_GPT_ATTR_BYTE] |= LOGDUMP_GPT_ACTIVE;
		eto[LOGDUMP_GPT_ATTR_BYTE] &= (u8)~LOGDUMP_GPT_UNBOOTABLE;
		eto[LOGDUMP_GPT_ATTR_BYTE] = (eto[LOGDUMP_GPT_ATTR_BYTE] & ~LOGDUMP_GPT_RETRY_MASK)
					    | LOGDUMP_GPT_RETRY_FULL;
		pr_emerg("logdump-rescue: 切换 ACTIVE %s→%s;boot_a=0x%02x boot_b=0x%02x\n",
			 from == cur ? "a" : "b", to == cur ? "a" : "b",
			 ea[LOGDUMP_GPT_ATTR_BYTE], eb[LOGDUMP_GPT_ATTR_BYTE]);
	}

	/* 表项 CRC 写进两份头 */
	{
		u32 ecrc = logdump_crc32(0xFFFFFFFFu, ent, ent_len) ^ 0xFFFFFFFFu;
		memcpy(hdr + 88, &ecrc, 4);
	}

	/* 读备头 → 同步表项 CRC → 各自重算头 CRC */
	pos = alt_lba * LOGDUMP_GPT_LBA;
	if (kernel_read(f, hdr2, LOGDUMP_GPT_LBA, &pos) != LOGDUMP_GPT_LBA ||
	    memcmp(hdr2, "EFI PART", 8)) {
		pr_err("logdump-rescue: 备份 GPT 头读不到/签名不对,只写主份\n");
		logdump_gpt_fix_hdr_crc(hdr);
		pos = pe_lba * LOGDUMP_GPT_LBA;
		if (kernel_write(f, ent, ent_len, &pos) != ent_len)
			goto out;
		pos = LOGDUMP_GPT_LBA;
		if (kernel_write(f, hdr, LOGDUMP_GPT_LBA, &pos) != LOGDUMP_GPT_LBA)
			goto out;
		vfs_fsync(f, 0);
		ok = true;
		goto out;
	}
	memcpy(hdr2 + 88, hdr + 88, 4);
	logdump_gpt_fix_hdr_crc(hdr);
	logdump_gpt_fix_hdr_crc(hdr2);

	/* 写序:先备份(表项→头),再主份(表项→头) */
	pos = alt_lba * LOGDUMP_GPT_LBA - ent_len;
	if (kernel_write(f, ent, ent_len, &pos) != ent_len) {
		pr_err("logdump-rescue: 写备份表项失败\n");
		goto out;
	}
	pos = alt_lba * LOGDUMP_GPT_LBA;
	if (kernel_write(f, hdr2, LOGDUMP_GPT_LBA, &pos) != LOGDUMP_GPT_LBA) {
		pr_err("logdump-rescue: 写备份头失败\n");
		goto out;
	}
	vfs_fsync(f, 0);
	pos = pe_lba * LOGDUMP_GPT_LBA;
	if (kernel_write(f, ent, ent_len, &pos) != ent_len) {
		pr_err("logdump-rescue: 写主表项失败\n");
		goto out;
	}
	pos = LOGDUMP_GPT_LBA;
	if (kernel_write(f, hdr, LOGDUMP_GPT_LBA, &pos) != LOGDUMP_GPT_LBA) {
		pr_err("logdump-rescue: 写主头失败\n");
		goto out;
	}
	vfs_fsync(f, 0);
	pr_emerg("logdump-rescue: ✅ 主/备 GPT 已更新并落盘\n");
	ok = true;
out:
	kfree(ent);
	kfree(hdr2);
	kfree(hdr);
	filp_close(f, NULL);
	return ok;
}

static void logdump_once(void)
{
	char *text = logdump_buf ? logdump_buf + LOGDUMP_OFF_TEXT : NULL;
	size_t len = 0;
	u32 count, seq;
	u32 source = 0;
	int ret = 0;

	mutex_lock(&logdump_mutex);

	if (!logdump_get_bdev()) {
		mutex_unlock(&logdump_mutex);
		return;
	}

	count = ++logdump_count;
	seq = ++logdump_seq;

	/* 0) 日志停涨(疑似卡死)⇒ 先把所有任务状态打进日志,本轮的采集就会带上它 */
	logdump_check_stuck();


	/* 1) 先把上一轮崩溃回调留下的快照落盘(那才是真正的现场) */
	logdump_flush_snapshot();

	/* 2) 周期采集 */
	len = logdump_collect(&logdump_reader, text, LOGDUMP_TEXT_MAX);
	if (len) {
		source = LOGDUMP_SRC_PERIODIC;
	} else {
		len = logdump_collect_syslog(text, LOGDUMP_TEXT_MAX);
		if (len)
			source = LOGDUMP_SRC_SYSLOG;
	}

	/*
	 * 3) 两条都拿不到(理论上不该发生):按间隔走正式 kmsg_dump() 入口,
	 *    让注册的回调把快照排队落盘;顺带原厂 mtdoops 会把日志写进
	 *    sda15 的 LAST KMSG 区(另一条可读通道)。
	 */
	if (!len && (count % LOGDUMP_KMSGDMP_EVERY) == 1) {
		kmsg_dump(KMSG_DUMP_OOPS);
		logdump_flush_snapshot();
		if (!source)
			source = LOGDUMP_SRC_KMSGDMP;
	}

	/* 3.5) 判断启动是否成功(只看日志尾部 64KB,足够看到最新消息) */
	if (!logdump_boot_done && len) {
		const char *tail = text + (len > 65536 ? len - 65536 : 0);
		size_t tlen = len > 65536 ? 65536 : len;

		if (logdump_memstr(tail, tlen, "Boot completed")) {
			logdump_boot_done = true;
			pr_info("logdump: 检测到 Boot completed,关闭自动进 fastboot\n");
		}
		/*
		 * ★ v4.8 修错判:只能在【同一行】里同时出现 surfaceflinger 和
		 *   "received signal" 才算一次 SF 崩溃,而且只统计【新增长的那段】。
		 *   旧版(v4.6/4.7)是在整块 tail 里各找一个子串 ⇒ 相机崩溃的
		 *   `received signal 6` + logcat 镜像里任意含 surfaceflinger 的行
		 *   (例如 "ctl.start for 'bootanim' ... (/system/bin/surfaceflinger)")
		 *   就凑成一次 ⇒ 54 次假崩溃 ⇒ 45 秒把【已经正常启动】的内核
		 *   重启进 fastboot(2026-10-02 01:43 实测踩到)。
		 */
		if (len < logdump_sf_scan_off)
			logdump_sf_scan_off = 0;	/* 日志环形缓冲绕过一圈了 */
		if (len > logdump_sf_scan_off) {
			logdump_sf_crashes +=
				logdump_count_sf_crash(text + logdump_sf_scan_off,
						       len - logdump_sf_scan_off);
			logdump_sf_scan_off = len;
		}
	}

	/* 4) 落盘:先记"本轮开始",再写日志,最后记结果 */
	logdump_write_status(count, seq, 0, len, source, 0, "begin");
	if (len)
		ret = logdump_write_log(logdump_buf, LOGDUMP_OFF_TEXT, len, seq,
					source, 0);
	logdump_write_status(count, seq, ret, len, source, 0,
			     ret ? "log-fail" : "ok");

	/* 记录本轮长度,供下一轮判断"日志是否停涨" */
	logdump_prev2_len = logdump_prev_len;
	logdump_prev_len = len;

	mutex_unlock(&logdump_mutex);

	/*
	 * ★ 5) 启动失败 ⇒ 自动重启到 bootloader(fastboot)。
	 *   注意:必须在本轮日志【已经落盘之后】再做,否则会丢掉最后的现场。
	 */
	/*
	 * ★★ 2026-10-06:自编内核自救 —— 优先级【高于】下面那个"自动进 fastboot"。
	 *   理由:进 fastboot 需要人工插拔(实测:设备切到 bootloader 时从 USB 总线
	 *   掉下来,主机看不到它),而切回另一个槽能自动回到一个"有 root、有 adb"
	 *   的系统。判据只看"这一轮启动里有没有出现过 USB 枚举痕迹"(锁存,见上)。
	 */
	if (!logdump_usb_seen && len &&
	    (logdump_memstr(text, len, "USB_STATE=CONFIGURED") ||
	     logdump_memstr(text, len, "configfs-gadget") ||
	     logdump_memstr(text, len, "MARS_USB_ENUM_OK"))) {
		logdump_usb_seen = true;
		pr_emerg("logdump-rescue: 已看到 USB 枚举痕迹(uptime=%llums),自救不触发\n",
			 logdump_uptime_ms());
	}
	if (logdump_rescue_slot && !logdump_rescue_done && !logdump_usb_seen &&
	    logdump_uptime_ms() >= LOGDUMP_RESCUE_MS) {
		logdump_rescue_done = true;
		pr_emerg("logdump-rescue: uptime=%llums 仍无任何 USB 枚举痕迹"
			 " ⇒ 判定本内核起不来通道,切槽自救\n", logdump_uptime_ms());
		logdump_write_status(count, seq, 0, len, source, 0, "slot-rescue");
		if (logdump_slot_rescue()) {
			pr_emerg("logdump-rescue: GPT 已改,准备重启到另一个槽\n");
			msleep(500);
			kernel_restart(NULL);
		} else {
			pr_err("logdump-rescue: 切槽失败,放弃自动路径(等人工)\n");
		}
	}
	if (logdump_auto_fastboot && !logdump_boot_done && !logdump_auto_fb_done) {
		u64 up = logdump_uptime_ms();
		bool timeout_fail = up > LOGDUMP_BOOT_TIMEOUT_MS;
		bool crash_fail = logdump_sf_crashes >= LOGDUMP_SF_CRASH_LIMIT &&
				  up > LOGDUMP_SF_CRASH_UPTIME;

		if (timeout_fail || crash_fail) {
			logdump_auto_fb_done = true;
			pr_emerg("logdump: 判定启动失败(%s: uptime=%llums, sf_crash=%d)"
				 "⇒ 自动重启到 bootloader 进 FASTBOOT\n",
				 timeout_fail ? "超时未见 Boot completed" : "surfaceflinger 反复崩溃",
				 up, logdump_sf_crashes);
			logdump_write_status(count, seq, 0, len, source, 0, "auto-fastboot");
			kernel_restart("bootloader");
		}
	}
}

/*
 * ★★ 用【专用内核线程】而不是 workqueue:
 *   实测 2026-10-02:换成内建 GPU 固件后,内核在 4.3~6.3 秒之间硬挂死,
 *   2 秒一轮的 workqueue 写盘刚好错过现场(v4.2 日志只有 1 轮、停在 4.32s)。
 *   workqueue 会被其它长时间睡眠的任务/被卡住的 worker 拖住,
 *   专用 kthread 至少能在"部分卡死"时继续把最后现场写上盘。
 */
static int logdump_thread_fn(void *data)
{
	while (!kthread_should_stop()) {
		logdump_once();
		/* 心跳:每 10 轮(≈5 秒)在日志里留一行,便于判断"内核还活着" */
		if ((logdump_count % 60) == 0) {
			pr_info("logdump: 心跳 #%u uptime=%llums\n",
				logdump_count, logdump_uptime_ms());
			/*
			 * ★★ v4.12:心跳顺便打一帧【模块表状态】。
			 *   2026-10-03 实测:内核在 ~15.6s 硬卡死(看门狗复位),
			 *   卡死瞬间 logdump 线程也跑不动 ⇒ 靠"日志停涨"触发的任务转储
			 *   根本来不及写。每 5 秒一帧模块状态,至少能看到最后一帧里
			 *   哪些模块 LIVE、哪些 COMING/UNFORMED。
			 */
			moddbg_dump();
		}
		/*
		 * ★ 每 50 轮(≈5~25 秒)打印一次【已加载模块列表】:
		 *   排查"模块到底装上没有"时,内核 WARN dump 不一定发生,
		 *   而 print_modules() 会把 "Modules linked in: ..." 写进日志,
		 *   我们的采集就能把它落盘。
		 */
		if ((logdump_count % 100) == 0)   /* v4.13:别再刷屏 */
			print_modules();
		/*
		 * ★★★ v4.7:
		 *   3.2 秒 → 强制 SELinux permissive(必须在 spawn 之前)
		 *   4.6 秒 → spawn 用户态采集脚本;失败则每 2.5 秒重试,最多 4 次
		 *  (logd 4.11 秒才起来,脚本内部还会等 /dev/socket/logdr)
		 */
		{
			u64 up = logdump_uptime_ms();

			if (logdump_force_permissive && !logdump_perm_done &&
			    up >= 3200) {
				logdump_perm_done = true;
				logdump_set_permissive();
			}
			if (logdump_spawn_helper && !logdump_helper_done &&
			    up >= 4600 && logdump_helper_tries < 4 &&
			    (up - logdump_helper_last_ms) >= 2500) {
				logdump_helper_last_ms = up;
				logdump_spawn_userspace();
			}
		}
		/*
		 * 分级周期:
		 *   前 15 秒 → 100ms(抓"4~5 秒就硬挂"这种早期现场,2 秒/500ms 都会错过)
		 *   15~180 秒 → 500ms
		 *   之后 → 10 秒(避免正常长时间运行时一直密写 UFS 磨损闪存)
		 */
		{
			u64 up = logdump_uptime_ms();
			/*
			 * ★★ v4.13(2026-10-03):把节奏放松回来。
			 *   实测教训:前 15 秒每 100ms 写一次(正文上限 2MB)
			 *   ⇒ 峰值 ~20MB/s 持续写 UFS,且叠加每 2.5s print_modules()
			 *   + 每 5s 一帧模块表 ⇒ 正好砸在启动期 I/O 最紧张的那 10 秒
			 *   (zygote/system_server/dex2oat 都在读写)⇒ 卡住 ⇒ 看门狗复位。
			 *   而更早"能进 MIUI"的版本是 512KB / 500ms。
			 *   现在:1s / 3s / 30s + 正文 512KB + 转储只在疑似卡死时做一次。
			 */
			msleep(up < 15000 ? 1000 :
			       (up < 180000 ? 3000 : 30000));
		}
	}
	return 0;
}

static void logdump_work_fn(struct work_struct *w)
{
	logdump_once();
	queue_delayed_work(system_wq, &logdump_work,
			   msecs_to_jiffies(LOGDUMP_PERIOD_MS * 4));
}

static int __init logdump_init(void)
{
	logdump_buf = vmalloc(LOGDUMP_BUF_SIZE);
	logdump_snap = vmalloc(LOGDUMP_SNAP_SIZE);
	if (!logdump_buf || !logdump_snap) {
		pr_err("分配缓冲区失败\n");
		vfree(logdump_buf);
		vfree(logdump_snap);
		logdump_buf = NULL;
		logdump_snap = NULL;
		return -ENOMEM;
	}

	logdump_dumper.dump = logdump_dump;
	if (kmsg_dump_register(&logdump_dumper)) {
		pr_err("kmsg_dump_register 失败\n");
		return -EBUSY;
	}

	INIT_DELAYED_WORK(&logdump_work, logdump_work_fn);
	INIT_WORK(&logdump_dump_work, logdump_dump_work_fn);

	queue_delayed_work(system_wq, &logdump_work, msecs_to_jiffies(1000));

	logdump_thread = kthread_run(logdump_thread_fn, NULL, "logdump");
	if (IS_ERR(logdump_thread)) {
		pr_err("创建 logdump 线程失败 %ld\n", PTR_ERR(logdump_thread));
		logdump_thread = NULL;
	}

	pr_info("v4.8 已启用(专用 kthread):每 %u ms 写 %s%d(日志@0、状态@2MB,正文上限 %u KB);"
		"permissive=%d spawn=%d auto_fb=%d\n",
		LOGDUMP_PERIOD_MS, LOGDUMP_DEV_NAME, LOGDUMP_DEV_PART,
		LOGDUMP_TEXT_MAX / 1024,
		(int)logdump_force_permissive, (int)logdump_spawn_helper,
		(int)logdump_auto_fastboot);
	return 0;
}

late_initcall(logdump_init);

MODULE_DESCRIPTION("periodic kernel log dumper for hard-reset debugging");
MODULE_LICENSE("GPL v2");
