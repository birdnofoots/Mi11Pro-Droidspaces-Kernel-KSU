#!/usr/bin/env python3
"""
mars 自编内核补丁:固件加载器对 -EACCES 重试

背景(2026-10-02 实测):
  自编内核启动比原厂"快"约 7 秒,用户态在 5.67s 就扫描硬件并触发 A660 GPU 固件请求,
  而此时 /vendor/firmware 里的固件对内核还不可读(返回 -EACCES),ueventd 也还没能力
  服务 sysfs 回退 ⇒ 固件永久加载失败 ⇒ Adreno GPU 起不来 ⇒ surfaceflinger 的
  RenderEngine 拿不到 EGLConfig("no suitable EGLConfig found, giving up")而自杀
  ⇒ 启动永远完不成 ⇒ 106 秒时 init powerctl 重启。

  原厂在 12.6s 才请求同一批固件(那时已可读)⇒ 一次成功。

修法:遇到 -EACCES 时重试(最多 10 秒)。ENOENT 等其它错误保持原行为,不影响启动速度。
"""
import sys

P = "drivers/base/firmware_loader/main.c"

MARK = "mars 补丁"

s = open(P, encoding="utf-8").read()
if MARK in s:
    print("✅ 补丁已存在,跳过")
    sys.exit(0)

# 1) 需要 msleep()
if "#include <linux/delay.h>" not in s:
    anchor = "#include <linux/timer.h>"
    assert anchor in s, "找不到 include 锚点"
    s = s.replace(anchor, anchor + "\n#include <linux/delay.h>", 1)
    print("   + #include <linux/delay.h>")

# 2) 声明 retry 变量
old_decl = "\tint i, len;\n"
assert old_decl in s, "找不到 `int i, len;` 声明"
s = s.replace(old_decl, "\tint i, len, retry;\n", 1)
print("   + int retry 声明")

# 3) 把 kernel_read_file_from_path 包进重试循环
old = """		fw_priv->size = 0;
		rc = kernel_read_file_from_path(path, &buffer, &size,
						msize, id);
		if (rc) {
"""
new = """		fw_priv->size = 0;
		/*
		 * ★ mars 补丁:早期启动阶段 /vendor/firmware 对内核还不可读(返回
		 *   -EACCES),而 ueventd 这时也还没法服务 sysfs 回退 ⇒ 固件会永久
		 *   加载失败。实测:A660 GPU 固件失败的后果是 surfaceflinger 拿不到
		 *   EGLConfig 而自杀,系统启动彻底卡死。这里对 -EACCES 重试,
		 *   最多等 10 秒;-ENOENT 等其它错误保持原行为(不拖慢启动)。
		 */
		for (retry = 0; retry < 40; retry++) {
			rc = kernel_read_file_from_path(path, &buffer, &size,
							msize, id);
			if (rc != -EACCES)
				break;
			if (retry == 0)
				dev_warn(device, "mars: %s 暂不可读(-EACCES),重试等待用户态就绪\\n",
					 path);
			msleep(250);
		}
		if (rc) {
"""
assert old in s, "找不到 kernel_read_file_from_path 调用块"
s = s.replace(old, new, 1)
print("   + -EACCES 重试循环")

open(P, "w", encoding="utf-8").write(s)
print("✅ firmware loader 重试补丁已应用")
