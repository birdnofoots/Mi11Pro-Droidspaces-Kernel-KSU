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
echo "== [KSU] 集成核对 =="
ls drivers/kernelsu/Makefile
grep -n 'kernelsu' drivers/Makefile drivers/Kconfig
echo "== [KSU] OK =="
