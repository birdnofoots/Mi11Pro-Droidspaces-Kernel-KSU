#!/usr/bin/env python3
"""wlan-debug.py <kernel_root> —— 在 qcacld 的 probe/startup 链上插 pr_err 标记(MARSDBG)

背景: qcacld 的 QDF 日志默认不进内核 console(hdd_err/hdd_info 全都看不到, 实测连
      "probing driver" 都没有), 而 cnss2 只告诉我们 `Failed to probe host driver, err = -1`
      (QDF 的 qdf_status_to_os_return 把未映射状态统统变成 -EPERM)。
      所以只能自己插 printk 标记, 一次编译定位到具体哪一步返回失败。

覆盖:
  core/pld/src/pld_pcie.c              pld_pcie_probe  →  pld_add_dev → ops->probe
  core/hdd/src/wlan_hdd_driver_ops.c   hdd_soc_probe / __hdd_soc_probe 6 个步骤
  core/hdd/src/wlan_hdd_main.c         hdd_wlan_startup 前 7 个步骤
"""
import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
if os.path.basename(os.path.abspath(root)) != "qcacld-3.0":
    root = os.path.join(root, "drivers/staging/qcacld-3.0")


def patch(rel, edits):
    path = os.path.join(root, rel)
    s = open(path, errors="ignore").read()
    if "MARSDBG" in s:
        print("wlan-debug: %s 已打过, 跳过" % rel)
        return
    for old, new in edits:
        n = s.count(old)
        if n != 1:
            raise SystemExit("wlan-debug: %s 锚点命中 %d 次(应为 1):\n%s" % (rel, n, old[:120]))
        s = s.replace(old, new, 1)
    open(path, "w").write(s)
    print("wlan-debug: %s 已插入 %d 个标记" % (rel, len(edits)))


# ---------------- pld_pcie.c ----------------
patch("core/pld/src/pld_pcie.c", [
    ("""	ret = pld_add_dev(pld_context, &pdev->dev, NULL, PLD_BUS_TYPE_PCIE);
	if (ret)
		goto out;

	return pld_context->ops->probe(&pdev->dev,
		       PLD_BUS_TYPE_PCIE, pdev, (void *)id);""",
     """	ret = pld_add_dev(pld_context, &pdev->dev, NULL, PLD_BUS_TYPE_PCIE);
	pr_err("MARSDBG pld_pcie_probe: pld_add_dev=%d\\n", ret);
	if (ret)
		goto out;

	ret = pld_context->ops->probe(&pdev->dev,
		       PLD_BUS_TYPE_PCIE, pdev, (void *)id);
	pr_err("MARSDBG pld_pcie_probe: ops->probe=%d\\n", ret);
	return ret;"""),
])

