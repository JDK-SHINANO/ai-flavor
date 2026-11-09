#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文「AI 味」可计数指标探针 v0.2
用法: python3 quant_cn.py FILE [FILE...]
输出: 每文件一行 TSV, 便于直接落表。

依赖:
  - 推荐 jieba（分词准确，密度口径与 JCIP 基线一致）
  - 无 jieba 时自动降级为「最长匹配」分词：词典项仍准确成词，词数分母按
    平均词长 1.704 字/词估算（JCIP 采样值）。降级模式输出带 warn 列。

设计原则:
  1. 只算「正则 + 词典」能稳定复现的量。需句法分析器的指标（NP 长度、
     依存距离、句法树高）不在本脚本内。
  2. 表格行与 frontmatter 先剔除 —— 否则整行表格会被当成一个「句子」，
     实测把最大句长抬到 500 字、标准差抬到 100，全部指标失真。
  3. 词典在分词后的词表上做精确匹配，不做子串匹配（「现在」的「在」会被
     误计为介词，实测虚高 2–3 倍）。仅 4 字以上套话允许子串匹配。
"""
import re, sys, os, statistics as st

CJK = re.compile(r"[\u4e00-\u9fff]")

# ---- 词典（可核查；改词典即改基线，务必版本化）----
CONJ = ["以及", "并且", "而且", "然而", "但是", "因此", "所以", "由于", "因为",
        "如果", "虽然", "尽管", "即使", "只要", "无论", "不仅", "同时", "另外",
        "此外", "于是", "从而", "进而", "或者", "还是", "以便", "与其", "不如",
        "和", "与", "及", "而", "但", "故", "若"]
PREP = ["关于", "对于", "由于", "为了", "除了", "随着", "作为", "通过", "根据",
        "按照", "依照", "针对", "在", "从", "对", "把", "被", "为", "以", "于",
        "跟", "向", "给", "按", "据", "离", "往", "朝", "沿"]
PRON1 = ["我们", "我", "咱", "咱们"]
PRON2 = ["你们", "你", "您"]
PRON3 = ["他们", "她们", "它们", "他", "她", "它"]
INTERJ = ["哎呀", "唉呀", "唉", "哎", "哦", "噢", "嗯", "啊", "呀", "哈", "嘿", "哇"]
PARTICLE_END = ["罢了", "就是了", "而已", "着呢", "来着", "啊", "呢", "吧", "嘛",
                "呀", "啦", "咯", "呗", "哇", "嘞"]
META = ["值得注意的是", "需要指出的是", "必须指出的是", "不难发现", "可以看出",
        "总的来说", "综上所述", "总而言之", "换言之", "换句话说",
        "与此同时", "从某种意义上说", "从这个角度看"]
HEDGE = ["在一定程度上", "在某种程度上", "某种意义上", "一般来说", "通常", "往往",
         "可能", "也许", "或许", "大概", "似乎", "相关", "相对", "较为", "有所"]

SENT_END = "。！？!?…"
CLOSERS = "”’」』）)》〉】\"'"

AVG_WORD_LEN = 1.704  # JCIP 2024 采样值，仅降级模式用于估算词数


# ---------- 分词：jieba 优先，缺失则最长匹配降级 ----------
def load_jieba():
    try:
        import jieba
        return jieba
    except ImportError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "_vendor", "jieba"),
              "/tmp/jj/jieba-0.42.1",
              os.path.expanduser("~/.cache/jieba")):
        if os.path.isdir(p):
            sys.path.insert(0, p)
            try:
                import jieba
                return jieba
            except ImportError:
                sys.path.pop(0)
    return None


JIEBA = load_jieba()
_LEXSET = set(CONJ + PREP + PRON1 + PRON2 + PRON3 + INTERJ + PARTICLE_END + HEDGE)
_MAXLEN = max(len(w) for w in _LEXSET)


def greedy_cut(text):
    """最长匹配：词典项整体成词，其余按字/字母数字切。零依赖降级用。"""
    out, i, n = [], 0, len(text)
    while i < n:
        hit = None
        for L in range(min(_MAXLEN, n - i), 1, -1):
            seg = text[i:i + L]
            if seg in _LEXSET:
                hit = seg
                break
        if hit:
            out.append(hit)
            i += len(hit)
        else:
            ch = text[i]
            if CJK.match(ch) or ch.isalnum():
                out.append(ch)
            i += 1
    return out


# ---------- 预处理 ----------
def clean(raw):
    """剔除 frontmatter、表格行、代码块、图片、markdown 符号。

    表格行必须删：整行文字会被句子切分器当成一句，句长与标准差全部失真。
    删掉的是「排版噪声」，正文段落不受影响。
    """
    text = re.sub(r"\A---\n.*?\n---\n", "", raw, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", "", text, flags=re.S)           # 代码块
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)            # 图片
    text = re.sub(r"(?m)^\s*\|.*$", "", text)                   # 表格行
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)           # 标题标记
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)                # 无序列表符号
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)              # 有序列表符号
    text = re.sub(r"[*_`>~]", "", text)                          # 行内符号
    return text


def sentences(text):
    text = re.sub(r"\s+", "", text)
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in SENT_END:
            out.append(buf)
            buf = ""
    if buf.strip(CLOSERS):
        out.append(buf)
    return [s for s in out if CJK.search(s)]


def mtld(tokens, thresh=0.72):
    """MTLD (McCarthy & Jarvis 2010)，双向平均。token < 10 返回 nan。"""
    def one_seq(seq):
        factors, types, n = 0.0, set(), 0
        for t in seq:
            n += 1
            types.add(t)
            if len(types) / n <= thresh:
                factors += 1
                types, n = set(), 0
        if n > 0:
            factors += (1 - len(types) / n) / (1 - thresh)
        return len(seq) / factors if factors else float("nan")
    if len(tokens) < 10:
        return float("nan")
    return (one_seq(tokens) + one_seq(list(reversed(tokens)))) / 2


def ttr(tokens):
    return len(set(tokens)) / len(tokens) if tokens else float("nan")


def measure(path):
    raw = open(path, encoding="utf-8", errors="ignore").read()
    text = clean(raw)
    nchar = len(CJK.findall(text))
    sents = sentences(text)
    slen = [len(CJK.findall(s)) for s in sents]
    slen = [x for x in slen if x > 0]

    payload = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", " ", text)
    if JIEBA:
        words = [w for w in JIEBA.lcut(payload) if w.strip()]
        W = len(words) or 1
        warn = ""
    else:
        words = greedy_cut(payload)
        W = max(1, round(nchar / AVG_WORD_LEN))
        warn = "no-jieba:W-est"
    joined = "".join(words)

    def dens(lex):
        c = sum(1 for w in words if w in lex)
        return 1000 * c / W if W else float("nan")

    end_particles = sum(1 for s in sents
                        if any(s.rstrip(CLOSERS).endswith(p) for p in PARTICLE_END))

    r = {
        "file": os.path.basename(path),
        "chars": nchar,
        "words": W,
        "sents": len(slen),
        "slen_mean": round(st.mean(slen), 2) if slen else float("nan"),
        "slen_sd": round(st.pstdev(slen), 2) if slen else float("nan"),
        "slen_cv": round(st.pstdev(slen) / st.mean(slen), 3) if slen else float("nan"),
        "slen_max": max(slen) if slen else float("nan"),
        "conj_p1k": round(dens(CONJ), 2),
        "prep_p1k": round(dens(PREP), 2),
        "pron1_p1k": round(dens(PRON1), 2),
        "pron_all_p1k": round(dens(PRON1 + PRON2 + PRON3), 2),
        "interj_p1k": round(dens(INTERJ), 2),
        "particle_end_pct": round(100 * end_particles / len(sents), 1) if sents else float("nan"),
        "ttr_w": round(ttr(words), 3),
        "mtld_w": round(mtld(words), 1),
        "ttr_c": round(ttr(list(CJK.findall(text))), 3),
        "mtld_c": round(mtld(list(CJK.findall(text))), 1),
        "meta_p10k": round(10000 * sum(joined.count(t) for t in META) / nchar, 1) if nchar else float("nan"),
        "hedge_p1k": round(dens(HEDGE), 2),
        "dash_p1k": round(1000 * text.count("——") / nchar, 2) if nchar else float("nan"),
        "semi_p1k": round(1000 * text.count("；") / nchar, 2) if nchar else float("nan"),
        "colon_p1k": round(1000 * text.count("：") / nchar, 2) if nchar else float("nan"),
        "dun_p1k": round(1000 * text.count("、") / nchar, 2) if nchar else float("nan"),
        "warn": warn,
    }
    return r


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python3 af_metrics.py FILE [FILE...]")
    rows = [measure(p) for p in sys.argv[1:]]
    keys = list(rows[0].keys())
    print("\t".join(keys))
    for r in rows:
        print("\t".join(str(r[k]) for k in keys))
    if not JIEBA:
        print("# 未找到 jieba，已降级：词典计数准确，词数分母为估算值。"
              "装 jieba 后口径与 JCIP 基线一致。", file=sys.stderr)


if __name__ == "__main__":
    main()
