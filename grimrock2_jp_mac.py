#!/usr/bin/env python3
"""Legend of Grimrock 2 日本語化パッチ Mac 用インストーラー

Windows 用の日本語化パッチ (grimrock2_jp.patch) を Mac 版 (Steam) の
grimrock2.dat に当てる。

Windows 版と Mac 版の grimrock2.dat は中身が少し違うため、元のパッチが
そのまま当たらないエントリは、LuaJIT バイトコードの文字列定数を
Mac 版の中から探して置き換え直す。

使い方:
  python3 grimrock2_jp_mac.py check     --patch PATH [--dat PATH]
  python3 grimrock2_jp_mac.py install   --patch PATH [--dat PATH]
  python3 grimrock2_jp_mac.py uninstall [--dat PATH]
"""
import argparse
import bisect
import hashlib
import os
import shutil
import struct
import subprocess
import sys

DEFAULT_DAT = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Legend of Grimrock 2/"
    "Legend of Grimrock 2.app/Contents/Resources/grimrock2.dat")
BACKUP_SUFFIX = ".orig"

# Lua 文字列リテラル用のエスケープ (翻訳フックが元スクリプトを埋め込むため)
ESC = [bytes([c]) if 32 <= c < 127 and c not in (34, 92) else ("\\%03d" % c).encode()
       for c in range(256)]


class PatchError(Exception):
    pass


# ---------------------------------------------------------------- パッチ形式

def read_patch(path):
    p = open(path, "rb").read()
    if p[:4] != b"GRJP" or struct.unpack_from("<I", p, 4)[0] != 2:
        raise PatchError("パッチファイルの形式が違います: %s" % path)
    n = struct.unpack_from("<I", p, 48)[0]
    entries, pos = [], 52
    for _ in range(n):
        h, cs, us, fl, kind, ln = struct.unpack_from("<IIIIIi", p, pos)
        entries.append(dict(hash=h, usize=us, flags=fl, kind=kind,
                            sha=p[pos + 24:pos + 56], body=p[pos + 56:pos + 56 + ln]))
        pos += 56 + ln
    return entries


def read_ops(body):
    ops, q = [], 0
    while q < len(body):
        op = body[q]
        if op == 1:
            l = struct.unpack_from("<i", body, q + 1)[0]
            ops.append((1, body[q + 5:q + 5 + l]))
            q += 5 + l
        else:
            a, l = struct.unpack_from("<ii", body, q + 1)
            ops.append((op, a, l))
            q += 9
    return ops


def apply_ops(orig, body):
    out = bytearray()
    for o in read_ops(body):
        if o[0] == 1:
            out += o[1]
        elif o[0] == 0:
            out += orig[o[1]:o[1] + o[2]]
        else:
            out += b"".join(ESC[c] for c in orig[o[1]:o[1] + o[2]])
    return bytes(out)


# ---------------------------------------------------------------- grimrock2.dat

def read_dat_table(path):
    with open(path, "rb") as f:
        head = f.read(8)
        if head[:4] != b"GRA2":
            raise PatchError("grimrock2.dat の形式が違います: %s" % path)
        cnt = struct.unpack_from("<I", head, 4)[0]
        tbl = f.read(20 * cnt)
    rows = [list(struct.unpack_from("<IIIII", tbl, 20 * i)) for i in range(cnt)]
    return head[:4], rows


def read_entry(f, row):
    f.seek(row[1])
    return f.read(row[2] or row[3])


# ---------------------------------------------------------------- LuaJIT バイトコード

def uleb(b, i):
    v = s = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return v, i


def enc_uleb(v):
    out = bytearray()
    while True:
        c, v = v & 0x7F, v >> 7
        if v:
            out.append(c | 0x80)
        else:
            out.append(c)
            return bytes(out)


