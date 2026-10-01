#!/usr/bin/env python3
"""给 KGSL 补上 KGSL_PROP_VK_DEVICE_ID(0x2A) —— surfaceflinger 起不来的真正根因。

★ 铁证(2026-10-02,从失败启动的用户态 logcat 抓到):
    E Adreno-GSL: <ioctl_kgsl_device_getinfo_ext:1572>:
                  Error -2 attempting to get the VK_DEVICE_ID property
    W libEGL  : eglInitialize(0x...) failed (EGL_BAD_ALLOC)
    W RenderEngine: no suitable EGLConfig found, trying a simpler query
    F RenderEngine: no suitable EGLConfig found, giving up
  ⇒ surfaceflinger abort ⇒ 启动循环。
  根因不是显示/GPU 固件/SELinux,而是:我们编的这棵树(官方 star-r-oss,
  Android 11 时代)的 KGSL 比设备原厂内核(Android 13 / MIUI 14)旧,
  少一个新属性;而原厂用户态 libgsl.so 里就有字符串
    "KGSL_PROP_VK_DEVICE_ID not available at run time"
  该 ioctl 失败被 libgsl 当成致命错误。

★ 参考实现(同 SM8350:arter97/android_kernel_oneplus_sm8350):
    include/uapi/linux/msm_kgsl.h:
        #define KGSL_PROP_GPU_MODEL      0x29
        #define KGSL_PROP_VK_DEVICE_ID   0x2A
    drivers/gpu/msm/adreno.c:
        adreno_prop_u32(): else if (type == KGSL_PROP_VK_DEVICE_ID)
                                   val = adreno_get_vk_device_id(device);
        adreno_property_funcs[]: { KGSL_PROP_VK_DEVICE_ID, adreno_prop_u32 }
        adreno_get_vk_device_id(): 读 DT "qcom,vk-device-id",
                                   读不到就返回 chipid
  本机 DT(/sys/firmware/devicetree/base/soc/qcom,kgsl-3d0@3d00000/)里
  【没有】qcom,vk-device-id ⇒ 原厂行为就是返回 chipid ⇒ 与参考实现的
  回退分支完全一致。

★ 用户态侧核对(反汇编 /vendor/lib64/libgsl.so):
    mov w1, #0x2a                ; property_type = 0x2a
    mov w1, #0x902 / movk #0xc018 ; ioctl = 0xc0180902 (GETPROPERTY, size 24)
    ⇒ 只需要返回 4 字节 u32。libgsl 只查 0x20 / 0x28 / 0x2a,前两个我们已有。
"""
import sys

HDR = 'include/uapi/linux/msm_kgsl.h'
ADR = 'drivers/gpu/msm/adreno.c'


def patch(path, subs):
    s = open(path).read()
    orig = s
    for old, new, desc in subs:
        if old not in s:
            if new.strip() and new.strip() in s:
                print("  [跳过] %s(已存在)" % desc)
                continue
            print("  [失败] 锚点缺失: %s (%s)" % (desc, path))
            sys.exit(1)
        s = s.replace(old, new, 1)
        print("  [ok] %s" % desc)
    if s != orig:
        open(path, 'w').write(s)


HDR_SUBS = [(
    '#define KGSL_PROP_CONTEXT_PROPERTY\t0x28',
    '#define KGSL_PROP_CONTEXT_PROPERTY\t0x28\n'
    '#define KGSL_PROP_VK_DEVICE_ID\t\t0x2A',
    'UAPI 常量 KGSL_PROP_VK_DEVICE_ID = 0x2A',
)]

HELPER = '''/*
 * ★ mars 补丁:VK_DEVICE_ID。
 *   用户态 libgsl 在 eglInitialize 里必须拿到这个属性,拿不到就直接
 *   EGL_BAD_ALLOC ⇒ surfaceflinger 自杀。取值与原厂一致:DT 里
 *   qcom,vk-device-id 优先,没有就用 chipid(本机 DT 没有该属性)。
 */
static u32 adreno_get_vk_device_id(struct kgsl_device *device)
{
\tstatic u32 device_id;

\tif (device_id)
\t\treturn device_id;

\tif (of_property_read_u32(device->pdev->dev.of_node,
\t\t\t\t "qcom,vk-device-id", &device_id))
\t\tdevice_id = ADRENO_DEVICE(device)->chipid;

\tpr_info("kgsl: VK_DEVICE_ID = 0x%x\\n", device_id);
\treturn device_id;
}

static int adreno_prop_u32('''

ADR_SUBS = [
    ('static int adreno_prop_u32(',
     HELPER,
     'adreno_get_vk_device_id() 取值函数'),
    ('\telse if (param->type == KGSL_PROP_SPEED_BIN)\n'
     '\t\tval = device->speed_bin;\n',
     '\telse if (param->type == KGSL_PROP_SPEED_BIN)\n'
     '\t\tval = device->speed_bin;\n'
     '\telse if (param->type == KGSL_PROP_VK_DEVICE_ID)\n'
     '\t\tval = adreno_get_vk_device_id(device);\n',
     'adreno_prop_u32() 里处理该属性'),
    ('\t{ KGSL_PROP_GAMING_BIN, adreno_prop_gaming_bin },\n',
     '\t{ KGSL_PROP_GAMING_BIN, adreno_prop_gaming_bin },\n'
     '\t{ KGSL_PROP_VK_DEVICE_ID, adreno_prop_u32 },\n',
     'adreno_property_funcs[] 注册'),
]

print("=== mars 补丁:KGSL_PROP_VK_DEVICE_ID ===")
patch(HDR, HDR_SUBS)
patch(ADR, ADR_SUBS)
print("=== 完成 ===")