# ---------------- wlan_hdd_driver_ops.c ----------------
patch("core/hdd/src/wlan_hdd_driver_ops.c", [
    # hdd_soc_probe
    ("""	errno = osif_psoc_sync_create_and_trans(&psoc_sync);
	if (errno)
		return errno;""",
     """	errno = osif_psoc_sync_create_and_trans(&psoc_sync);
	pr_err("MARSDBG hdd_soc_probe: psoc_sync_create_and_trans=%d\\n", errno);
	if (errno)
		return errno;"""),
    ("""	errno = __hdd_soc_probe(dev, bdev, bid, bus_type);
	if (errno)
		goto destroy_sync;""",
     """	errno = __hdd_soc_probe(dev, bdev, bid, bus_type);
	pr_err("MARSDBG hdd_soc_probe: __hdd_soc_probe=%d\\n", errno);
	if (errno)
		goto destroy_sync;"""),
    # __hdd_soc_probe 入口
    ("""	struct hdd_context *hdd_ctx;
	QDF_STATUS status;
	int errno;

	hdd_info("probing driver");

	hdd_soc_load_lock(dev);""",
     """	struct hdd_context *hdd_ctx;
	QDF_STATUS status;
	int errno;

	hdd_info("probing driver");
	pr_err("MARSDBG __hdd_soc_probe: enter\\n");

	hdd_soc_load_lock(dev);"""),
    ("""	cds_set_recovery_in_progress(false);

	errno = hdd_init_qdf_ctx(dev, bdev, bus_type, bid);
	if (errno)
		goto unlock;""",
     """	cds_set_recovery_in_progress(false);

	errno = hdd_init_qdf_ctx(dev, bdev, bus_type, bid);
	pr_err("MARSDBG __hdd_soc_probe: hdd_init_qdf_ctx=%d\\n", errno);
	if (errno)
		goto unlock;"""),
    ("""	errno = hdd_init_dma_mask(dev, bus_type);
	if (errno)
		goto unlock;""",
     """	errno = hdd_init_dma_mask(dev, bus_type);
	pr_err("MARSDBG __hdd_soc_probe: hdd_init_dma_mask=%d\\n", errno);
	if (errno)
		goto unlock;"""),
    ("""	hdd_ctx = hdd_context_create(dev);
	if (IS_ERR(hdd_ctx)) {""",
     """	hdd_ctx = hdd_context_create(dev);
	pr_err("MARSDBG __hdd_soc_probe: hdd_context_create=%p err=%ld\\n",
	       hdd_ctx, IS_ERR(hdd_ctx) ? PTR_ERR(hdd_ctx) : 0L);
	if (IS_ERR(hdd_ctx)) {"""),
    ("""	status = dp_prealloc_init((struct cdp_ctrl_objmgr_psoc *)hdd_ctx->psoc);

	if (status != QDF_STATUS_SUCCESS) {""",
     """	status = dp_prealloc_init((struct cdp_ctrl_objmgr_psoc *)hdd_ctx->psoc);
	pr_err("MARSDBG __hdd_soc_probe: dp_prealloc_init=%d\\n", status);

	if (status != QDF_STATUS_SUCCESS) {"""),
    ("""	errno = hdd_wlan_startup(hdd_ctx);
	if (errno)
		goto hdd_context_destroy;""",
     """	errno = hdd_wlan_startup(hdd_ctx);
	pr_err("MARSDBG __hdd_soc_probe: hdd_wlan_startup=%d\\n", errno);
	if (errno)
		goto hdd_context_destroy;"""),
    ("""	status = hdd_psoc_create_vdevs(hdd_ctx);
	if (QDF_IS_STATUS_ERROR(status)) {""",
     """	status = hdd_psoc_create_vdevs(hdd_ctx);
	pr_err("MARSDBG __hdd_soc_probe: hdd_psoc_create_vdevs=%d\\n", status);
	if (QDF_IS_STATUS_ERROR(status)) {"""),
])

# ---------------- wlan_hdd_main.c (hdd_wlan_startup) ----------------
patch("core/hdd/src/wlan_hdd_main.c", [
    ("""	status = wlan_hdd_cache_chann_mutex_create(hdd_ctx);
	if (QDF_IS_STATUS_ERROR(status))
		return qdf_status_to_os_return(status);""",
     """	status = wlan_hdd_cache_chann_mutex_create(hdd_ctx);
	pr_err("MARSDBG hdd_wlan_startup: cache_chann_mutex_create=%d\\n", status);
	if (QDF_IS_STATUS_ERROR(status))
		return qdf_status_to_os_return(status);"""),
    ("""	errno = hdd_init_regulatory_update_event(hdd_ctx);
	if (errno) {""",
     """	errno = hdd_init_regulatory_update_event(hdd_ctx);
	pr_err("MARSDBG hdd_wlan_startup: init_regulatory_update_event=%d\\n", errno);
	if (errno) {"""),
    ("""	errno = hdd_wlan_start_modules(hdd_ctx, false);
	if (errno) {""",
     """	errno = hdd_wlan_start_modules(hdd_ctx, false);
	pr_err("MARSDBG hdd_wlan_startup: start_modules=%d\\n", errno);
	if (errno) {"""),
    ("""	errno = hdd_wiphy_init(hdd_ctx);
	if (errno) {""",
     """	errno = hdd_wiphy_init(hdd_ctx);
	pr_err("MARSDBG hdd_wlan_startup: wiphy_init=%d\\n", errno);
	if (errno) {"""),
    ("""	errno = hdd_initialize_mac_address(hdd_ctx);
	if (errno) {""",
     """	errno = hdd_initialize_mac_address(hdd_ctx);
	pr_err("MARSDBG hdd_wlan_startup: initialize_mac_address=%d\\n", errno);
	if (errno) {"""),
    ("""	errno = register_netdevice_notifier(&hdd_netdev_notifier);
	if (errno) {""",
     """	errno = register_netdevice_notifier(&hdd_netdev_notifier);
	pr_err("MARSDBG hdd_wlan_startup: register_netdevice_notifier=%d\\n", errno);
	if (errno) {"""),
    ("""	status = wlansap_global_init();
	if (QDF_IS_STATUS_ERROR(status))
		goto unregister_notifiers;""",
     """	status = wlansap_global_init();
	pr_err("MARSDBG hdd_wlan_startup: wlansap_global_init=%d\\n", status);
	if (QDF_IS_STATUS_ERROR(status))
		goto unregister_notifiers;"""),
])
print("wlan-debug: 完成")
