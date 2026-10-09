#!/usr/bin/env python3
"""wlan-profile.py <kernel_root> [输出目录] —— 给 qcacld 钉死「mars(SM8350/QCA6490/PCIe)」平台档位

为什么需要:
  QTI 的 `configs/default_defconfig` 用一大串 `ifeq` 从 **内核 .config** 里猜总线
  (`CONFIG_ROME_IF` ← CONFIG_CNSS/CNSS2/ICNSS/ICNSS2/CNSS_QCA6xxx/LITHIUM…)。
  我们的 config 是原厂 MIUI 的, 里面 `CONFIG_ICNSS2=m`、`CONFIG_CNSS2=m` 同时存在,
  于是它可能猜成 snoc/ipci; 再叠加各分支的"默认值", 会出现自相矛盾的组合(实测):
    * `HIF_PCI=y` + `HIF_IPCI=y` ⇒ regtable_pcie.h / regtable_ipcie.h 同 TU 重定义
    * `WLAN_TX_FLOW_CONTROL_V2=y` + `..._LEGACY=y` ⇒ ol_txrx_flow_control.o 与
      ol_txrx_legacy_flow_control.o 都有 ol_txrx_vdev_pause/unpause ⇒ ld duplicate symbol
    * `IPA_OFFLOAD=y` 但内核 `include/linux/ipa.h` 给的是 stub `static inline ipa_is_ready()`
      ⇒ 与 components/ipa/.../wlan_ipa_obj_mgmt_api.c 里的定义重定义

做法: 把档位覆盖**追加到 configs/default_defconfig 末尾**(make 语义: 后写覆盖先写),
      同时把同样的开关写成 make 变量文件给外部模块(M=)用。
      mars 的硬件事实: WLAN = QCA6490 over **PCIe**, 走 cnss2(PLD_PCIE_CNSS_FLAG);
      IPA offload / USB / SDIO / SNOC / IPCI 全不需要。
"""
import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"

# (符号, 值) —— 顺序即写入顺序
PROFILE = [
    ("CONFIG_ROME_IF", "pci"),
    ("CONFIG_HIF_PCI", "y"),
    ("CONFIG_HIF_IPCI", "n"),
    ("CONFIG_HIF_SNOC", "n"),
    ("CONFIG_HIF_USB", "n"),
    ("CONFIG_HIF_SDIO", "n"),
    ("CONFIG_PLD_PCIE_CNSS_FLAG", "y"),
    ("CONFIG_PLD_PCIE_INIT_FLAG", "y"),
    ("CONFIG_PLD_SNOC_ICNSS_FLAG", "n"),
    ("CONFIG_PLD_IPCI_ICNSS_FLAG", "n"),
    ("CONFIG_WLAN_TX_FLOW_CONTROL_V2", "y"),
    ("CONFIG_WLAN_TX_FLOW_CONTROL_LEGACY", "n"),
    ("CONFIG_FEATURE_SKB_PRE_ALLOC", "n"),
    # 注意: 这里**不要**动 CONFIG_IPA_OFFLOAD。
    # los43 实测: 显式 `CONFIG_IPA_OFFLOAD := n` 会把 default_defconfig 里
    #   ifeq ($(CONFIG_IPA_OFFLOAD), y) → CONFIG_ENABLE_SMMU_S1_TRANSLATION := y
    # 那条删掉, 而 cmn 的 qdf_ipa.h 只在 `#ifdef ENABLE_SMMU_S1_TRANSLATION` 里声明
    # qdf_get_ipa_smmu_enabled(), cds_api.c 却无条件调用它
    #   ⇒ ../core/cds/src/cds_api.c:2873: error: implicit declaration of function
    #     'qdf_get_ipa_smmu_enabled'  (modules rc=2, wlan.ko 变成缓存里的旧文件!)
    # 树内编译本来就按内核 .config 自然取值, 不需要我们钉。
]

d = os.path.join(root, "drivers/staging/qcacld-3.0/configs")
cfg = os.path.join(d, "default_defconfig")
if os.path.exists(cfg):
    with open(cfg) as f:
        txt = f.read()
    if "MARS PROFILE OVERRIDE" not in txt:
        with open(cfg, "a") as f:
            f.write("\n# ===== MARS PROFILE OVERRIDE (SM8350/QCA6490/PCIe) =====\n")
            for k, v in PROFILE:
                f.write("%s := %s\n" % (k, v))
        print("wlan-profile: 已把档位覆盖追加到 %s" % cfg)
    else:
        print("wlan-profile: %s 已有覆盖, 跳过追加" % cfg)
else:
    print("wlan-profile: 找不到 %s (树里没有 qcacld?), 只产出 make 变量" % cfg)

mk = os.path.join(outdir, "wlan_profile.txt")
with open(mk, "w") as f:
    for k, v in PROFILE:
        f.write("%s=%s\n" % (k, v))
print("wlan-profile: make 变量 → %s" % mk)
for k, v in PROFILE:
    print("  %-40s = %s" % (k, v))
