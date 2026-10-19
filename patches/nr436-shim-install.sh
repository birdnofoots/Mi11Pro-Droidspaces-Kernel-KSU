#!/system/bin/sh
# nr436-shim 一键安装器(手机上 root 运行) —— ★每个新容器都要跑一次
# 前置: /sdcard/nr436-shim 已就位(arm64 静态, 由 patches/nr436-shim.c 编译)
# 用法: sh nr436-shim-install.sh <容器名>
#
# 2026-10-19 更新：Droidspaces 7.0 会在容器启动时把 /sbin/init 恢复成 systemd 符号链，
# 所以 systemd 容器改用“持久位”：
#   /lib/systemd/systemd      = shim
#   /lib/systemd/systemd.real = 真 systemd
#   /sbin/init.real -> /lib/systemd/systemd.real
# /sbin/init 仍可被 App 重置成 -> /lib/systemd/systemd，但那一层已经是 shim。
# busybox/openrc 容器仍用原来的 /sbin/init 替换法。
# 幂等: 已装则跳过; 装完自动重启容器并验证。
DS=/data/local/tmp/droidspaces
NAME=$1
[ -n "$NAME" ] || { echo "用法: $0 <容器名>"; exit 2; }
[ -f /sdcard/nr436-shim ] || { echo "缺 /sdcard/nr436-shim(先 adb push)"; exit 2; }
CFG=/data/local/Droidspaces/Containers/$NAME/container.config
[ -f "$CFG" ] || { echo "无容器配置: $CFG"; exit 2; }

# 1) 容器内看不见手机存储时, 打开 android_storage(配置层, 安全)
grep -q '^enable_android_storage=1' "$CFG" || {
  sed -i 's/^enable_android_storage=0/enable_android_storage=1/' "$CFG"
  echo "[i] 已开 enable_android_storage(装完可改回)"
}

# 2) 确保容器在跑(挂载 rootfs) —— 一律走 droidspaces 自己的挂载, 绝不手动 loop 挂载
$DS show 2>/dev/null | grep -q "| $NAME " || { $DS start -n $NAME >/dev/null 2>&1; sleep 12; }

# 3) 容器内安装(幂等; systemd 用持久位, 其它用 /sbin/init)
$DS --name=$NAME run /bin/sh -c '
if [ -e /lib/systemd/systemd.real ]; then
  echo "[=] 已装(systemd 持久位), 跳过"; exit 0
fi
if [ -e /sbin/init.real ] && [ ! -e /lib/systemd/systemd ]; then
  echo "[=] 已装(/sbin/init 方式), 跳过"; exit 0
fi
cp /storage/emulated/0/nr436-shim /tmp/nr436-shim || { echo "[x] 拷入失败(存储桥未通?)"; exit 1; }
chmod 755 /tmp/nr436-shim
if [ -x /lib/systemd/systemd ] && [ ! -L /lib/systemd/systemd ]; then
  cp /tmp/nr436-shim /lib/systemd/systemd.shim
  mv /lib/systemd/systemd /lib/systemd/systemd.real
  ln -sfn /lib/systemd/systemd.real /sbin/init.real
  cp /lib/systemd/systemd.shim /lib/systemd/systemd
  chmod 755 /lib/systemd/systemd
  echo "[+] systemd 持久位: /lib/systemd/systemd=shim -> /lib/systemd/systemd.real"
else
  mv /sbin/init /sbin/init.real
  cp /tmp/nr436-shim /sbin/init
  chmod 755 /sbin/init
  echo "[+] init 替换: /sbin/init=shim -> /sbin/init.real"
fi
' || exit 1

# 4) 重启生效 + 验证
$DS stop -n $NAME >/dev/null 2>&1; sleep 2
$DS start -n $NAME >/dev/null 2>&1; sleep 12
$DS --name=$NAME run /bin/sh -c '
echo "--- init ---"
ls -l /sbin/init /sbin/init.real /lib/systemd/systemd /lib/systemd/systemd.real 2>/dev/null
if [ -x /lib/systemd/systemd.real ]; then
  [ "$(stat -c%s /lib/systemd/systemd 2>/dev/null)" = "$(stat -c%s /lib/systemd/systemd.shim 2>/dev/null)" ] \
    && echo "[+] 验证 OK: /lib/systemd/systemd = shim" \
    || echo "[!] /lib/systemd/systemd 可能不是 shim"
elif [ -x /sbin/init.real ]; then
  echo "[+] 验证 OK: /sbin/init = shim"
fi
echo "--- net ---"
ip addr show eth0 2>/dev/null | grep inet | head -1
ping -c 2 -W 3 1.1.1.1 2>&1 | tail -2
'
