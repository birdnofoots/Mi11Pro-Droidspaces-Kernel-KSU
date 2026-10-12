#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
/* 容器 init 包装器 v2:
   - 436(APatch supercall): 带 0x1158 魔数放行, 否则回 ENOSYS
     ⇒ systemd 的 close_range 收 ENOSYS 走 /proc 回退, 服务复活
   - 不设 PR_SET_NO_NEW_PRIVS(避免干扰 binfmt_misc/跨架构 exec); 以 CAP_SYS_ADMIN 装过滤器 */
static void clog(const char *s) {
    int fd = open("/dev/console", O_WRONLY | O_NOCTTY);
    if (fd >= 0) { write(fd, s, strlen(s)); close(fd); }
}
int main(int argc, char **argv) {
    char buf[256];
    struct sock_filter filt[] = {
        BPF_STMT(BPF_LD  | BPF_W | BPF_ABS, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 436, 0, 4),
        BPF_STMT(BPF_LD  | BPF_W | BPF_ABS, 24),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, 0xFFFF0000),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0x11580000, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (38 & 0xFFFF)),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog prog = { .len = sizeof filt / sizeof filt[0], .filter = filt };
    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog)) {
        snprintf(buf, sizeof buf, "nr436-shim: seccomp fail errno=%d, fallback no_new_privs\n", errno);
        clog(buf);
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
        if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog)) {
            snprintf(buf, sizeof buf, "nr436-shim: seccomp2 fail errno=%d\n", errno);
            clog(buf);
        }
    }
    const char *cands[6];
    int n = 0;
    if (argc >= 2) cands[n++] = argv[1];
    cands[n++] = "/sbin/init.real";
    cands[n++] = "/lib/systemd/systemd";
    cands[n++] = "/usr/lib/systemd/systemd";
    cands[n] = NULL;
    char *orig0 = argv[0] ? argv[0] : (char *)"/sbin/init";
    for (int i = 0; i < n; i++) {
        char *av[16];
        av[0] = orig0;                      /* busybox 按 argv[0] 选 applet, 保留原名 */
        int k = 1;
        if (i > 0) { /* 自建候选: 丢掉 droidspaces 的内核式参数 */
            for (int j = 1; j < argc && k < 15; j++)
                if (argv[j][0] >= '0' && argv[j][0] <= '9') av[k++] = argv[j];
        } else {
            for (int j = 1; j < argc && k < 15; j++) av[k++] = argv[j];
        }
        av[k] = NULL;
        execv(cands[i], av);
        snprintf(buf, sizeof buf, "nr436-shim: execv(%s) errno=%d\n", cands[i], errno);
        clog(buf);
    }
    return 5;
}
