#!/system/bin/sh
# ============================================================================
# 99-wlan-mars.sh  v8  (2026-10-19)   ★ 手机侧【唯一】需要的开机脚本 ★
#
# v8 (2026-10-19): 修「重启后 WiFi 处于关闭状态」——
#   等 WifiService 就绪后反复 enable，直到 settings global wifi_on=1；
#   等 IP 期间周期补 enable；即使最终没 IP 也保证 WiFi 是开的（绝不留在关闭状态）。
#   另含 v7 的 C0 段（直接 insmod 原厂 camera.ko）。
#
# 位置: /data/adb/service.d/99-wlan-mars.sh   (chmod 755; APatch 开机自动执行)
# 日志: /data/local/tmp/wlan-boot.log
#
# 它做三件事(全部幂等, 重复执行无害):
#   A) 去谷歌化 + 关掉"连不上 Google 就判无互联网"的逻辑
#      (MIUI 国际版(EEA) 在国内会因此把已保存网络标成
#       NETWORK_SELECTION_DISABLED_NO_INTERNET_PERMANENT ⇒ 永远不自动连)
#   B) 按【必须的顺序】把原厂 WLAN 栈装起来(我们内核里 WLAN 走"整包原厂栈"路线):
#        开闸 mars_wlan_allow=1 → cnss_utils/prealloc/nl + mi_cnss_statistic
#        → 原厂 cnss2.ko → echo 1 > fs_ready 等 CBC 完成
#        → 原厂 qca_cld3_wlan.ko → /system/bin/svc wifi enable → 等 IP
#      * qca_cld3_wlan 早于 CBC 装会被 cnss2 以 -EPERM 拒绝("Reject WLAN Driver insmod before CBC")
#      * service.d 环境里 `svc` 会解析成 APatch BusyBox 的 runsv 命令 ⇒ 必须写 /system/bin/svc
#   C) 体检: 声卡/音频模块是否就绪(音频由 MIUI 自己的 modprobe 装, 本脚本不装)
#
# 为什么需要这个脚本(而不是让 MIUI 自己装 WLAN):
#   内核为保开机稳定打了 WLAN 门禁(wlanblock=1: 按模块名挡住 cnss2/qca_cld3_* 等),
#   否则 MIUI 早期把原厂栈装成半截会把内核卡死(2026-10-10 los48 实测, 手机要人工进 fastboot)。
#   所以"先挡、开机后再由本脚本按正确顺序装"是当前唯一稳定的路径。
#   详见 docs/mars-handover-CHECKLIST.md §41.61/§41.69/§41.71/§41.73 与 work/keep-p3/MANIFEST.md
# ============================================================================
LOG=/data/local/tmp/wlan-boot.log
FS=/sys/devices/platform/soc/b0000000.qcom,cnss-qca6490/fs_ready
V=/vendor/lib/modules
G=$V/5.4-gki
X=/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml
BAK=/data/local/tmp/WifiConfigStore.xml.mars-bak
log(){ echo "[$(date +%H:%M:%S)] $*" >> $LOG; }
has(){ lsmod | grep -q "^$1 "; }
ins(){ f=$1; [ -f "$f" ] || return 2; insmod "$f" 2>>$LOG; r=$?; log "  insmod $(basename $f) rc=$r ($(dirname $f))"; return $r; }
: > $LOG
log "=== v8 引导开始 ==="

# ---- 0) 开闸 + 等系统起完 ----
[ -e /sys/module/kernel/parameters/mars_wlan_allow ] && { echo 1 > /sys/module/kernel/parameters/mars_wlan_allow; log "门禁开=$(cat /sys/module/kernel/parameters/mars_wlan_allow)"; }
i=0; while [ $i -lt 90 ]; do [ "$(getprop sys.boot_completed)" = "1" ] && break; sleep 5; i=$((i+1)); done
log "boot_completed=$(getprop sys.boot_completed)"
sleep 5

