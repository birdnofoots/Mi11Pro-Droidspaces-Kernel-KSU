#!/bin/bash
# container-opts.sh <kernel_root> —— 把 Droidspaces 容器必需项写进 $K/out/.config（在 olddefconfig 之前/之后都能跑）
# 同时: MODVERSIONS=n + 固定 LOCALVERSION(原厂串) —— 让 MIUI vendor DLKM 能装进来
set -eu
K="${1:?kernel root}"
CFG="$K/out/.config"
SC="$K/scripts/config"
[ -f "$CFG" ] || { echo "❌ 没有 $CFG"; exit 1; }
# 容器必需项
for opt in PID_NS IPC_NS UTS_NS NET_NS USER_NS SYSVIPC POSIX_MQUEUE DEVTMPFS \
           CGROUPS CGROUP_DEVICE CGROUP_PIDS CGROUP_FREEZER NAMESPACES VETH SECCOMP SECCOMP_FILTER \
           OVERLAY_FS BRIDGE TMPFS MEMCG CGROUP_BPF BLK_DEV_INITRD IP_NF_NAT IP_NF_TARGET_MASQUERADE \
           NETFILTER_XT_TARGET_MASQUERADE NF_NAT NF_CONNTRACK; do
  "$SC" --file "$CFG" -e "$opt" 2>/dev/null || echo "  (跳过 $opt: 该树没有此符号)"
done
# vendor 模块兼容
"$SC" --file "$CFG" -d MODVERSIONS 2>/dev/null || true
"$SC" --file "$CFG" -d MODULE_SIG -d MODULE_SIG_FORCE -d MODULE_SIG_ALL 2>/dev/null || true
"$SC" --file "$CFG" -d LOCALVERSION_AUTO 2>/dev/null || true
"$SC" --file "$CFG" --set-str LOCALVERSION "-qgki-gbb70cde46897" 2>/dev/null || true
echo "=== container-opts 结果 ==="
grep -E "^CONFIG_(PID_NS|IPC_NS|UTS_NS|NET_NS|USER_NS|SYSVIPC|POSIX_MQUEUE|DEVTMPFS|CGROUPS|CGROUP_DEVICE|NAMESPACES|VETH|SECCOMP_FILTER|OVERLAY_FS|BRIDGE|TMPFS|NF_NAT|IP_NF_TARGET_MASQUERADE)=" "$CFG" | sort
grep -E "^# CONFIG_MODVERSIONS is not set|^CONFIG_LOCALVERSION=" "$CFG" || true
