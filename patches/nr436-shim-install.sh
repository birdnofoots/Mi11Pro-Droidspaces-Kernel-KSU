#!/system/bin/sh
# nr436-shim 安装器(手机上 root 运行): 给 Droidspaces 容器装 436→ENOSYS 适配层
# 依赖: /sdcard/nr436-shim(arm64 静态二进制, 由 patches/nr436-shim.c 编译)
# 用法: sh nr436-shim-install.sh <容器名> [img|dir]
#   img: rootfs.img(loop 挂载, 建议 -o loop,ro,norecovery 先探测再 rw) ; dir: 目录型 rootfs 路径
NAME=$1; MODE=$2; R=${3:-/data/local/Droidspaces/Containers/$NAME/rootfs.img}
install_to() {
  D=$1
  [ -e $D/sbin/init.real ] && { echo "$NAME: 已装"; return; }
  mv $D/sbin/init $D/sbin/init.real        # 符号链/实体都原样保留
  cp /sdcard/nr436-shim $D/sbin/init
  chmod 755 $D/sbin/init
  echo "$NAME: 装好"
}
if [ "$MODE" = "dir" ]; then
  install_to "$R"
else
  mkdir -p /mnt/fixroot
  mount -o loop "$R" /mnt/fixroot || { echo "挂载失败"; exit 1; }
  install_to /mnt/fixroot
  sync; umount /mnt/fixroot
fi
