#!/usr/bin/env python3
"""kabi-posix-mqueue.py <kernel_root> —— 打开 CONFIG_POSIX_MQUEUE 但【不改变 user_struct 布局】
同 kabi-sysvipc.py 的理由(user_struct.mq_bytes 改用 KABI 预留槽)。
本树(GKI mars)的 user_struct 只有 RESERVE(1)/(2),没有 ANDROID_OEM_DATA_ARRAY ⇒ 适配版。
"""
import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
p = os.path.join(root, "include/linux/sched/user.h")
s = open(p, errors="ignore").read()
if "mars-kabi-mqueue" in s:
    print("kabi-posix-mqueue: skip (already applied)")
    sys.exit(0)

a = "\tunsigned long mq_bytes;\t/* How many bytes can be allocated to mqueue? */\n"
if a not in s:
    print("kabi-posix-mqueue: 找不到 mq_bytes 字段")
    sys.exit(1)
s = s.replace(a, "\t/* mars-kabi-mqueue: 见 patches/kabi-posix-mqueue.py */\n"
                 "\t/* unsigned long mq_bytes; */\n", 1)

b = "\tANDROID_KABI_RESERVE(1);\n\tANDROID_KABI_RESERVE(2);\n"
if b not in s:
    print("kabi-posix-mqueue: 找不到 ANDROID_KABI_RESERVE(1)/(2)")
    sys.exit(1)
new = ("#if defined(CONFIG_POSIX_MQUEUE)\n"
       "\tANDROID_KABI_USE(1, unsigned long mq_bytes);\n"
       "\tANDROID_KABI_RESERVE(2);\n"
       "#else\n"
       + b +
       "#endif\n")
s = s.replace(b, new, 1)
open(p, "w").write(s)
chk = open(p, errors="ignore").read()
assert "mars-kabi-mqueue" in chk and "ANDROID_KABI_USE(1, unsigned long mq_bytes)" in chk
print("kabi-posix-mqueue: 已注入(user_struct 布局保持不变)")
