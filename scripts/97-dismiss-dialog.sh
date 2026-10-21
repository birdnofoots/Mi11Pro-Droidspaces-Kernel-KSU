#!/system/bin/sh
# 自动点掉 “Android 系统：您的设备内部出现了问题。请联系您的设备制造商” (SYSTEM_ERROR)
# 该弹窗由 system_server 的 Build.isBuildConsistent() 检查触发（system/vendor 指纹不一致），
# 不是真的故障；这里只负责在开机后自动点“确定”，避免卡住。
LOG=/data/local/tmp/dismiss-system-error.log
log(){ echo "[$(date +%H:%M:%S)] $*" >> $LOG; }
: > $LOG
i=0; while [ $i -lt 120 ]; do [ "$(getprop sys.boot_completed)" = 1 ] && break; sleep 5; i=$((i+1)); done
log "boot_completed=$(getprop sys.boot_completed)"
sleep 8
n=0
for i in $(seq 1 120); do
  if dumpsys window windows 2>/dev/null | grep -q "ty=SYSTEM_ERROR"; then
    n=$((n+1))
    log "检测到 SYSTEM_ERROR 弹窗(第 $n 次)，点击确定"
    input tap 720 2962
    sleep 2
    if dumpsys window windows 2>/dev/null | grep -q "ty=SYSTEM_ERROR"; then
      log "点击后仍在，尝试 ENTER"
      input keyevent KEYCODE_ENTER
    fi
    sleep 2
    log "剩余 SYSTEM_ERROR 窗口: $(dumpsys window windows 2>/dev/null | grep -c 'ty=SYSTEM_ERROR')"
  fi
  sleep 3
done
log "监控结束"
