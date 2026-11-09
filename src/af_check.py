#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改稿对账器：原稿 vs 改稿

用法:
  python3 af_check.py 原稿.md 改稿.md
  python3 af_check.py 原稿.md 改稿.md --min 0.65   # 允许缩字下限

查七项，全 PASS 才算没改坏：
  1. 数字         原稿的每个数字都应在改稿里（多重集）
  2. 新增实体     改稿新增的书名号／专名，须能解释来路（硬失败）
  3. 模态方向     可能/也许/或许 不能变确定；必须/应当 不能变软
  4. 术语一致     原稿的高频实词不应在改稿里换写法
  5. 节拍         句长标准差与段长极差，改后不能更小（防「越改越匀」）
  6. 篇幅         改稿字数／原稿字数，落在 [min, 1.25]
  7. 结构         标题数、代码块、列表项不应无故减少

为什么要有第 5 项：盲测里 AI 词汇从 70 降到 0，均匀节拍却从 60 升到 101，
格言收尾从 38 升到 61——减法式改写的天花板就在这里。
"""
import re, sys, os, argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from af_metrics import measure  # noqa: E402

MODAL_STRONG = ["必须", "应当", "应该", "一定", "必然", "确定", "已经", "将会", "不得"]
MODAL_WEAK = ["可能", "也许", "或许", "大概", "似乎", "往往", "通常", "或许", "或可"]
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
QUOTE_RE = re.compile(r"[《〈「『]([^》〉」』]{2,30})[》〉」』]")


def read(p):
    return open(p, encoding="utf-8", errors="ignore").read()


def nums(text):
    return Counter(NUM_RE.findall(text))


def quotes(text):
    return set(QUOTE_RE.findall(text))


def heads(text):
    return len(re.findall(r"(?m)^#{1,6}\s", text))


def fences(text):
    return text.count("```") // 2


def bullets(text):
    return len(re.findall(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", text))


def para_range(text):
    """段落长度极差（按汉字数）。

    段数少于 3 时返回 None：原文若用单换行分段（txt 常见），re.split(r"\\n\\s*\\n")
    会把整篇当成一段，极差变成「全文长度」——这是伪影，不能当节奏证据。
    """
    paras = [p for p in re.split(r"\n\s*\n", text) if re.search(r"[\u4e00-\u9fff]", p)]
    if len(paras) < 3:
        return None
    lens = [len(re.findall(r"[\u4e00-\u9fff]", p)) for p in paras]
    return max(lens) - min(lens)


def main():
    ap = argparse.ArgumentParser(description="ai-flavor 改稿对账")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--min", type=float, default=0.65, help="缩字下限（默认 0.65）")
    ap.add_argument("--max", type=float, default=1.25, help="增字上限（默认 1.25）")
    a = ap.parse_args()

    o, n = read(a.old), read(a.new)
    mo, mn = measure(a.old), measure(a.new)
    rows, fails = [], []

    def add(name, ok, detail):
        rows.append((name, "PASS" if ok else "FAIL", detail))
        if not ok:
            fails.append(name)

    no, nn = nums(o), nums(n)
    lost = {k: v for k, v in no.items() if nn.get(k, 0) < v}
    add("数字", not lost,
        "全部保留" if not lost else "丢失 " + "、".join(f"{k}×{v}" for k, v in list(lost.items())[:6]))

    qo, qn = quotes(o), quotes(n)
    newq = qn - qo
    add("新增实体", not newq,
        "无新增书名／专名" if not newq else "新增：" + "、".join(list(newq)[:6]) + "（须能说明来路，否则删）")

    so, sn = sum(o.count(w) for w in MODAL_STRONG), sum(n.count(w) for w in MODAL_STRONG)
    wo, wn = sum(o.count(w) for w in MODAL_WEAK), sum(n.count(w) for w in MODAL_WEAK)
    modal_ok = (sn >= so - 1) and (wn >= wo - 1)
    add("模态方向", modal_ok,
        f"确定词 {so}→{sn}｜或然词 {wo}→{wn}" + ("" if modal_ok else "（确定度被改动，最严重）"))

    words_o = [w for w in re.findall(r"[\u4e00-\u9fff]{3,6}", o)]
    freq = Counter(words_o).most_common(12)
    swapped = [w for w, c in freq if c >= 3 and w not in n]
    add("术语一致", not swapped,
        "核心词未改写法" if not swapped else "原稿高频词在改稿消失：" + "、".join(swapped[:6]))

    sd_o, sd_n = mo.get("slen_sd"), mn.get("slen_sd")
    pr_o, pr_n = para_range(o), para_range(n)
    tempo_ok = ((sd_n is None or sd_o is None or sd_n >= sd_o * 0.95)
                and (pr_o is None or pr_n is None or pr_n >= pr_o * 0.8))
    add("节拍", tempo_ok,
        f"句长标准差 {sd_o}→{sd_n}｜段长极差 "
        f"{'n/a' if pr_o is None else pr_o}→{'n/a' if pr_n is None else pr_n}"
        + ("" if tempo_ok else "（更匀了：减法式改写的典型症状，回退）"))

    co, cn = mo.get("chars") or 1, mn.get("chars") or 1
    ratio = cn / co
    add("篇幅", a.min <= ratio <= a.max, f"{co}→{cn} 字，比 {ratio:.2f}（允许 {a.min}–{a.max}）")

    st_ok = heads(n) >= heads(o) and fences(n) >= fences(o) and bullets(n) >= bullets(o)
    add("结构", st_ok,
        f"标题 {heads(o)}→{heads(n)}｜代码块 {fences(o)}→{fences(n)}｜列表 {bullets(o)}→{bullets(n)}")

    print(f"# 对账 {os.path.basename(a.old)} → {os.path.basename(a.new)}\n")
    print("| 项 | 结果 | 详情 |")
    print("|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} |")
    print(f"\n**{len(rows)-len(fails)}/{len(rows)} PASS**"
          + ("" if not fails else f"　未过：{'、'.join(fails)}"))
    if fails:
        print("\n> 未过项须逐条处理。改动前先存快照，术语与模态两项工具查不全，需人工过一遍。")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
