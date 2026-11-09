#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从各档报告里抽出「改后全文」，另存 .body.md，供 metrics/scan 复算。

用法: python3 extract_body.py L1.md L4.md
"""
import re, sys, os


def extract(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"(?m)^##\s*[一二三四五]、?\s*改后全文\s*$", txt)
    if not m:
        return None
    rest = txt[m.end():]
    n = re.search(r"(?m)^##\s", rest)
    return (rest[:n.start()] if n else rest).strip()


def main():
    for p in sys.argv[1:]:
        body = extract(p)
        if not body:
            print(f"SKIP {p}（找不到「改后全文」节）")
            continue
        out = os.path.splitext(p)[0] + ".body.md"
        open(out, "w", encoding="utf-8").write(body + "\n")
        print(f"{p} → {out}  {len(re.findall(r'[一-鿿]', body))} 汉字")


if __name__ == "__main__":
    main()