# ---- A) 去谷歌化 + 连通性检测 ----
settings put global captive_portal_mode 0
settings put global captive_portal_detection_enabled 0
settings put global captive_portal_use_https 0
settings put global captive_portal_http_url  http://connect.rom.miui.com/generate_204
settings put global captive_portal_https_url https://connect.rom.miui.com/generate_204
settings put global captive_portal_fallback_url http://connect.rom.miui.com/generate_204
settings put global device_provisioned 1
settings put secure user_setup_complete 1
for p in com.google.android.setupwizard com.android.provision; do
  pm list packages 2>/dev/null | grep -q "package:$p$" && pm disable-user --user 0 "$p" >/dev/null 2>&1
done
settings put global package_verifier_enable 0
settings put global verifier_verify_adb_installs 0
settings put global package_verifier_user_consent -1
settings put global package_verifier_include_adb_installs 0
settings put global upload_apk_enable 0
log "A) captive_portal_mode=$(settings get global captive_portal_mode) url=$(settings get global captive_portal_http_url) provisioned=$(settings get global device_provisioned)"

# 清掉历史遗留的"无互联网 → 永久禁用"标记(清了就 wifi 关再开一次, 让框架重读配置)
CLEARED=0
if [ -f "$X" ]; then
  n=$(grep -c 'NETWORK_SELECTION_DISABLED_NO_INTERNET' "$X" 2>/dev/null)
  if [ "$n" != "0" ]; then
    [ -f "$BAK" ] || cp -f "$X" "$BAK" 2>/dev/null
    sed -i \
      -e 's|<string name="SelectionStatus">NETWORK_SELECTION_PERMANENTLY_DISABLED</string>|<string name="SelectionStatus">NETWORK_SELECTION_ENABLED</string>|g' \
      -e 's|<string name="DisableReason">NETWORK_SELECTION_DISABLED_NO_INTERNET[^<]*</string>|<string name="DisableReason">NETWORK_SELECTION_ENABLE</string>|g' \
      "$X" 2>>$LOG
    CLEARED=1
    log "A) 清除 $n 处 NO_INTERNET 永久禁用(备份 $BAK)"
  else
    log "A) 无 NO_INTERNET 永久禁用"
  fi
fi

# ---- B) 原厂 WLAN 栈(顺序不可改) ----
if [ "$CLEARED" = "1" ]; then /system/bin/svc wifi disable >/dev/null 2>&1; sleep 2; fi
for m in cnss_utils cnss_prealloc cnss_nl mi_cnss_statistic; do
  if has $m; then log "B) $m 已装"; else ins $G/$m.ko || ins $V/$m.ko; fi
