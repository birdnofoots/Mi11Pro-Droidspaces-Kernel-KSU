#!/bin/bash
# mini-host (192.168.1.81) 环境自检 + 为 mars 项目做准备
# 用法(小主机上): bash minihost-setup.sh
set -u
echo "================= 小主机环境报告 ================="
echo "主机名: $(hostname)"; echo "系统  : $(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY | cut -d= -f2)"
echo "内核  : $(uname -r)"; echo "CPU   : $(nproc) 核"; free -h | head -2 | tail -1
echo "磁盘  :"; df -h / /home 2>/dev/null | tail -2
echo "块设备:"; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT 2>/dev/null | head -12
echo "adb   : $(command -v adb || echo 缺)  $(adb version 2>/dev/null | head -1)"
echo "fastboot: $(command -v fastboot || echo 缺)  $(fastboot --version 2>/dev/null | head -1)"
echo "git   : $(command -v git || echo 缺)"; echo "python3: $(command -v python3 || echo 缺)"
echo "sudo  : $(echo gozilla | sudo -S id 2>/dev/null | head -1)"
echo "当前 USB:"; lsusb 2>/dev/null | grep -viE "root hub" | head -8

echo; echo "================= 1) 装 udev 规则(让 adb/fastboot 免 root 用 USB) ================="
if [ ! -f /etc/udev/rules.d/51-android.rules ]; then
  echo gozilla | sudo -S tee /etc/udev/rules.d/51-android.rules >/dev/null <<'RULES'
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", MODE="0666", GROUP="plugdev"
RULES
  echo gozilla | sudo -S udevadm control --reload-rules 2>/dev/null
  echo gozilla | sudo -S udevadm trigger 2>/dev/null
  echo "已写入 /etc/udev/rules.d/51-android.rules ✓"
else
  echo "已存在 udev 规则 ✓"
fi
if ! id -nG "$USER" | grep -qw plugdev; then
  echo gozilla | sudo -S usermod -aG plugdev "$USER" && echo "已把 $USER 加入 plugdev 组(下次登录生效)✓"
fi

echo; echo "================= 2) adb server 对所有网卡监听(供容器远程使用) ================="
adb kill-server >/dev/null 2>&1
adb -a -P 5037 start-server >/dev/null 2>&1
sleep 2
if ss -tlnp 2>/dev/null | grep -q ':5037'; then
  echo "adb server 已监听 5037 ✓ → 容器里可: ADB_SERVER_SOCKET=tcp:192.168.1.81:5037 adb devices"
else
  echo "adb server 未监听(可稍后再试)✗"
fi

echo; echo "================= 3) 建工作目录并克隆项目 ================="
mkdir -p ~/mars && cd ~/mars
if [ -d Mi11Pro-Droidspaces-Kernel-KSU/.git ]; then
  (cd Mi11Pro-Droidspaces-Kernel-KSU && git pull --ff-only 2>&1 | tail -2)
  echo "仓库已存在,已尝试更新 ✓"
else
  git clone --depth 1 https://github.com/birdnofoots/Mi11Pro-Droidspaces-Kernel-KSU.git 2>&1 | tail -3
fi
ls -la ~/mars | head -6

echo; echo "================= 4) mars 是否已插上(USB) ================="
timeout 8 fastboot devices 2>&1 | head -2
timeout 8 adb devices 2>&1 | head -4
echo; echo "提示:"
echo "  * mars 进 FASTBOOT 后,小主机上应看到: <serial>   fastboot"
echo "  * 刷入命令: fastboot flash boot ~/mars/Mi11Pro-Droidspaces-Kernel-KSU/boot-star-stock.img"
echo "  * 容器侧(局域网恢复后)可直接: ADB_SERVER_SOCKET=tcp:192.168.1.81:5037 adb devices"
echo "================= 报告结束 ================="