def parse_bc(b):
    """stripped LuaJIT 2.0 バイトコードを読み、
    protos: [(長さ欄の開始, 本体の開始, 本体の長さ)]
    strs:   {文字列定数の開始(長さ欄を含む): 終端}
    を返す。"""
    if b[:3] != b"\x1bLJ":
        raise PatchError("LuaJIT バイトコードではありません")
    flags, i = uleb(b, 4)
    if not flags & 2:
        raise PatchError("デバッグ情報付きのバイトコードには対応していません")
    protos, strs = [], {}

    def kstr(pb, j, base):
        t, j2 = uleb(pb, j)
        if t >= 5:
            strs[base + j] = base + j2 + t - 5
            return j2 + t - 5
        return None

    while True:
        st = i
        ln, i = uleb(b, i)
        if ln == 0:
            break
        pb, base = b[i:i + ln], i
        nuv = pb[3]
        j = 4
        nkgc, j = uleb(pb, j)
        nkn, j = uleb(pb, j)
        nbc, j = uleb(pb, j)
        j += nbc * 4 + nuv * 2
        for _ in range(nkgc):
            e = kstr(pb, j, base)
            if e is not None:
                j = e
                continue
            tp, j = uleb(pb, j)
            if tp == 1:  # テーブル
                na, j = uleb(pb, j)
                nh, j = uleb(pb, j)
                for _ in range(na + 2 * nh):
                    e = kstr(pb, j, base)
                    if e is not None:
                        j = e
                        continue
                    t, j = uleb(pb, j)
                    if t == 3:
                        _, j = uleb(pb, j)
                    elif t == 4:
                        _, j = uleb(pb, j)
                        _, j = uleb(pb, j)
            elif tp in (2, 3):
                j += 8
            elif tp == 4:
                j += 16
        for _ in range(nkn):
            isnum = pb[j] & 1
            _, j = uleb(pb, j)
            if isnum:
                _, j = uleb(pb, j)
        if j != ln:
            raise PatchError("バイトコードの解析に失敗しました")
        protos.append((st, i, ln))
        i += ln
    if i != len(b):
        raise PatchError("バイトコードの末尾が想定と違います")
    return protos, strs


def split_strs(seg):
    out, i = [], 0
    while i < len(seg):
        t, j = uleb(seg, i)
        if t < 5 or j + t - 5 > len(seg):
            raise ValueError
        out.append(seg[i:j + t - 5])
        i = j + t - 5
    return out


def port_bytecode(mac, body):
    """Windows 版向けのパッチ操作を、Mac 版のバイトコードに当て直す。

    パッチの「挿入」が置き換えている元データの範囲 (gap) ごとに、
    Mac 版の中の対応する文字列定数を探して日本語に差し替え、
    関数プロトタイプの長さを計算し直す。"""
    ops = read_ops(body)
    protos, strs = parse_bc(mac)
    starts = sorted(strs)
    lenf = [(st, i) for st, i, _ in protos]

    # 元データの順に並んだコピー操作を目印に、gap と置き換え後のバイト列を取り出す
    gaps, cur, pending, win_size = [], 0, bytearray(), 0
    for o in ops:
        if o[0] == 1:
            pending += o[1]
        elif o[0] == 0 and o[1] >= cur:
            if o[1] > cur or pending:
                gaps.append((cur, o[1], bytes(pending)))
            pending, cur = bytearray(), o[1] + o[2]
            win_size = cur
        elif o[0] == 0:
            pending += mac[o[1]:o[1] + o[2]]  # 元データの別の場所の再利用
        else:
            raise PatchError("このエントリの形式には対応していません")
    if pending:
        raise PatchError("このエントリの形式には対応していません")

    # Mac 版は途中で前後にずれていることがある。ずれ幅は 0 と全体の差の間に収まる
    delta = len(mac) - win_size
    lo, hi = min(0, delta), max(0, delta)

    def cover(x):
        k = bisect.bisect_right(starts, x) - 1
        if k >= 0 and starts[k] <= x < strs[starts[k]]:
            return starts[k]
        return None

    repl, shift = {}, 0
    for a, b, new in gaps:
        cands = sorted(range(lo, hi + 1), key=lambda s: (abs(s - shift), s))
        if a == 0:
            continue  # ファイル先頭のヘッダーと最初の長さ欄
        hit = next((s for s in cands
                    if any(x <= a + s and b + s <= y for x, y in lenf)), None)
        if hit is not None:
            shift = hit
            continue  # プロトタイプの長さ欄: 後で計算し直す
        done = False
        for s in cands:
            st, en = a + s, b + s
            c0, c1 = cover(st), cover(en - 1)
            if c0 is None or c1 is None:
                continue
            run, p = [c0], c0
            while p != c1:
                p = strs[p]
                if p not in strs or p > c1:
                    run = None
                    break
                run.append(p)
            if not run:
                continue
            try:
                news = split_strs(mac[c0:st] + new + mac[en:strs[c1]])
            except (ValueError, IndexError):
                continue
            if len(news) != len(run):
                continue
            for k, ns in zip(run, news):
                repl[k] = (strs[k], ns)
            shift, done = s, True
            break
        if not done:
            raise PatchError("置き換える文字列が Mac 版の中に見つかりません (offset %d)" % a)

    hdr_end = 4 + len(enc_uleb(uleb(mac, 4)[0]))
    out = bytearray(mac[:hdr_end])
    for _, i, ln in protos:
        pb, p = bytearray(), i
        for k in sorted(x for x in repl if i <= x < i + ln):
            pb += mac[p:k] + repl[k][1]
            p = repl[k][0]
        pb += mac[p:i + ln]
        out += enc_uleb(len(pb)) + pb
    out += b"\x00"
    out = bytes(out)
    parse_bc(out)  # 組み立て結果が正しいバイトコードか確かめる
    return out, len(repl)


