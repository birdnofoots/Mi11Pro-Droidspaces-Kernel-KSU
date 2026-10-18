#!/system/bin/sh
# nr436-shim 一键安装器(手机上 root 运行) —— ★每个新容器都要跑一次
# 前置: /sdcard/nr436-shim 已就位(arm64 静态, 由 patches/nr436-shim.c 编译)
# 用法: sh nr436-shim-install.sh <容器名>
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

# 3) 容器内安装(幂等; busybox/符号链/实体三种 init 都兼容)
$DS --name=$NAME run /bin/sh -c '
if [ -e /sbin/init.real ]; then echo "[=] 已装, 跳过"; exit 0; fi
cp /storage/emulated/0/nr436-shim /tmp/nr436-shim || { echo "[x] 拷入失败(存储桥未通?)"; exit 1; }
chmod 755 /tmp/nr436-shim
mv /sbin/init /sbin/init.real        # 符号链/实体原样保留
cp /tmp/nr436-shim /sbin/init
chmod 755 /sbin/init
echo "[+] 装好: /sbin/init=$(ls -la /sbin/init | awk "{print \$5}")B -> init.real=$(ls -la /sbin/init.real | tail -c 60)"
' || exit 1

# 4) 重启生效 + 验证
$DS stop -n $NAME >/dev/null 2>&1; sleep 2
$DS start -n $NAME >/dev/null 2>&1; sleep 12
$DS --name=$NAME run /bin/sh -c '
ls -la /sbin/init /sbin/init.real >/dev/null 2>&1 || echo "[x] 文件异常"
[ -x /sbin/init.real ] && echo "[+] 验证 OK: init=shim, init.real 存在"
ip addr show eth0 2>/dev/null | grep inet | head -1
ping -c 2 -W 3 1.1.1.1 2>&1 | tail -2
'
