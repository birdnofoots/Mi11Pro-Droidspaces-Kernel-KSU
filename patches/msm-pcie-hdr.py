#!/usr/bin/env python3
"""把 include/linux/msm_pcie.h 的【ABI 布局】对齐 vendor(cnss2.ko 编译时用的那份)。

★★★ 2026-10-06 真机定位(决定性证据链):
   现象: cnss2.ko 装载成功,但登记 PCIe 事件时报
        `PCIe: User of event registration is NULL` ⇒ -ENODEV
        ⇒ `Failed to register MSM PCI event, err = -19` ⇒ PCIe 链路从不训练
        ⇒ `msm_pcie_handle_linkdown: PCIe link is down for RC0` ⇒ 无 WiFi。
   根因(逐行对比 MiCode 树 vs LineageOS sm8350 树的 include/linux/msm_pcie.h):
        struct msm_pcie_register_event {
       MiCode:  u32 events; void *user; ...
       LOS  :  struct list_head node; u32 events; void *user; ...   ← 多一个前导字段
       在 arm64 上 struct list_head = 16 字节 ⇒ 两边【所有字段偏移差 16 字节】。
       cnss2.ko 是按 vendor 头文件编译的(它写 .user 到偏移 16),我们的内核按偏移 8 读
       ⇒ reg->user == NULL ⇒ 直接 -ENODEV。完美对应观测。
   同时 enum msm_pcie_config 的取值也不同(MiCode 用 0x1/0x2/0x4/0x8/0x10,
   LOS/vendor 用 BIT(0..3)) ⇒ 一并按 vendor 口径对齐(保留 MiCode 独有的
   NO_CFG_RESTORE 但挪到高位,避免与 vendor 语义冲突)。
"""
import os, re, sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
path = os.path.join(root, "include/linux/msm_pcie.h")
s = open(path, errors="ignore").read()
orig = s

# ── 1) 给 struct msm_pcie_register_event 补上前导 struct list_head node; ──
if "struct msm_pcie_register_event {" in s:
    m = re.search(r"(struct msm_pcie_register_event \{\n)", s)
    assert m, "结构体起点没找到"
    body_after = s[m.end():m.end()+200]
    if "struct list_head node;" not in body_after:
        s = s[:m.end()] + "\tstruct list_head node;\t/* ★ ABI: 必须与 vendor 头文件同布局 */\n" + s[m.end():]
        print("msm-pcie-hdr: 已补 struct list_head node;")
    else:
        print("msm-pcie-hdr: node 字段已存在,跳过")
else:
    print("msm-pcie-hdr: 没找到结构体!"); sys.exit(1)

# ── 2) enum msm_pcie_config 对齐 vendor 取值 ──
old_enum = re.search(r"enum msm_pcie_config \{(.*?)\};", s, re.S)
if old_enum:
    new_body = """
	MSM_PCIE_CONFIG_INVALID = 0,
	MSM_PCIE_CONFIG_LINKDOWN = BIT(0),
	MSM_PCIE_CONFIG_NO_RECOVERY = BIT(1),
	MSM_PCIE_CONFIG_NO_L1SS_TO = BIT(2),
	MSM_PCIE_CONFIG_NO_DRV_PC = BIT(3),
	MSM_PCIE_CONFIG_NO_CFG_RESTORE = BIT(4),	/* MiCode 独有:挪到高位避开 vendor 语义 */
"""
    s = s[:old_enum.start()] + "enum msm_pcie_config {" + new_body + "};" + s[old_enum.end():]
    print("msm-pcie-hdr: enum msm_pcie_config 已按 vendor 口径对齐")

# ── 3) 补 MSM_PCIE_EVENT_LINK_RECOVER(vendor 有,我们没有) ──
if "MSM_PCIE_EVENT_LINK_RECOVER" not in s:
    m = re.search(r"(MSM_PCIE_EVENT_DRV_DISCONNECT\s*=\s*BIT\(5\),\n)", s)
    if m:
        s = s[:m.end()] + "\tMSM_PCIE_EVENT_LINK_RECOVER = BIT(6),\n" + s[m.end():]
        print("msm-pcie-hdr: 已补 MSM_PCIE_EVENT_LINK_RECOVER")

assert s != orig, "什么都没改?"
open(path, "w").write(s)
# 自证:结构体第一字段必须是 node
chk = re.search(r"struct msm_pcie_register_event \{\n(.*?)\n\};", s, re.S)
first = [l.strip() for l in chk.group(1).splitlines() if l.strip() and not l.strip().startswith(("/*","*"))][0]
print("msm-pcie-hdr: 结构体第一字段 = %r" % first)
assert first.startswith("struct list_head node;"), "第一字段不是 node ⇒ ABI 仍未对齐"
print("msm-pcie-hdr: ✅ 完成")
