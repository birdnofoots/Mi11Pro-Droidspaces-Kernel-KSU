#!/bin/bash
# 一加 USB 直连 mars: 容器里常缺 usbfs 设备节点, 补上后 adb 即认
# (lsusb 能看到 2717:ff48 就说明内核已枚举, 只差节点)
for BUS in /sys/bus/usb/devices/*/busnum; do
  [ -e "$BUS" ] || continue
  B=$(cat "$BUS"); D=$(cat "$(dirname "$BUS")/devnum")
  [ -e "$(dirname "$BUS")/idVendor" ] || continue
  mkdir -p /dev/bus/usb/$(printf %03d $B)
  N=/dev/bus/usb/$(printf %03d $B)/$(printf %03d $D)
  [ -e "$N" ] || mknod "$N" c 189 $(( (B-1)*128 + D-1 ))
  chmod 666 "$N" 2>/dev/null
done
adb kill-server 2>/dev/null; sleep 1
adb devices -l | tail -3
