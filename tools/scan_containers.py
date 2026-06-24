#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
掃 Minecraft region(.mca)檔,數每個 chunk 的容器 block-entity 數量,找出「箱子最密 =
最操 LazyContainer」的 chunk,印出方塊座標(供你複製該 region 去測)。Python 3.5 相容。

免裝 NBT 函式庫:解壓每個 chunk 後直接在 bytes 裡數容器 id 字串。會略為高估(方塊 palette 也含
一次 id),作為密度排名足夠。

用法:  python3 scan_containers.py <world/region 目錄> [topN]
"""
import sys, os, glob, struct, zlib, gzip

CONTAINERS = [b'minecraft:chest', b'minecraft:trapped_chest',
              b'minecraft:barrel', b'minecraft:shulker_box']

def decomp(data, ctype):
    if ctype == 1: return gzip.decompress(data)
    if ctype == 2: return zlib.decompress(data)
    if ctype == 3: return data
    if ctype == 4:
        import lz4.block
        return lz4.block.decompress(data)
    raise ValueError("compression %d" % ctype)

def count_containers(buf):
    n = 0
    for s in CONTAINERS:
        n += buf.count(s)
    return n

def scan_region(path):
    base = os.path.basename(path)            # r.X.Z.mca
    try:
        parts = base.split('.')
        rx, rz = int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return []
    out = []
    with open(path, 'rb') as f:
        header = f.read(4096)
        if len(header) < 4096:
            return []
        for i in range(1024):
            off = struct.unpack('>I', b'\x00' + header[i*4:i*4+3])[0]
            cnt = header[i*4+3]
            if off == 0 or cnt == 0:
                continue
            f.seek(off * 4096)
            try:
                length = struct.unpack('>I', f.read(4))[0]
                ctype = f.read(1)[0]
                if ctype & 0x80:        # 外部 .mcc 超大 chunk,略過
                    continue
                buf = decomp(f.read(length - 1), ctype)
            except Exception:
                continue
            c = count_containers(buf)
            if c:
                out.append((rx*32 + i % 32, rz*32 + i // 32, c))
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    region_dir = sys.argv[1]
    topN = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    files = sorted(glob.glob(os.path.join(region_dir, 'r.*.mca')))
    if not files:
        print("找不到 .mca:" + region_dir); sys.exit(1)
    chunks, region_tot = [], {}
    for fp in files:
        res = scan_region(fp)
        chunks.extend(res)
        s = sum(c for _, _, c in res)
        if s:
            region_tot[os.path.basename(fp)] = s
    chunks.sort(key=lambda t: -t[2])
    total = sum(c for _, _, c in chunks)
    print("\n掃了 {} 個 region,容器(含palette)約 {},有容器的 chunk {} 個。\n".format(
        len(files), total, len(chunks)))
    print("== 容器最密的 region(複製整個 .mca 最方便)==")
    for name, s in sorted(region_tot.items(), key=lambda kv: -kv[1])[:10]:
        print("  {:18s} 約 {} 個容器".format(name, s))
    print("\n== 容器最密的 {} 個 chunk(blockX/Z = 該 chunk 西北角)==".format(topN))
    print("  {:>7} {:>7} {:>8} {:>8} {:>6}   去這裡測".format(
        'chunkX', 'chunkZ', 'blockX', 'blockZ', '容器'))
    for cx, cz, c in chunks[:topN]:
        print("  {:7d} {:7d} {:8d} {:8d} {:6d}   /tp {} ~ {}  (r.{}.{}.mca)".format(
            cx, cz, cx*16, cz*16, c, cx*16+8, cz*16+8, cx >> 5, cz >> 5))

if __name__ == '__main__':
    main()