# ---------------------------------------------------------------- 本体

def build_entries(patch_path, dat_path, verbose=True):
    entries = read_patch(patch_path)
    _, rows = read_dat_table(dat_path)
    index = {r[0]: i for i, r in enumerate(rows)}
    if any(e["kind"] == 0 and e["hash"] in index for e in entries):
        raise PatchError("すでに日本語化済みのようです。入れ直す場合は先に uninstall を実行してください。")
    built, n_same, n_port = [], 0, 0
    with open(dat_path, "rb") as f:
        for e in entries:
            h = e["hash"]
            if e["kind"] == 0:
                data = e["body"]
            else:
                if h not in index:
                    raise PatchError("grimrock2.dat に必要なデータがありません (%08x)" % h)
                orig = read_entry(f, rows[index[h]])
                data = apply_ops(orig, e["body"])
                if hashlib.sha256(data).digest() == e["sha"]:
                    n_same += 1
                else:
                    data, nrep = port_bytecode(orig, e["body"])
                    n_port += 1
                    if verbose:
                        print("  %08x: Mac 版に合わせて %d 個の文字列を置き換え" % (h, nrep))
            built.append((h, data, e["flags"]))
    if verbose:
        n_new = sum(1 for e in entries if e["kind"] == 0)
        print("パッチ %d 件: そのまま適用 %d / Mac 版に合わせて変換 %d / 追加 %d"
              % (len(entries), n_same, n_port, n_new))
    return built


def write_patched(dat_path, built):
    magic, rows = read_dat_table(dat_path)
    index = {r[0]: i for i, r in enumerate(rows)}
    n_new = sum(1 for h, _, _ in built if h not in index)
    new_end = 8 + 20 * (len(rows) + n_new)
    with open(dat_path, "r+b") as g:
        # 表が広がる分の場所にあるデータを末尾へ移す
        for r in rows:
            if r[1] < new_end:
                buf = read_entry(g, r)
                g.seek(0, 2)
                r[1] = g.tell()
                g.write(buf)
        for h, data, fl in built:
            g.seek(0, 2)
            row = [h, g.tell(), 0, len(data), fl]
            g.write(data)
            if h in index:
                rows[index[h]] = row
            else:
                rows.append(row)
        tbl = bytearray(magic + struct.pack("<I", len(rows)))
        for r in rows:
            tbl += struct.pack("<IIIII", *r)
        g.seek(0)
        g.write(tbl)


def game_running():
    try:
        return subprocess.run(["pgrep", "-x", "grimrock2"],
                              stdout=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def need_file(path, what):
    if not os.path.isfile(path):
        raise PatchError("%s が見つかりません: %s" % (what, path))


def cmd_check(args):
    need_file(args.patch, "パッチファイル")
    need_file(args.dat, "grimrock2.dat")
    build_entries(args.patch, args.dat)
    print("\nこの grimrock2.dat に日本語化パッチを当てられます。")


def cmd_install(args):
    need_file(args.patch, "パッチファイル")
    need_file(args.dat, "grimrock2.dat")
    if game_running():
        raise PatchError("ゲームを終了してから実行してください。")
    print("grimrock2.dat: %s" % args.dat)
    print("パッチを組み立て中...")
    built = build_entries(args.patch, args.dat)
    bak = args.dat + BACKUP_SUFFIX
    if not os.path.exists(bak):
        print("バックアップを作成中: %s (約 1GB)..." % os.path.basename(bak))
        shutil.copyfile(args.dat, bak)
    print("パッチを適用中...")
    write_patched(args.dat, built)
    print("\n日本語化が完了しました。")


def cmd_uninstall(args):
    bak = args.dat + BACKUP_SUFFIX
    need_file(bak, "バックアップ")
    if game_running():
        raise PatchError("ゲームを終了してから実行してください。")
    os.replace(bak, args.dat)
    print("元の英語版に戻しました。")


def main():
    ap = argparse.ArgumentParser(description="Legend of Grimrock 2 日本語化パッチ (Mac 用)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("check", cmd_check, "パッチを当てられるか確かめる (何も書き換えない)"),
                            ("install", cmd_install, "日本語化する"),
                            ("uninstall", cmd_uninstall, "英語版に戻す")):
        sp = sub.add_parser(name, help=help_)
        if name != "uninstall":
            sp.add_argument("--patch", required=True, help="grimrock2_jp.patch のパス")
        sp.add_argument("--dat", default=DEFAULT_DAT, help="grimrock2.dat のパス (省略時は Steam の標準の場所)")
        sp.set_defaults(func=fn)
    args = ap.parse_args()
    try:
        args.func(args)
    except PatchError as e:
        print("\nエラー: %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
