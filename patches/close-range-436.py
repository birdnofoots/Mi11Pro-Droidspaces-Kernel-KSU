#!/usr/bin/env python3
# MARS-CLOSE-RANGE-436(2026-10-13) — 恢复 arm64 主线 syscall 编号 + 真 close_range 实现
#
# 病灶: 本 QGKI 树(SM8350, 5.4) 把 process_madvise 抢占了 436 号
#   (主线编号: 436=close_range, 437=openat2, 438=pidfd_getfd, 439=faccessat2, 440=process_madvise)。
#   现代用户态按主线编号: glibc 的 close_range() 调 syscall 436 ⇒ 撞上 process_madvise,
#   收到 EINVAL(而非 ENOSYS) ⇒ glibc 不回退 close-loop ⇒ systemd 的 fd 清理/孵化失败
#   (ExecCondition 202/FDS、dbus/ssh/networkd 全挂、容器拿不到 IP)。
#   这与 root 方案无关(APatch 的 supercall 是加塞 436, KSU 根本没动它)——APatch 下还需
#   nr436-shim, KSU 下用本补丁内核侧根治(容器无需 shim)。
#
# 修法:
#   1) unistd.h: 436 → close_range(新实现); 437-439 → sys_ni_syscall(显式 ENOSYS, 防表项
#      NULL 空洞; 行为与今日的边界检查 ENOSYS 完全一致); 440 → process_madvise(还给主线
#      编号, bionic 的 process_madvise 从此可用); __NR_syscalls → 441。
#   2) fs/file.c: 追加 SYSCALL_DEFINE3(close_range,...) 最小正确实现(flags 仅支持 0)。
#
# 用法: python3 close-range-436.py <kernel-tree>
import sys, os

tree = sys.argv[1]
assert tree and os.path.isdir(tree), "kernel tree path required"

# ---- 1) unistd.h ----
up = os.path.join(tree, "include/uapi/asm-generic/unistd.h")
s = open(up).read()
old = (
    "#define __NR_process_madvise 436\n"
    "__SYSCALL(__NR_process_madvise, sys_process_madvise)\n"
    "\n"
    "#undef __NR_syscalls\n"
    "#define __NR_syscalls 437\n"
)
new = (
    "/* MARS-CLOSE-RANGE-436: 本树曾把 process_madvise 抢占 436(主线 436=close_range,\n"
    " * 440=process_madvise)。glibc close_range() 调 436 撞上 process_madvise 收 EINVAL\n"
    " * (非 ENOSYS) ⇒ 不回退 close-loop ⇒ systemd fd 清理/孵化失败(202/FDS、容器无网)。\n"
    " * 恢复主线编号; 437-439 本树无实现, 显式 ENOSYS(防表项 NULL 空洞)。 */\n"
    "#define __NR_close_range 436\n"
    "__SYSCALL(__NR_close_range, sys_close_range)\n"
    "#define __NR_openat2 437\n"
    "__SYSCALL(__NR_openat2, sys_ni_syscall)\n"
    "#define __NR_pidfd_getfd 438\n"
    "__SYSCALL(__NR_pidfd_getfd, sys_ni_syscall)\n"
    "#define __NR_faccessat2 439\n"
    "__SYSCALL(__NR_faccessat2, sys_ni_syscall)\n"
    "#define __NR_process_madvise 440\n"
    "__SYSCALL(__NR_process_madvise, sys_process_madvise)\n"
    "\n"
    "#undef __NR_syscalls\n"
    "#define __NR_syscalls 441\n"
)
assert s.count(old) == 1, "unistd.h anchor not unique!"
s = s.replace(old, new, 1)
open(up, "w").write(s)
print("unistd.h: 436=close_range, 437-439=ni, 440=process_madvise, syscalls=441")

# ---- 2) fs/file.c: 追加 close_range 实现 ----
fp = os.path.join(tree, "fs/file.c")
s = open(fp).read()
impl = (
    "\n"
    "/* MARS-CLOSE-RANGE: 真 close_range(最小正确实现, flags 仅支持 0)。\n"
    " * 语义: 关闭 [fd, max_fd] 区间内全部描述符(缺失的静默跳过); fd>max_fd 或未知\n"
    " * flags 返回 -EINVAL。逐 fd __close_fd(等价于 glibc 回退路径的性能, 足够 systemd 用)。\n"
    " * 注意: 本树 process_madvise 原占 436 与主线撞号, 见 unistd.h MARS-CLOSE-RANGE-436。 */\n"
    "SYSCALL_DEFINE3(close_range, unsigned int, fd, unsigned int, max_fd, unsigned int, flags)\n"
    "{\n"
    "\tunsigned int cur;\n"
    "\n"
    "\tif (flags)\n"
    "\t\treturn -EINVAL;\n"
    "\tif (fd > max_fd)\n"
    "\t\treturn -EINVAL;\n"
    "\tif (max_fd >= sysctl_nr_open)\n"
    "\t\tmax_fd = sysctl_nr_open - 1;\n"
    "\n"
    "\tfor (cur = fd; cur <= max_fd; cur++)\n"
    "\t\t__close_fd(current->files, cur);\n"
    "\treturn 0;\n"
    "}\n"
)
assert "SYSCALL_DEFINE3(close_range" not in s, "close_range already present!"
assert s.rstrip().endswith("}"), "fs/file.c unexpected ending"
s = s.rstrip() + "\n" + impl
open(fp, "w").write(s)
print("fs/file.c: SYSCALL_DEFINE3(close_range) appended")

# ---- 核对 ----
s = open(up).read()
for probe in ("__NR_close_range 436", "__NR_process_madvise 440", "__NR_syscalls 441"):
    assert probe in s, probe
print("MARS-CLOSE-RANGE-436 OK")
