#!/usr/bin/env python3
"""
patch-crcs.py — 把内核里的 kABI CRC 表改写成原厂值,让原厂的 .ko 能加载

原理(vmlinux 里已验证):
  * __ksymtab / __ksymtab_gpl 是 struct kernel_symbol 数组,每项 24 字节
    { unsigned long value; const char *name; const char *namespace; }
  * __kcrctab / __kcrctab_gpl 是平行的 u32 数组,第 i 项就是第 i 个符号的 CRC
    (已核对:kcrctab[i] == __crc_<name_i>)
  * 模块加载时 check_version() 拿模块 __versions 里的 CRC 和这张表比,
    不一致就拒绝加载 —— 这就是原厂模块全部加载失败的根因。

用法:
  patch-crcs.py <stock-crcs.txt> <vmlinux>

之后用 `make O=out Image` 重新生成 Image 即可(Image 是 objcopy 出来的,
会带上被改写过的 .rodata)。
"""
import mmap
import struct
import sys

PAGE = 4096
KSYM_ENTRY = 24  # struct kernel_symbol, arm64 上 PREL32 关闭时


class Elf:
    def __init__(self, path):
        self.writable = "--dry-run" not in sys.argv
        self.f = open(path, "r+b" if self.writable else "rb")
        self.m = mmap.mmap(self.f.fileno(), 0,
                           access=mmap.ACCESS_WRITE if self.writable else mmap.ACCESS_READ)
        m = self.m
        e_shoff = self.u64(0x28)
        e_shentsize = self.u16(0x3A)
        e_shnum = self.u16(0x3C)
        e_shstrndx = self.u16(0x3E)
        sh = [struct.unpack_from("<IIQQQQ", m, e_shoff + i * e_shentsize) for i in range(e_shnum)]
        strtab = bytes(m[sh[e_shstrndx][4]:sh[e_shstrndx][4] + sh[e_shstrndx][5]])

        def name(off):
            e = strtab.find(b"\0", off)
            return strtab[off:e].decode()

        self.secs = {}
        for i, (n, t, fl, addr, off, size) in enumerate(sh):
            self.secs[name(n)] = {"idx": i, "addr": addr, "off": off, "size": size}
        self._ranges = sorted(
            (s["addr"], s["addr"] + s["size"], s["off"]) for s in self.secs.values() if s["size"] > 0
        )

    def u16(self, o):
        return struct.unpack_from("<H", self.m, o)[0]

    def u32(self, o):
        return struct.unpack_from("<I", self.m, o)[0]

    def u64(self, o):
        return struct.unpack_from("<Q", self.m, o)[0]

    def v2o(self, va):
        for a, e, o in self._ranges:
            if a <= va < e:
                return o + (va - a)
        return None

    def rdstr(self, va):
        o = self.v2o(va)
        if o is None:
            return None
        e = self.m.find(b"\0", o)
        return bytes(self.m[o:e]).decode("utf-8", "replace")


def load_stock(path):
    d = {}
    for line in open(path):
        line = line.rstrip("\n")
        if not line or "\t" not in line:
            continue
        n, c = line.split("\t")
        d[n] = int(c, 16)
    return d


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dry = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    stock = load_stock(args[0])
    e = Elf(args[1])

    patched = 0
    seen = set()
    for kt in sorted(k for k in e.secs if k.startswith("__ksymtab") and k != "__ksymtab_strings"):
        ct = kt.replace("__ksymtab", "__kcrctab")
        if ct not in e.secs:
            continue
        ksz = e.secs[kt]["size"]
        csz = e.secs[ct]["size"]
        n = ksz // KSYM_ENTRY
        if csz // 4 != n:
            print("  跳过 %s: 条目数不一致 (%d vs %d)" % (kt, n, csz // 4))
            continue
        for i in range(n):
            eo = e.secs[kt]["off"] + i * KSYM_ENTRY
            name = e.rdstr(e.u64(eo + 8))
            if name is None:
                continue
            seen.add(name)
            want = stock.get(name)
            if want is None:
                continue
            co = e.secs[ct]["off"] + i * 4
            cur = e.u32(co)
            if cur != want:
                if not dry:
                    struct.pack_into("<I", e.m, co, want)
                patched += 1

    missing = sorted(k for k in stock if k not in seen)
    print("原厂需要的符号      : %d" % len(stock))
    print("本内核导出的可比对  : %d" % len(seen & set(stock)))
    print("CRC 与原厂不一致     : %d%s" % (patched, "  (dry-run,未改写)" if dry else "  (已改写为原厂值)"))
    print("本内核【没有导出】的: %d" % len(missing))
    if missing:
        print("  " + ", ".join(missing[:40]))
        print("  ^ 这些符号对应的模块仍然会加载失败(Unknown symbol),需要在配置里补")
    if not dry:
        e.m.flush()
    e.m.close()
    e.f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
