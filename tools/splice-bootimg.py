#!/usr/bin/env python3
"""
splice-bootimg.py — 把新编译的内核 Image 原样塞进原厂 boot.img

为什么不直接用 magiskboot repack?
  原厂 boot.img 头部 extra_cmdline 区域里有一段 32 字节的非零数据
  (偏移 576..608,例如 d1f61bf9...226622)。magiskboot repack 会保留它,
  但我们之前的打包流程把它清零了 —— 多引入了一个和内核无关的变量。
  本脚本做逐字节拼接:
    * 头部 4096 字节原样保留,只改 kernel_size
    * ramdisk 使用【原厂压缩字节】,不重新压缩
    * 不做任何 AVB / 签名处理

用法:
  splice-bootimg.py <参考boot.img> <新内核Image> <输出boot.img> [--trim]

--trim: 去掉尾部全零填充(得到真机分区实际内容长度)
"""
import struct, sys, os

PAGE = 4096


def ru(x, align=PAGE):
    return (x + align - 1) // align * align


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    ref, image, out = sys.argv[1], sys.argv[2], sys.argv[3]
    trim = "--trim" in sys.argv[4:]

    raw = open(ref, "rb").read()
    hdr = bytearray(raw[:PAGE])
    magic, ksz, rsz, osv, hsz, *_rest = struct.unpack_from("<8sIIIIIIIII", raw, 0)
    assert magic == b"ANDROID!", "not an Android boot image"
    hv = struct.unpack_from("<I", raw, 40)[0]
    assert hv == 3, "only header v3 is supported (got v%d)" % hv
    # v3: no second stage / recovery_dtbo / dtb in this device image
    assert struct.unpack_from("<I", raw, 1576)[0] == 0, "recovery_dtbo present, unsupported"
    assert struct.unpack_from("<I", raw, 1592)[0] == 0, "dtb present, unsupported"

    koff = PAGE
    roff = koff + ru(ksz)
    ramdisk = raw[roff:roff + rsz]
    assert len(ramdisk) == rsz, "truncated reference image"

    newk = open(image, "rb").read()
    assert newk[:4] == b"MZ\x00\x91" or newk[:2] == b"MZ", "image does not look like an arm64 Image"

    struct.pack_into("<I", hdr, 8, len(newk))

    blob = bytes(hdr) + newk + b"\x00" * (ru(len(newk)) - len(newk))
    blob += ramdisk
    blob += b"\x00" * (ru(len(blob)) - len(blob))

    if trim:
        blob = blob.rstrip(b"\x00")
        blob += b"\x00" * (PAGE - (len(blob) % PAGE)) if len(blob) % PAGE else b""

    open(out, "wb").write(blob)
    print("ref        : %s (%d bytes, kernel %d, ramdisk %d)" % (ref, len(raw), ksz, rsz))
    print("new kernel : %s (%d bytes)" % (image, len(newk)))
    print("output     : %s (%d bytes)" % (out, len(blob)))
    sig = hdr[576:608]
    print("header sig : %s%s" % (sig.hex(), "  (preserved)" if any(sig) else "  (was zero in ref)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
