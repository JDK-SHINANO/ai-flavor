#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai-flavor 三轴扫描器 v0.1

用法:
  python3 scan.py FILE [FILE...]                     单篇/多篇扫描
  python3 scan.py --baseline a.md b.md -- FILE       用 a/b 作同文体对照基线
  python3 scan.py --json FILE                        机器可读输出

设计原则（三条，写在前面，免得后来者改坏）:
  1. **脚本只举证，不定案。** 每条命中给行号、片段、规则、置信度；是否算病由人判。
  2. **白名单前置。** 命中后先过白名单，命中白名单标 WL 并排除出计数。
  3. **被引用的规则不算犯规则。** 讲规则的段落（「不要写『不是 A 而是 B』」）
     本身会出现这些句式。检测到「规则讲述标记」的行，标 QUOTE 降权。

三轴对应 SKILL.md 的三病:
  甲 J  形合硬搬（纠偏）
  乙 Y  语域塌缩（定域）
  丙 B  结构可预测（破均）
"""
import re, sys, os, json, argparse, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from af_metrics import CJK, CONJ, PARTICLE_END, META, HEDGE, JIEBA, greedy_cut  # noqa: E402

# ============ 词表（可核查；改词表即改判据，须版本化） ============

PSEUDO_TERMS = ["知名度", "可读性", "前瞻性", "可操作性", "获得感", "颗粒度",
                "底层逻辑", "闭环", "抓手", "维度的", "多维度", "深度赋能",
                "赋能的", "生态位", "链路", "矩阵式", "组合拳", "护城河"]
BANNED_RAISE = ["标志着", "彰显了", "充分体现", "注入新的活力", "注入新动能",
                "具有里程碑意义", "开启新篇章", "迈上新台阶", "书写新篇章",
                "提供了有力支撑", "奠定了坚实基础", "产生了深远影响",
                "具有重要的现实意义", "价值转化"]
FALSE_CONTRAST = [r"(不是|并非|不只是|不仅)[^。！？]{1,28}(而是|更是)",
                  r"(不单|岂止)[^。！？]{1,24}更是"]
ORDINAL_FOUR = r"首先[^。]{0,80}其次[^。]{0,80}(再次|最后)"
COLLOCATION = ["进行", "作出", "加以", "予以", "给予", "取得"]
COLLOCATION_WL = ["作出决定", "作出判决", "作出裁定", "予以驳回", "予以处罚",
                  "依法予以", "进行曲", "加以说明", "取得进展", "取得突破"]
PASSIVE_WL = ["被评为", "被列入", "被依法", "被称为", "被授予", "被告知", "被视为",
              "被称作", "被采用", "被采纳"]
NONHUMAN_MEN = ["民众", "听众", "观众", "制度", "公司", "学校", "部门", "团队",
                "玩家", "用户", "粉丝", "群众"]
QUOTE_MARKERS = ["不要写", "不要用", "避免", "禁止", "反面", "正例", "反例", "判据",
                 "例如", "如：", "忌用", "病句", "改写前", "改写后", "×", "✗"]

# ============ 行级预处理 ============

def load_lines(path):
    """返回 [(行号, 清洗后正文)]，剔除 frontmatter、表格行、代码块。"""
    raw = open(path, encoding="utf-8", errors="ignore").read()
    raw = re.sub(r"\A---\n.*?\n---\n", "", raw, flags=re.S)
    out, in_fence = [], False
    for i, ln in enumerate(raw.split("\n"), 1):
        s = ln.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or s.startswith("|"):
            continue
        out.append((i, ln))
    return out


def strip_md(s):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", s)
    s = re.sub(r"(?m)^\s*[-*+]\s+", "", s)
    s = re.sub(r"(?m)^\s*\d+[.)]\s+", "", s)
    s = re.sub(r"[*_`>~]", "", s)
    return s


# ============ 规则 ============
# (id, axis, 名称, 正则, 白名单正则|None, 置信度, 建议)
RULES = [
    # ---- 甲 形合硬搬 ----
    ("J1", "甲", "万能动词＋名词", r"(进行|作出|加以|予以|给予|取得)(了|一次|一个|进一步)?(的)?[\u4e00-\u9fff]{1,4}(?=[，。；、！？\s]|的)",
     None, "mid", "动词被架空：还原为谓语（进行调整→调整）"),
    ("J2", "甲", "句式杂糅", r"(由于[^，。]{2,24}，\s*使得|通过[^，。]{2,24}，\s*使|根据[^。]{0,12}显示|本着以[^，。]{0,12}为|是由于[^。]{0,24}的结果)",
     None, "high", "两套骨架硬拼：留一套（由于…使得→…，因此）"),
    ("J3", "甲", "被动句", r"被[\u4e00-\u9fff]{1,4}(?=[，。；、！？的\s])", None, "low", "施事测试：已知且重要却隐去才改"),
    ("J4", "甲", "「们」附着非人", r"(民众|听众|观众|制度|公司|学校|部门|团队|玩家|用户|粉丝|群众)们", None, "high", "伪复数：去「们」或用「众／全体」"),
    ("J5", "甲", "条件从句后置", r"[，,]\s*(如果|当|若|假如)[^。！？]{2,40}[。！？]?\s*$", None, "mid", "条件前置：汉语先说条件再说结果"),
    ("J6", "甲", "长定语链", r"的[^，。；：、！？]{2,24}的[^，。；：、！？]{2,24}的", None, "mid", "拆成后置短句（名词后补语）"),
    ("J7", "甲", "时体冗余", r"(已经|曾经)[^，。]{0,12}了(?=[，。；])", None, "low", "无时间副词时不必强加「了／已经」"),
    ("J8", "甲", "「作为一个」", r"作为一个[^，。]{2,20}[，,]", None, "mid", "话题框架冗余，常与「我认为」叠加"),
    # ---- 乙 语域塌缩 ----
    ("Y1", "乙", "伪术语", r"(知名度|可读性|前瞻性|可操作性|获得感|颗粒度|底层逻辑|闭环|抓手|生态位|护城河|组合拳)", None, "high",
     "无新增信息，只抬语域：换成具体说法或删"),
    ("Y2", "乙", "抽象名词作主语", r"的(减少|增加|提高|下降|改善|变化|增长|降低|调整)(改变|导致|使得|引起|带来|影响|成为)", None, "high",
     "施事被降为定语：还原成短句"),
    ("Y3", "乙", "介词框架", r"(当[^，。]{2,20}的时候|在[^，。]{2,20}的情况下)", None, "high", "缩为「……时」「……下」"),
    ("Y4", "乙", "「具有…性／度」壳", r"具有(很高|较高|一定|很强|很强|显著)?的?[\u4e00-\u9fff]{1,6}(性|度)", None, "mid",
     "壳测试：去掉壳后形容词能否直接作谓语"),
    ("Y5", "乙", "「之一」无限定", r"之一(?=[，。；、！？]|$)", r"(七贤|八大家|四书|五经|之一，|三甲)", "low",
     "集合不明确时削弱断言"),
    ("Y6", "乙", "「随着…发展」开头", r"^随着[^，。]{2,30}的(发展|推进|普及|深入)", None, "mid", "背景无独立信息即压缩"),
    # ---- 丙 结构可预测 ----
    ("B1", "丙", "元话语", r"(值得注意的是|需要指出的是|必须指出的是|不难发现|可以看出|总的来说|综上所述|总而言之|换言之|换句话说|与此同时|从某种意义上说)",
     None, "high", "删预告与免责，直接说事"),
    ("B2", "丙", "逻辑标记四级", ORDINAL_FOUR, None, "high", "四级堆叠：合并或删，读者能猜下一段"),
    ("B3", "丙", "假对比", "|".join(FALSE_CONTRAST), None, "mid", "直接说后半句，否定只用于纠正真实误解"),
    ("B4", "丙", "意义拔高", "|".join(map(re.escape, BANNED_RAISE)), None, "high", "删掉价值判断，只留具体事实"),
    ("B5", "丙", "破折号连环", r"——[^—]{1,40}——", None, "low", "GB/T 15834 允许插入语，无频次限制；此条仅为风格建议"),
    ("B6", "丙", "加粗当小标题", r"\*\*[^*\n]{1,24}\*\*\s*[:：]", None, "mid", "写成句子；只留术语首现与界面元素"),
]

# 内置规则的语言学层级：按「问题主要发生在哪一层」归一层，只归一层。
# 判据见 assets/lexicon/FORMAT.md 第二节。
LEVEL_MAP = {
    "J1": "句法", "J2": "句法", "J3": "句法", "J4": "词法", "J5": "句法",
    "J6": "句法", "J7": "句法", "J8": "语用",
    "Y1": "词法", "Y2": "词法", "Y3": "句法", "Y4": "词法", "Y5": "词法", "Y6": "篇章",
    "B1": "篇章", "B2": "篇章", "B3": "修辞", "B4": "修辞", "B5": "修辞", "B6": "修辞",
}

# ============ 篇级规则 ============
# 结构性的病不在句内，在段与段之间。逐行扫必漏，故单列。
# (id, 轴, 层, 名, 正则, 置信, 建议) —— 在全文（去换行）上跑一次
PROSE_RULES = [
    ("P1", "丙", "篇章", "逻辑标记四级",
     r"(?s)首先.{0,600}?其次.{0,600}?(再次|最后)", "high",
     "四级堆叠跨段成立：读者能预判下一段的形状，合并或删"),
    ("P2", "乙", "篇章", "时代背景开头",
     r"(^|。)(在当今|在当前|在这个|如今|随着)[^。！？]{0,26}(时代|今天|背景下|大环境下|浪潮中)", "mid",
     "背景句若无独立信息，压缩或删"),
    ("P3", "丙", "篇章", "论文体元话语",
     r"(本文将从|本文将|本文旨在|本文认为|下面我们|接下来我们|让我们)", "high",
     "删预告，直接说事"),
]
PROSE_COMPILED = [(rid, ax, lv, name, re.compile(pat), conf, adv)
                  for rid, ax, lv, name, pat, conf, adv in PROSE_RULES]

COMPILED = [(rid, ax, LEVEL_MAP.get(rid, "句法"), name,
             re.compile(pat), re.compile(wl) if wl else None, conf, adv, "")
            for rid, ax, name, pat, wl, conf, adv in RULES]

# ============ 外置词库 ============
# 词库与代码分离：词条由 merge_lexicon.py 从 raw/*.tsv 合并而来。
# 词库缺失时退回内置规则，不影响可用性。
LEXICON = os.path.normpath(os.path.join(HERE, "..", "assets", "lexicon", "lexicon.tsv"))


def load_lexicon(path=LEXICON, lang=None):
    """读合并词库（10 列），返回 (id, 轴, 层, 名, 正则, 白名单, 置信, 建议, 域) 元组表。

    lang: "zh" 只取中文字条，"en" 只取英文字条，None 全取。
    判据：term 里含汉字即中文条。英文 em dash 之类不能拿来扫中文文本，
    否则中文破折号会被当成英文 em dash 滥用，实测能造出几十条假警报。
    """
    extra = []
    if not os.path.exists(path):
        return extra
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip() or line.startswith("term\t"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 10:
                continue
            term, typ, lv, ax, rule, conf, scope, _ex, _src, note = c[:10]
            if ax not in ("甲", "乙", "丙") or conf not in ("high", "mid", "low"):
                continue
            if lv not in ("词法", "句法", "篇章", "语用", "修辞"):
                continue
            item_lang = "zh" if CJK.search(term) else "en"
            if lang and item_lang != lang:
                continue
            pat = re.escape(term) if typ.strip() == "word" else term
            try:
                rgx = re.compile(pat)
            except re.error:
                continue
            advice = note.strip() or "词库命中，回上下文判断"
            extra.append((f"L·{rule.strip()}", ax, lv, term.strip()[:14], rgx, None,
                          conf, advice, scope.strip()))
    return extra


def is_zh_text(text):
    """中文占比过半即按中文处理。"""
    cjk = len(CJK.findall(text))
    lat = len(re.findall(r"[A-Za-z]", text))
    return cjk >= max(1, lat)


TABLE_ZH = COMPILED + load_lexicon(lang="zh")   # 内置规则是中文的
TABLE_EN = load_lexicon(lang="en")              # 英文侧暂无内置规则


# ============ 篇级指标 ============

def profile(lines):
    body = "\n".join(strip_md(t) for _, t in lines)
    nchar = len(CJK.findall(body))
    sents = [s for s in re.split(r"[。！？!?…]+", re.sub(r"\s+", "", body)) if CJK.search(s)]
    slen = [len(CJK.findall(s)) for s in sents]
    paras = [p for p in re.split(r"\n\s*\n", body) if CJK.search(p)]
    plen = [len(CJK.findall(p)) for p in paras]

    payload = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", " ", body)
    if JIEBA:
        words = [w for w in JIEBA.lcut(payload) if w.strip()]
        W = len(words) or 1
    else:
        words = greedy_cut(payload)
        W = max(1, round(nchar / 1.704))
    joined = "".join(words)

    def dens(lex):
        return round(1000 * sum(1 for w in words if w in lex) / W, 2) if W else None

    particles = sum(1 for s in sents if any(s.rstrip("”’」』）)》】") .endswith(p) for p in PARTICLE_END))
    return {
        "chars": nchar, "words": W, "sents": len(sents),
        "slen_mean": round(st.mean(slen), 2) if slen else None,
        "slen_sd": round(st.pstdev(slen), 2) if slen else None,
        "slen_cv": round(st.pstdev(slen) / st.mean(slen), 3) if slen and st.mean(slen) else None,
        "paras": len(plen),
        "para_range": (max(plen) - min(plen)) if plen else None,
        "conj_p1k": dens(CONJ),
        "meta_p10k": round(10000 * sum(joined.count(t) for t in META) / nchar, 1) if nchar else None,
        "hedge_p1k": dens(HEDGE),
        "particle_n": particles,
        "particle_pct": round(100 * particles / len(sents), 1) if sents else None,
        "dash_n": body.count("——"), "bold_n": len(re.findall(r"\*\*[^*\n]+\*\*", body)),
        "bullets": sum(1 for _, t in lines if re.match(r"^\s*([-*+]|\d+[.)])\s+", t.strip())),
    }


# ============ 命中检测 ============

def is_quote(line):
    return any(m in line for m in QUOTE_MARKERS)


CONF_RANK = {"high": 0, "mid": 1, "low": 2}


def scan(path, baseline=None, axis=None, level=None, min_conf=None, register=None):
    """扫描单篇。

    axis/level/min_conf：按属性过滤（甲乙丙／词法句法篇章语用修辞／置信度下限）。
    register：目标文体 R1–R9。词条 register_scope 里标「该档正常」的，降为 low 线索。
    """
    lines = load_lines(path)
    prof = profile(lines)
    raw_text = "\n".join(t for _, t in lines)
    table = TABLE_ZH if is_zh_text(raw_text) else TABLE_EN
    hits = []
    for ln, text in lines:
        clean = strip_md(text)
        if not CJK.search(clean):
            continue
        quoted = is_quote(text)
        for rid, ax, lv, name, rgx, wlr, conf, adv, scope in table:
            if axis and ax != axis:
                continue
            if level and lv != level:
                continue
            if min_conf and CONF_RANK[conf] > CONF_RANK[min_conf]:
                continue
            if scope and (f"{register}正常" in scope or "全档可用" in scope):
                pass  # 该档合法，降级在下面统一处理
            for m in rgx.finditer(clean):
                frag = m.group(0)
                status = "WL" if (wlr and wlr.search(frag)) else ("QUOTE" if quoted else "HIT")
                c = conf
                if scope and (f"{register}正常" in scope or "全档可用" in scope):
                    c = "low"
                hits.append(dict(line=ln, axis=ax, level=lv, rule=rid, name=name,
                                 frag=frag, status=status, conf=c, advice=adv, scope=scope))
    # 篇级规则：在全文（去换行）上跑，专抓跨段结构
    flat = re.sub(r"\s+", "", raw_text)
    for rid, ax, lv, name, rgx, conf, adv in PROSE_COMPILED:
        if axis and ax != axis:
            continue
        if level and lv != level:
            continue
        if min_conf and CONF_RANK[conf] > CONF_RANK[min_conf]:
            continue
        for m in rgx.finditer(flat):
            hits.append(dict(line=0, axis=ax, level=lv, rule=rid, name=name,
                             frag=m.group(0)[:60], status="HIT", conf=conf,
                             advice=adv, scope=""))

    # 同处去重：同一行、同轴、同片段只留一条。
    # 优先级：有文体域的词库条 > 无域的内置兜底条；同域时取置信度高者。
    best = {}
    for h in hits:
        k = (h["line"], h["axis"], h["frag"].lower())
        cur = best.get(k)
        if cur is None:
            best[k] = h
        elif h.get("scope") and not cur.get("scope"):
            best[k] = h
        elif bool(h.get("scope")) == bool(cur.get("scope")) \
                and CONF_RANK[h["conf"]] < CONF_RANK[cur["conf"]]:
            best[k] = h
    hits = sorted(best.values(), key=lambda h: (h["line"], h["axis"]))

    # 篇级判读
    flags = []
    if prof["slen_sd"] is not None and prof["sents"] >= 10 and prof["slen_sd"] < 10:
        flags.append(("丙", "句长标准差偏窄", f"{prof['slen_sd']} 字（人类常见 12–18）", "节拍被排匀"))
    if prof["conj_p1k"] is not None and prof["words"] >= 300 and prof["conj_p1k"] > 25:
        flags.append(("甲", "连词密度偏高", f"{prof['conj_p1k']}/千词（人类基线 13，AI 36）", "形合硬搬"))
    if prof["particle_n"] == 0 and prof["sents"] >= 20:
        flags.append(("乙", "句末语气词为零", f"0 / {prof['sents']} 句",
                      "语域塌缩——但 R1–R4 本应为零，只有 R5–R8 才算警报"))
    if prof["meta_p10k"] is not None and prof["meta_p10k"] > 15:
        flags.append(("丙", "元话语密度高", f"{prof['meta_p10k']}/万字符", "结构可预测"))

    if baseline:
        bps = [profile(load_lines(p)) for p in baseline]
        for key in ("slen_sd", "conj_p1k", "meta_p10k", "particle_pct"):
            vals = [b[key] for b in bps if b.get(key) is not None]
            cur = prof.get(key)
            if len(vals) >= 2 and cur is not None:
                mu = st.mean(vals)
                sd = st.pstdev(vals) or 0.0
                z = round((cur - mu) / sd, 2) if sd else None
                prof[f"base_{key}"] = round(mu, 2)
                prof[f"z_{key}"] = z

    counts = {ax: {"high": 0, "mid": 0, "low": 0} for ax in ("甲", "乙", "丙")}
    for h in hits:
        if h["status"] == "HIT":
            counts[h["axis"]][h["conf"]] += 1
    return dict(file=os.path.basename(path), profile=prof, flags=flags,
                hits=hits, counts=counts)


# ============ 输出 ============

def render_md(res):
    p, out = res["profile"], []
    out.append(f"# {res['file']}\n")
    out.append("## 画像\n")
    out.append("| 指标 | 值 |")
    out.append("|---|---|")
    for k, label in (("chars", "字数"), ("words", "词数"), ("sents", "句数"),
                     ("slen_mean", "句长均值（字）"), ("slen_sd", "句长标准差"),
                     ("slen_cv", "变异系数"), ("paras", "段数"), ("para_range", "段长极差"),
                     ("conj_p1k", "连词/千词"), ("meta_p10k", "元话语/万字符"),
                     ("hedge_p1k", "hedge/千词"), ("particle_n", "句末语气词"),
                     ("particle_pct", "语气词句占比%"), ("dash_n", "破折号"),
                     ("bold_n", "加粗"), ("bullets", "列表项")):
        if p.get(k) is not None:
            out.append(f"| {label} | {p[k]} |")
    for k in list(p):
        if k.startswith("base_"):
            z = p.get("z_" + k[5:])
            out.append(f"| 基线 {k[5:]} | {p[k]}（z={z}） |")
    if res["flags"]:
        out.append("\n## 篇级判读\n")
        out.append("| 轴 | 迹象 | 依据 | 含义 |")
        out.append("|---|---|---|---|")
        for ax, name, ev, mean in res["flags"]:
            out.append(f"| {ax} | {name} | {ev} | {mean} |")
    live = [h for h in res["hits"] if h["status"] == "HIT"]
    if live:
        out.append(f"\n## 命中 {len(live)} 条（已排除白名单与引用）\n")
        out.append("| 行 | 层 | 轴 | 规则 | 片段 | 置信 | 建议 |")
        out.append("|---|---|---|---|---|---|---|")
        for h in live:
            frag = h["frag"].replace("|", "\\|")[:40]
            ln = "篇" if h["line"] == 0 else h["line"]
            out.append(f"| {ln} | {h.get('level','')} | {h['axis']} | {h['rule']} {h['name']} | {frag} | {h['conf']} | {h['advice']} |")
    wl = [h for h in res["hits"] if h["status"] == "WL"]
    qt = [h for h in res["hits"] if h["status"] == "QUOTE"]
    if wl:
        out.append(f"\n**白名单放行 {len(wl)} 条**（不作病灶计）：" +
                   "、".join(sorted({h["rule"] + " " + h["frag"] for h in wl})[:8]))
    if qt:
        out.append(f"\n**引用标记降权 {len(qt)} 条**（讲规则的段落，不算犯规则）")
    c = res["counts"]
    out.append("\n## 汇总\n")
    out.append("| 轴 | high | mid | low | 合计 |")
    out.append("|---|---|---|---|---|")
    for ax in ("甲", "乙", "丙"):
        r = c[ax]
        out.append(f"| {ax} | {r['high']} | {r['mid']} | {r['low']} | {sum(r.values())} |")
    out.append("\n**置信度怎么用**：high 可直接采信；mid 须回上下文；low 只作线索，"
               "不得作为判病依据（被动、破折号、加粗多数是合法的）。")
    out.append("**条目数不等于严重度**：同段多条只算一处，密度比条数更能说明问题。\n")
    out.append("> 脚本只举证，不定案。白名单与引用已排除。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="ai-flavor 三轴×三层扫描器")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--baseline", nargs="+", default=None, help="同文体对照样本")
    ap.add_argument("--axis", choices=["甲", "乙", "丙"], help="只跑该轴")
    ap.add_argument("--level", choices=["词法", "句法", "篇章", "语用", "修辞"], help="只跑该层")
    ap.add_argument("--min-conf", choices=["high", "mid", "low"], help="置信度下限")
    ap.add_argument("--register", choices=[f"R{i}" for i in range(1, 10)],
                    help="目标文体；词条在该档合法者降为线索")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    files = a.files
    if "--" in files:
        i = files.index("--")
        a.baseline, files = files[:i], files[i + 1:]
    results = [scan(f, a.baseline, a.axis, a.level, a.min_conf, a.register) for f in files]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("\n\n---\n\n".join(render_md(r) for r in results))


if __name__ == "__main__":
    main()
