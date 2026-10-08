#!/usr/bin/env python3
"""kabi-sysvipc.py <kernel_root> —— 打开 CONFIG_SYSVIPC 但【不改变 task_struct 布局】

为什么(2026-10-09): 容器必需项要 CONFIG_SYSVIPC=y,但原厂 272 个 vendor 模块是按
"没有 SYSVIPC" 的 task_struct 布局编译的;直接开启会让 sysvsem/sysvshm 插进结构体中间,
后续字段偏移全变 ⇒ 模块读写错位(静默损坏/挂死)。
做法: 用 Android GKI 的 KABI 预留槽(ANDROID_KABI_USE/RESERVE)承载这两个结构,
      使 struct 大小与字段偏移与原厂完全一致(即上游 Droidspaces 的 001 号补丁)。
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
p = os.path.join(root, "include/linux/sched.h")
s = open(p, errors="ignore").read()
if "mars-kabi-sysvipc" in s:
    print("kabi-sysvipc: skip (already applied)")
    sys.exit(0)

# 1) 注释掉 SYSVIPC 块里的两个字段(它们改到 KABI 预留区)
a = "\tstruct sysv_sem\t\t\tsysvsem;\n\tstruct sysv_shm\t\t\tsysvshm;\n"
if a not in s:
    a2 = re.search(r"#ifdef CONFIG_SYSVIPC\n(.*?)#endif\n", s, re.S)
    print("kabi-sysvipc: 找不到 SYSVIPC 字段块:", bool(a2))
    if a2: print("   实际内容:", a2.group(1)[:200])
    sys.exit(1)
s = s.replace(a, "\t/* mars-kabi-sysvipc: 见 patches/kabi-sysvipc.py */\n"
                 "\t/* struct sysv_sem\t\tsysvsem; */\n"
                 "\t/* struct sysv_shm\t\tsysvshm; */\n", 1)

# 2) KABI 预留槽改成按 SYSVIPC 条件使用
b = "\tANDROID_KABI_RESERVE(6);\n\tANDROID_KABI_RESERVE(7);\n\tANDROID_KABI_RESERVE(8);\n"
if b not in s:
    print("kabi-sysvipc: 找不到 ANDROID_KABI_RESERVE(6..8) 块")
    sys.exit(1)
new = ("#ifdef CONFIG_SYSVIPC\n"
       "\tANDROID_KABI_USE(6, struct sysv_sem sysvsem);\n"
       "\t_ANDROID_KABI_REPLACE(ANDROID_KABI_RESERVE(7); ANDROID_KABI_RESERVE(8), struct sysv_shm sysvshm);\n"
       "#else\n"
       + b +
       "#endif\n")
s = s.replace(b, new, 1)
open(p, "w").write(s)
chk = open(p, errors="ignore").read()
assert "mars-kabi-sysvipc" in chk and "ANDROID_KABI_USE(6, struct sysv_sem" in chk
print("kabi-sysvipc: 已注入(task_struct 布局保持不变)")
