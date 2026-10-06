#!/usr/bin/env python3
"""log-buf-min.py <kernel_root> —— 把 printk 环缓冲下限钳到 4MB

为什么必须做(CHECKLIST §22.14.AE 第 3 段):
  mars 的最终 cmdline 里 `log_buf_len=256K` 来自 **DT/ABL**(不是 boot.img):
    · 手机上 `/proc/device-tree/chosen/bootargs` 的第一个 token 就是 `log_buf_len=256K`;
    · 我们/原厂的 boot.img 的 cmdline 字段实测**全是空字符串**(v3 header,偏移 44);
    · 最终 cmdline 顺序 = ABL(`ramoops_memreserve=4M`) → DT(`log_buf_len=256K`) → … → ABL(`androidboot.verifiedbootstate`)
  ⇒ 环缓冲只有 256K ⇒ **启动 4~12s 的日志(正是 vendor 模块装载/CNSS bring-up 的窗口)被挤掉**,
    我们为此误判过多轮(F34 判决错误就是这么来的)。
  又因为 `log_buf_len_update()` 是"最后一次非零值生效",把 `log_buf_len=4M` 写进镜像 cmdline
  会被后面的 DT `256K` 覆盖 ⇒ **只能在内核源码里钳下限**。

做法: 在 `kernel/printk/printk.c` 的 `log_buf_len_update(u64 size)` 里,把非零但 <4MB 的请求抬到 4MB。
  只影响日志缓冲大小,不改变任何功能路径;4MB 常驻内存对 12GB 机器可忽略。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "kernel/printk/printk.c")
s = open(path, errors="ignore").read()

if "mars-logbuf-clamp" in s:
    print("log-buf-min: skip (already applied)")
    sys.exit(0)

MARK = "\t/* mars-logbuf-clamp: 保证环缓冲足够大,否则启动 4~12s 的日志会被覆盖 */\n" \
       "\tif (size && size < (4ULL << 20))\n" \
       "\t\tsize = (4ULL << 20);\n"

# 目标函数(5.4 的 MiCode 树里是 log_buf_len_update;老树可能直接写在 setup 里)
m = re.search(r"(static\s+void\s+__init\s+log_buf_len_update\s*\(u64\s+size\)\s*\{)", s)
if m:
    # 插到函数体第一行的前面
    body_start = m.end()
    s2 = s[:body_start] + "\n" + MARK + s[body_start:]
else:
    # 退化路径:直接改 log_buf_len_setup 里的 memparse 之后
    m2 = re.search(r"(static\s+int\s+__init\s+log_buf_len_setup\s*\(char\s*\*str\)\s*\{)", s)
    if not m2:
        print("log-buf-min: ❌ 找不到 log_buf_len_update / log_buf_len_setup")
        sys.exit(1)
    b = m2.end()
    s2 = s[:b] + "\n" + MARK + s[b:]

assert "mars-logbuf-clamp" in s2
open(path, "w").write(s2)
print("log-buf-min: ✅ 已注入环缓冲下限 4MB")