done
has hwid || ins $V/hwid.ko
has cnss2 || ins $V/cnss2.ko
sleep 3
[ -e $FS ] && { echo 1 > $FS 2>>$LOG; log "B) fs_ready=1 (触发 CBC)"; }
i=0; while [ $i -lt 40 ]; do dmesg | grep -q "Calibration completed successfully" && { log "B) ★ CBC 完成"; break; }; sleep 3; i=$((i+1)); done
sleep 3
has wlan || ins $V/qca_cld3_wlan.ko
sleep 8
i=0; while [ $i -lt 24 ]; do ls /sys/class/net 2>/dev/null | grep -q wlan0 && { log "B) ★ wlan0 出现"; break; }; sleep 5; i=$((i+1)); done
if ls /sys/class/net 2>/dev/null | grep -q wlan0; then
  # 等 WifiService 就绪（cmd wifi status 能返回 "Wifi is ..."）
  i=0; READY=0
  while [ $i -lt 30 ]; do
    cmd wifi status 2>/dev/null | head -1 | grep -q "Wifi is" && { READY=1; break; }
    sleep 2; i=$((i+1))
  done
  log "B) WifiService 就绪=$READY"

  # 反复 enable，直到 settings global wifi_on=1（svc 在服务未就绪时会被忽略）
  i=0
  while [ $i -lt 36 ]; do
    /system/bin/svc wifi enable >/dev/null 2>&1
    cmd wifi set-wifi-enabled enabled >/dev/null 2>&1
    sleep 5
    [ "$(settings get global wifi_on 2>/dev/null)" = "1" ] && { log "B) ★ wifi_on=1 (第 $((i+1)) 次)"; break; }
    i=$((i+1))
  done
  log "B) wifi_on=$(settings get global wifi_on 2>/dev/null)"

  # 等 IP；期间周期性补 enable，保证最终 WiFi 一定是开的
  i=0
  while [ $i -lt 40 ]; do
    ip addr show wlan0 2>/dev/null | grep -q "inet " && { log "B) ★ wlan0 拿到 IP"; break; }
    sleep 5
    [ $((i % 3)) -eq 0 ] && /system/bin/svc wifi enable >/dev/null 2>&1
    i=$((i+1))
  done
  if ! ip addr show wlan0 2>/dev/null | grep -q "inet "; then
    log "B) 仍未拿到 IP，强制保持 WiFi 开启并补一次扫描"
    /system/bin/svc wifi enable >/dev/null 2>&1
    cmd wifi start-scan >/dev/null 2>&1 || true
  fi

  # 连接后再清一次 NO_INTERNET（开机阶段框架可能重新写入）
  if [ -f "$X" ]; then
    n=$(grep -c 'NETWORK_SELECTION_DISABLED_NO_INTERNET' "$X" 2>/dev/null)
    if [ "$n" != "0" ]; then
      sed -i \
        -e 's|<string name="SelectionStatus">NETWORK_SELECTION_PERMANENTLY_DISABLED</string>|<string name="SelectionStatus">NETWORK_SELECTION_ENABLED</string>|g' \
        -e 's|<string name="DisableReason">NETWORK_SELECTION_DISABLED_NO_INTERNET[^<]*</string>|<string name="DisableReason">NETWORK_SELECTION_ENABLE</string>|g' \
        "$X" 2>>$LOG
      log "B) 连接后清除 $n 处 NO_INTERNET"
    fi
  fi
  log "B) wlan0: $(ip addr show wlan0 2>/dev/null | grep -E 'inet |state' | tr '\n' '|')"
  log "B) wifi: $(cmd wifi status 2>/dev/null | head -4 | tr '\n' '|' | cut -c1-300)"
  log "B) ping: $(ping -c 2 -W 4 223.5.5.5 2>&1 | tail -2 | tr '\n' '|')"
else
  log "B) !! 没有 wlan0"
fi

# ---- C) 相机: 必须【直接 insmod】, 不能走 modprobe ----
#   camera.ko 的 modules.dep 依赖 msm_drm / leds-qti-flash / led-class-flash /
#   qti_battery_charger_main —— 这些与我们内建驱动撞名会被内核拒装
#   ("exports duplicate symbol … owned by kernel") ⇒ modprobe 依赖链断, camera.ko 永远轮不到
#   ⇒ CamX::HwEnvironment::Initialize() 打不开 /dev/cam_req_mgr ⇒ vendor.camera-provider-2-4 崩溃循环。
#   实测(§41.82): camera.ko 300 个未定义符号中 8 个 debugfs_* 在真机构建里被编译掉,
#   余下 292 个中 291 个由我们 vmlinux 直接提供, 只有 get_hw_version_platform 来自 hwid.ko(上面 B 段已装)
#   ⇒ 直接 insmod 即可(与 vmlinux 零撞名)。
if has camera; then log "C0) camera 已装"; else
  ins $V/camera.ko
  sleep 3
  log "C0) camera=$(lsmod | grep -c '^camera') 个 / /dev/video*=$(ls /dev/video* 2>/dev/null | wc -l) 个 / dmesg: $(dmesg | grep -ai camera | tail -1 | cut -c1-120)"
fi

# ---- C) 体检(不装音频; 音频由 MIUI 自己的 modprobe 按原厂顺序装) ----
log "C) 声卡: $(cat /proc/asound/cards 2>/dev/null | tr '\n' '|')"
log "C) 音频模块数: $(lsmod | grep -cE '^(mbhc|machine|wcd93|swr_dmic|wsa883x|cs35l41|bolero)')"
log "=== v8 结束 net=$(ls /sys/class/net | tr '\n' ' ')"
