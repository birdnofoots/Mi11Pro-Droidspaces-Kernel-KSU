#!/bin/bash
# ksu-integrate.sh <内核树根> —— KernelSU v0.9.5 非 GKI 整合(官方 kprobe 法, 固定 v0.9.5)
#
# 背景(2026-10-12 §O8): 最新 KSU(>=1.0) 只支持 GKI 5.10+, boot.img patch 对 5.4 非 GKI 无效;
#   非 GKI 唯一正路 = v0.9.5 源码整合(kernel/Kconfig: CONFIG_KSU depends on OVERLAY_FS)。
#   我们工厂 config 已有 KPROBES=y / HAVE_KPROBES=y / OVERLAY_FS=y ⇒ 走 kprobe 自动挂钩:
#   KernelSU 在 ksu.c 里注册 kprobe(execveat/faccessat/vfs_read/stat + core_hook 的 prctl/rename/setuid)。
#   ⚠️ 上次 KSU 尝试"没 root 成功"的高概率原因: CONFIG_KPROBES 没开 —— 源码里明说
#      "KPROBES is disabled, KernelSU may not work"; 本次由 workflow 断言 CONFIG_KSU=y。
#   ⚠️ 若 bootloop: 按官方文档注释 ksu.c 的 ksu_sucompat_init()/ksu_ksud_init() 再改手动挂钩法。
set -eu
K="${1:?用法: ksu-integrate.sh <内核树根>}"
cd "$K"
echo "== [KSU] 拉取 tiann/KernelSU v0.9.5 =="
rm -rf KernelSU
git clone --depth 1 --branch v0.9.5 https://github.com/tiann/KernelSU KernelSU
test -f KernelSU/kernel/Makefile
echo "== [KSU] 挂进内核树(等价官方 setup.sh: 软链 + Makefile + Kconfig) =="
ln -sfn ../KernelSU/kernel drivers/kernelsu
grep -q 'kernelsu' drivers/Makefile || echo 'obj-$(CONFIG_KSU) += kernelsu/' >> drivers/Makefile
grep -q 'drivers/kernelsu/Kconfig' drivers/Kconfig || echo 'source "drivers/kernelsu/Kconfig"' >> drivers/Kconfig
echo "== [KSU] ★MARS 修复: escape_to_root 清 securebits(上游 v0.9.5 缺陷) =="
python3 - "KernelSU/kernel/core_hook.c" <<'PYFIX'
import sys
p = sys.argv[1]
s = open(p).read()
anchor = "\t// disable seccomp"
fix = (
    "\t// MARS-SECUREBITS-FIX(2026-10-13): Android zygote/adbd 给进程留 securebits=0x2f\n"
    "\t// (NOROOT|NOROOT_LOCKED|NO_SETUID_FIXUP|NO_SETUID_FIXUP_LOCKED|KEEP_CAPS_LOCKED)。\n"
    "\t// 上游 v0.9.5 escape_to_root 忘了清零 ⇒ su/root 链全程继承锁位 ⇒\n"
    "\t// PR_SET_KEEPCAPS/PR_SET_SECUREBITS 恒 EPERM(ping 报错)、systemd 服务孵化失败\n"
    "\t// (容器无 IP/终端进不去)。锁定位用户态不可逆, 必须内核直写清零。\n"
    "\tcred->securebits = 0;\n\n"
)
assert s.count(anchor) == 1, "escape_to_root anchor not unique!"
s = s.replace(anchor, fix + anchor, 1)
open(p, 'w').write(s)
print("MARS-SECUREBITS-FIX injected")
PYFIX
echo "== [KSU] ★MARS 修复2: root profile 能力兜底(必须在 caps memcpy 之前) =="
python3 - "KernelSU/kernel/core_hook.c" <<'PYFIX2'
import sys
p = sys.argv[1]
s = open(p).read()
anchor = "\tu64 cap_for_ksud =\n"
fix = (
    "\t// MARS-ROOTCAP-FIX(2026-10-13): default_root_profile 是零初始化 static, 其缓存\n"
    "\t// 只靠管理器(CMD_SET_APP_PROFILE)下发 ⇒ 重启后归零 ⇒ escape_to_root 会发出\n"
    "\t// 零能力 root(uid=0 但 CapEff/CapBnd 全 0) ⇒ unshare/chmod/容器/droidspaces check 全挂。\n"
    "\t// root 必须是全能力, 直接兜底(用户态 profile 语义对容器场景无意义)。\n"
    "\tprofile->capabilities.effective = ~0ULL;\n\n"
)
assert s.count(anchor) == 1, "cap_for_ksud anchor not unique!"
s = s.replace(anchor, fix + anchor, 1)
open(p, 'w').write(s)
print("MARS-ROOTCAP-FIX injected")
PYFIX2
grep -n 'MARS-SECUREBITS-FIX\|MARS-ROOTCAP-FIX\|cred->securebits = 0\|profile->capabilities.effective = ~0' KernelSU/kernel/core_hook.c | head -5
echo "== [KSU] 集成核对 =="
ls drivers/kernelsu/Makefile
grep -n 'kernelsu' drivers/Makefile drivers/Kconfig
echo "== [KSU] OK =="
