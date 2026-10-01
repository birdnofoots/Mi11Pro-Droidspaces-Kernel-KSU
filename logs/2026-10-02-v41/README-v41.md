# v4.1 测试日志 + 根因证据(2026-10-02)

## 结论
启动失败根因 = **GPU 固件时序**:
自编内核(显示/GPU 内建)在 5.67s 就请求 A660 GPU 固件,而 `/vendor/firmware` 那时对内核
不可读(-EACCES)、ueventd 也还不能服务 sysfs 回退 ⇒ GPU 起不来 ⇒ surfaceflinger
`no suitable EGLConfig found` 自杀 ⇒ 106 秒时 init powerctl 重启。
原厂在 12.6s 才请求同一批固件(ueventd 已就绪)⇒ 正常。

## 文件
| 文件 | 说明 |
|---|---|
| `logdump-v41.bin` | sde59 前 4MB 原始镜像(**校验和通过**) |
| `bootlog-v41.txt` | 解析出的完整 106 秒内核日志(3572 行) |
| `tombstone_30` | surfaceflinger 崩溃现场(Abort message + 调用栈) |
| `tombstone_01/31` | camera provider 崩溃现场 |
| `stock-dmesg.txt` | 原厂完整启动日志(对照模块/固件时序) |
