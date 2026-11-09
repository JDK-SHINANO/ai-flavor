#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词库合并器 v2：raw/*.tsv（10 列）→ lexicon.tsv + conflicts.md

用法:
  python3 merge_lexicon.py            # 合并并写文件
  python3 merge_lexicon.py --check    # 只校验

做五件事:
  1. 校验：列数、层、轴、类型、置信度、正则、register_scope
  2. 去重：键 = (term, axis)
  3. 解冲突：同词不同轴时取高置信度，跨轴冲突留档待人工裁决
  4. 排序：层（词法→句法→篇章→语用→修辞）→ 轴 → 规则 → 置信度
  5. 出报告：层×轴分布、退回条目、未落 R1–R9 的条目、冲突组

不自动裁决语义。合并只做排序与去重，判断留给人。
"""
import os, re, sys, glob, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "lexicon.tsv")
REPORT = os.path.join(HERE, "conflicts.md")

COLS = ["term", "type", "level", "axis", "rule", "conf", "register_scope",
        "example", "source", "note"]
LEVELS = {"词法": 0, "句法": 1, "篇章": 2, "语用": 3, "修辞": 4}
AXES = {"甲": 0, "乙": 1, "丙": 2}
CONFS = {"high": 0, "mid": 1, "low": 2}
TYPES = {"word", "pattern"}
REG_RE = re.compile(r"R[1-9]")


def norm(s):
    return (s or "").strip()


def load_files():
    rows, bad = [], []
    files = sorted(glob.glob(os.path.join(RAW, "*.tsv")))
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for ln, line in enumerate(fh, 1):
                if not line.strip() or line.startswith("term\t"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 10:
                    bad.append(({"_src": os.path.basename(f), "_ln": ln,
                                 "term": cols[0] if cols else ""},
                                f"列数 {len(cols)} < 10（旧 8 列格式？）"))
                    continue
                d = dict(zip(COLS, cols[:10]))
                d["_src"], d["_ln"] = os.path.basename(f), ln
                rows.append(d)
    return rows, bad, files


def validate(rows):
    ok, bad = [], []
    for d in rows:
        t, typ = norm(d["term"]), norm(d["type"])
        lv, ax, conf = norm(d["level"]), norm(d["axis"]), norm(d["conf"])
        if not t:
            bad.append((d, "term 为空")); continue
        if typ not in TYPES:
            bad.append((d, f"type 非法: {typ}")); continue
        if lv not in LEVELS:
            bad.append((d, f"level 非法: {lv}（须为 词法/句法/篇章/语用/修辞）")); continue
        if ax not in AXES:
            bad.append((d, f"axis 非法: {ax}")); continue
        if conf not in CONFS:
            bad.append((d, f"conf 非法: {conf}")); continue
        src = norm(d["source"])
        if not src:
            bad.append((d, "source 为空")); continue
        if not norm(d["example"]):
            # 有 URL 的必须给原文例句；只有文献标识（论文附录词表）允许无例句
            if "http" in src:
                bad.append((d, "有 URL 却无例句（必须原样摘录，不得自造）")); continue
            d["example"] = "（词表项，无例句）"
            d["_noex"] = True
        scope = norm(d["register_scope"])
        if not scope:
            bad.append((d, "register_scope 为空（旧格式？须补 R1–R9 或「待定」）")); continue
        if typ == "pattern":
            try:
                re.compile(t)
            except re.error as e:
                bad.append((d, f"正则无法编译: {e}")); continue
        if typ == "word" and ("|" in t or "\t" in t):
            bad.append((d, "word 含非法字符 | 或 TAB")); continue
        d.update(term=t, type=typ, level=lv, axis=ax, conf=conf, register_scope=scope)
        d["rule"] = norm(d["rule"]).upper()
        ok.append(d)
    return ok, bad


def dedupe(rows):
    best, conflicts = {}, []
    for d in rows:
        key = (d["term"], d["axis"])
        cur = best.get(key)
        if cur is None:
            best[key] = dict(d, _n=1)
            continue
        cur["_n"] += 1
        if CONFS[d["conf"]] < CONFS[cur["conf"]]:
            d["_n"] = cur["_n"]; best[key] = d
        elif d["conf"] == cur["conf"] and len(d["example"]) > len(cur["example"]):
            d["_n"] = cur["_n"]; best[key] = d
    by_term = {}
    for d in best.values():
        by_term.setdefault(d["term"], []).append(d)
    for term, ds in by_term.items():
        if len({x["axis"] for x in ds}) > 1:
            conflicts.append(ds)
    return list(best.values()), conflicts


def order(rows):
    """层 → 语言（中文先，便于人读）→ 轴 → 规则 → 置信度。"""
    zh = re.compile(r"[\u4e00-\u9fff]")
    return sorted(rows, key=lambda d: (LEVELS[d["level"]],
                                       0 if zh.search(d["term"]) else 1,
                                       AXES[d["axis"]], d["rule"],
                                       CONFS[d["conf"]], d["term"]))


def write(rows):
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\t".join(COLS) + "\n")
        for d in rows:
            fh.write("\t".join(norm(d[c]).replace("\t", " ").replace("\n", " ")
                               for c in COLS) + "\n")


def report(rows, bad, conflicts, files):
    L = ["# 词库合并报告\n", f"输入 {len(files)} 份，有效 {len(rows)} 条。\n"]
    L.append("\n## 来源\n\n| 文件 | 条数 |\n|---|---|")
    for f in files:
        b = os.path.basename(f)
        L.append(f"| {b} | {sum(1 for d in rows if d['_src'] == b)} |")
    noex = sum(1 for d in rows if d.get("_noex"))
    if noex:
        L.append(f"\n其中 **{noex} 条为论文/词表项，无原文例句**（学术附录的 excess words，本无例句）。")
    L.append("\n## 按层\n\n| 层 | 条数 |\n|---|---|")
    for lv in LEVELS:
        L.append(f"| {lv} | {sum(1 for d in rows if d['level'] == lv)} |")
    L.append("\n## 按轴\n\n| 轴 | 条数 |\n|---|---|")
    for ax in AXES:
        L.append(f"| {ax} | {sum(1 for d in rows if d['axis'] == ax)} |")
    L.append("\n## 按置信度\n\n| 级 | 条数 |\n|---|---|")
    for c in CONFS:
        L.append(f"| {c} | {sum(1 for d in rows if d['conf'] == c)} |")
    L.append("\n## 层 × 轴\n\n|  | 甲 | 乙 | 丙 |\n|---|---|---|---|")
    for lv in LEVELS:
        cells = [sum(1 for d in rows if d["level"] == lv and d["axis"] == ax) for ax in AXES]
        L.append(f"| {lv} | " + " | ".join(map(str, cells)) + " |")
    unscoped = [d for d in rows if not REG_RE.search(d["register_scope"])]
    if unscoped:
        L.append(f"\n## register_scope 未落到 R1–R9 的 {len(unscoped)} 条（须补）\n")
        for d in unscoped[:20]:
            L.append(f"- `{d['term'][:20]}` — {d['register_scope']}（{d['_src']}）")
    if bad:
        L.append(f"\n## 退回 {len(bad)} 条\n")
        for d, why in bad:
            L.append(f"- `{d.get('_src','?')}:{d.get('_ln','?')}` {str(d.get('term',''))[:20]} — {why}")
    if conflicts:
        L.append(f"\n## 跨轴冲突 {len(conflicts)} 组（须人工裁决，合并器不自动定）\n")
        for ds in conflicts:
            L.append("### " + ds[0]["term"])
            for d in ds:
                L.append(f"- {d['level']}／{d['axis']}／{d['rule']}／{d['conf']} — "
                         f"{d['example'][:50]}（{d['source']}）")
            L.append("")
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def apply_overrides(rows):
    """应用人工裁决表。原始收料不动，只覆盖 axis/level/rule/conf。"""
    path = os.path.join(HERE, "overrides.tsv")
    if not os.path.exists(path):
        return 0
    ov = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#") or line.startswith("term\t"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) >= 5:
                ov[c[0].strip()] = c[1:5]
    n = 0
    for d in rows:
        o = ov.get(d["term"])
        if o:
            d["axis"], d["level"], d["rule"] = o[0], o[1], o[2]
            if o[3] in CONFS:
                d["conf"] = o[3]
            if "人工裁决" not in d["note"]:
                d["note"] = (d["note"] + "｜人工裁决").strip("｜")
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(RAW):
        sys.exit(f"没有 {RAW}，先收料。")
    rows, bad0, files = load_files()
    ok, bad = validate(rows)
    n_ov = apply_overrides(ok)
    rows2, conflicts = dedupe(ok)
    rows2 = order(rows2)
    if not a.check:
        write(rows2)
    report(rows2, bad0 + bad, conflicts, files)
    print(f"有效 {len(rows2)} 条｜退回 {len(bad0)+len(bad)}｜冲突 {len(conflicts)} 组｜人工裁决 {n_ov} 条")
    print(f"→ {OUT}\n→ {REPORT}")
    for lv in LEVELS:
        print(f"  {lv}: {sum(1 for d in rows2 if d['level']==lv)}")


if __name__ == "__main__":
    main()
