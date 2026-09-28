#!/usr/bin/env python3
"""
make-bootimg.py — 用原厂 boot.img 的 header + ramdisk 拼出可直接 fastboot 的 boot.img

为什么不用 magiskboot repack:
  原厂 boot.img 头部偏移 576..608 有 32 字节原厂签名字段,ramdisk 也是原厂压缩字节。
  逐字节拼接可以保证除内核之外一个字节都不变。
  已用「把原厂内核塞回去」验证过:产物和能开机的 test2 md5 完全一致。

用法:
  make-bootimg.py <header.bin> <ramdisk.gz> <Image> <输出.img> [--no-ramdisk-mods]

--no-ramdisk-mods: 从 ramdisk 里删掉 vendor/lib/modules/*.ko
  (原厂模块和我们编的内核 CRC 不一致时,first-stage 加载失败可能直接打死 init)
"""
import gzip
import struct
import sys

PAGE = 4096
# 原厂 ramdisk 里这 5 个 vendor_dlkm 模块(设备无 vendor_dlkm 分区,被塞进了 boot ramdisk)
RAMDISK_KOS = {
    "vendor/lib/modules/adsp_loader_dlkm.ko",
    "vendor/lib/modules/apr_dlkm.ko",
    "vendor/lib/modules/q6_notifier_dlkm.ko",
    "vendor/lib/modules/q6_pdr_dlkm.ko",
    "vendor/lib/modules/snd_event_dlkm.ko",
}


def ru(x, a=PAGE):
    return (x + a - 1) // a * a


def strip_cpio_entries(cpio, drop):
    out = bytearray()
    i = 0
    n = 0
    while i + 110 <= len(cpio):
        if cpio[i:i + 6] != b"070701":
            break
        def fld(a, b):
            return int(cpio[i + a:i + b], 16)
        namesize = fld(94, 102)
        filesize = fld(54, 62)
        name = cpio[i + 110:i + 110 + namesize - 1].decode("utf-8", "replace")
        body = 110 + namesize
        body = (body + 3) // 4 * 4
        total = body + (filesize + 3) // 4 * 4
        if name not in drop:
            out += cpio[i:i + total]
        else:
            n += 1
        i += total
        if name == "TRAILER!!!":
            break
    sys.stderr.write("  cpio: 删除 %d 个条目,剩余 %d 字节\n" % (n, len(out)))
    return bytes(out)


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    hdr_path, ram_path, img_path, out_path = sys.argv[1:5]
    no_mods = "--no-ramdisk-mods" in sys.argv[5:]

    hdr = bytearray(open(hdr_path, "rb").read())
    assert hdr[:8] == b"ANDROID!" and len(hdr) == PAGE, "header 文件不对"
    hv = struct.unpack_from("<I", hdr, 40)[0]
    assert hv == 3, "只支持 header v3(本机就是 3)"

    ram = open(ram_path, "rb").read()
    if no_mods:
        cpio = gzip.decompress(ram)
        cpio = strip_cpio_entries(cpio, RAMDISK_KOS)
        ram = gzip.compress(cpio, 9)
        sys.stderr.write("  ramdisk 重新压缩: %d → %d 字节\n" % (len(open(ram_path, "rb").read()), len(ram)))

    kern = open(img_path, "rb").read()
    assert kern[:2] == b"MZ", "%s 看起来不是 arm64 Image" % img_path

    struct.pack_into("<I", hdr, 8, len(kern))
    struct.pack_into("<I", hdr, 12, len(ram))

    blob = bytes(hdr) + kern + b"\x00" * (ru(len(kern)) - len(kern))
    blob += ram + b"\x00" * (ru(len(blob) + len(ram)) - len(blob) - len(ram))

    open(out_path, "wb").write(blob)
    print("kernel  : %d 字节" % len(kern))
    print("ramdisk : %d 字节%s" % (len(ram), "  (已删掉 5 个 vendor 模块)" if no_mods else ""))
    print("输出    : %s  (%d 字节)" % (out_path, len(blob)))
    print("签名    : %s%s" % (bytes(hdr[576:608]).hex(),
                              "  (原厂签名字段,已保留)" if any(hdr[576:608]) else "  (全 0)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
