# mars 自编内核启动日志(v4 logdump 首次成功抓取)

**日期**:2026-10-02(容器时间 2026-10-01 晚)
**来源**:自编内核 `5.4.233-qgki`(star-ds-ksu,run 36851919386,commit b9181a6)
**抓取方式**:内核侧 `logdump` 驱动(gh/patches/logdump.c v4)
  崩溃回调(memcpy 到静态快照 + schedule_work,workqueue 里 bio 直写)→
  `/dev/block/by-name/logdump`(sde59)偏移 0

## 文件
| 文件 | 说明 |
|---|---|
| `logdump-v4-1.bin` | sde59 前 4MB 原始镜像(权威原始证据) |
| `bootlog-v4-1.txt` | 从中解析出的内核日志正文(3809 行,0 → 96.68s) |
| `stock-dmesg.txt` | 同一台设备的**原厂内核**启动日志(5.4.233-qgki-gbb70cde46897),用于对照 |
| `MD5SUMS.txt` | 各文件 md5 |

## 解析出的头部(权威)
```
magic=KLOGDMP4 seq=52 len=354876 source=3 reason=5 uptime=106169ms
source=3 → LOGDUMP_SRC_CALLBACK(崩溃回调快照经 workqueue 落盘)
reason=5 → KMSG_DUMP_RESTART ⇒ 失败形态是【有序重启】,不是硬复位
uptime=106.169s ⇒ 与用户观察的 30~120 秒吻合
```

## 已知缺陷(导致正文只到 96.68s)
写入长度未按设备逻辑块大小(4096)对齐 ⇒ `-EIO`,最后一次写入的尾部 ~100KB 丢失:
```
sd 0:0:0:4: [sde] tag#9 request not aligned to the logical block size
blk_update_request: I/O error, dev sde, sector 3992656 op 0x1:(WRITE) ...
```
已在 v4.1 修正(长度向上对齐 + RESTART 回调里 flush_work),run 36856890671。
