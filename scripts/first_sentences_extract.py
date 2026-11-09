# INPUT: 一个顶刊全文 md 目录（默认 ~/学术文献夹/语料库；可用 --corpus 指定），PDF 转出的文本，段落边界不可靠、页眉页脚混在正文里
# OUTPUT: 结果/节首句.tsv（每篇每节第一句）、结果/段首句.tsv（段落边界可靠的文件里每节各段第一句）、结果/引言前三句.tsv（引言起头三句，不依赖段落边界）、结果/引言首段各句.tsv（段落可靠文件的引言首段逐句，带句位与总句数）、结果/抽取统计.md
# POS: zh-econ-scaffold 工具层：给 references/first-sentences.md 那类统计做抽取，把"哪一节、第几段、第几句"切出来；归纳不在这里做。用法：python3 scripts/first_sentences_extract.py --corpus <目录> --out <输出目录>

import re, pathlib, statistics, collections, argparse
_ap = argparse.ArgumentParser(); _ap.add_argument("--corpus", default="~/学术文献夹/语料库"); _ap.add_argument("--out", default="./first_sentences_out"); _args = _ap.parse_args()

ROOT = pathlib.Path(_args.corpus).expanduser()
OUT  = pathlib.Path(_args.out).expanduser()
OUT.mkdir(parents=True, exist_ok=True)

TYPES = collections.OrderedDict([
    ("引言", r"引\s*言|导论|导言|前言|绪论|问题的?提出|研究背景|研究问题|研究动机"),
    ("文献", r"文献|研究综述|研究述评|相关研究|研究回顾|研究评述"),
    ("理论", r"理论|机制|机理|假设|假说|逻辑|框架|概念|分析范式|研究命题"),
    ("制度", r"制度背景|政策背景|改革背景|现实背景|背景|典型事实|特征事实|事实"),
    ("设计", r"研究设计|实证设计|经验设计|模型设定|模型构建|计量模型|实证模型|识别策略|实证策略|经验策略|研究方法|数据|变量|样本|估计方法|实证方法"),
    ("结果", r"实证结果|回归结果|基准|估计结果|实证分析|实证检验|经验结果|经验分析|检验结果|实证研究|主要结果|基本结果"),
    ("稳健", r"稳健|内生性"),
    ("拓展", r"进一步|拓展|异质性|扩展"),
    ("结论", r"结论|结语|总结|启示|政策建议|政策含义|政策意涵|评述|讨论"),
])
KEYWORDS = "|".join(TYPES.values())
CN = "[一二三四五六七八九十]{1,3}"
# 三种标题：一、引言 ／ 一引言（世界经济体例，须含节关键词）／ 1. 引言（须含节关键词）
HEAD_RE = re.compile(r"(?m)^(?:#{1,4}\s*)?(?:(" + CN + r")[、．.]\s*([^\n]{1,40})|(" + CN + r")((?:" + KEYWORDS + r")[^\n，,。；;：:]{0,22})|(\d)[、．.]?\s+((?:" + KEYWORDS + r")[^\n，,。；;：:]{0,22}))\s*$")
BARE = ["引言", "引  言", "引 言", "导言", "导论", "前言", "绪论", "结语", "结论", "总结", "文献综述", "理论分析", "研究设计", "结论与启示", "结论与政策建议", "结论与政策启示", "问题的提出", "问题提出", "研究背景"]
BARE_RE = re.compile(r"(?m)^(?:#{1,4}\s*)?(" + "|".join(sorted(map(re.escape, BARE), key=len, reverse=True)) + r")\s*$")
NOISE = re.compile(r"^[\*①-⑳]|^注[:：]|^资料来源|^数据来源|^表\s*\d|^图\s*\d|^续表|^Table|^Figure|邮箱|电子信箱|E-?mail|电子邮件|基金项目|文责自负|作者感谢|感谢匿名|通讯作者|责任编辑|DOI|中图分类号|JEL|文献标识码|文章编号|关键词|摘\s*要|Abstract|年第\s*\d+\s*期|https?://|www\.|^第\s*\d+\s*页")
SENT_END = re.compile(r"(?<=[。！？])")
SUBHEAD = re.compile(r"^[（(]" + CN + r"[）)]|^#+|^\d{1,2}[、．.]\s*[^\d]")

def clean(s):
    s = re.sub(r"[ \t　]+", "", s).replace("\n", "")
    s = re.sub(r"•\s*\d+\s*•", "", s)
    return s.strip("#").strip()

def cn_ratio(s):
    return len(re.findall(r"[一-鿿]", s)) / max(len(s), 1)

def sentences(block):
    out = []
    for s in SENT_END.split(block):
        s = s.strip()
        if not s or len(s) < 12 or len(s) > 220: continue
        if NOISE.search(s) or cn_ratio(s) < 0.6: continue
        out.append(s)
    return out

def classify(title, seen):
    for tname, pat in TYPES.items():
        if re.search(pat, title):
            if tname == "理论" and ({"设计", "结果"} & seen) and re.search(r"机制|机理|检验|分析", title) and not re.search(r"理论", title):
                return "机制检验"
            if tname == "制度" and ({"设计", "结果"} & seen):
                return "拓展"
            return tname
    return "其他"

def headings(text):
    found = []
    for m in HEAD_RE.finditer(text):
        title = (m.group(2) or m.group(4) or m.group(6) or "").strip()
        cut = re.search(r"[0-9，,。；;：:（(]", title)
        if cut and cut.start() >= 2: title = title[:cut.start()].strip()
        if len(title) < 2 or len(title) > 24: continue
        if m.group(1) is None and not re.search(KEYWORDS, title): continue
        found.append((m.start(), m.end(), title))
    for m in BARE_RE.finditer(text):
        found.append((m.start(), m.end(), m.group(1).replace(" ", "")))
    found.sort()
    dedup = []
    for h in found:
        if dedup and h[0] - dedup[-1][0] < 3: continue
        dedup.append(h)
    return dedup

def running_heads(blocks, stem):
    """页眉：文件里重复出现三次以上的短块，加上文件名里的题目与作者"""
    cnt = collections.Counter(b for b in blocks if 4 <= len(b) <= 60)
    heads = [b for b, n in cnt.items() if n >= 3]
    parts = [p for p in re.split(r"_", stem) if not re.fullmatch(r"[\dp\-—]+", p)]
    for p in parts:
        p = re.sub(r"[ \t]+", "", p)
        if len(p) >= 4:
            heads.append(p); heads.append(p.replace("：", ":")); heads.append(p.replace(":", "："))
    return sorted(set(heads), key=len, reverse=True)

AUTHOR_HEAD = re.compile(r"^[一-鿿、]{2,16}(等)?[:：](?=[一-鿿])")

def prepare_blocks(raw_blocks, heads):
    """去页眉、去小标题；不合并块，只标记哪一块的开头是干净的段首（前一块以句末标点收尾）"""
    out = []
    prev_closed = True
    for b in raw_blocks:
        for h in heads: b = b.replace(h, "")
        b = AUTHOR_HEAD.sub("", b).strip()
        if not b: continue
        if NOISE.search(b[:40]): continue
        if len(b) < 25 and not re.search(r"[。！？]", b): continue        # 小标题、残片，不改变上一块的收尾状态
        if SUBHEAD.match(b) and len(b) < 40: continue
        b = re.sub(r"^[（(]" + CN + r"[）)]", "", b)
        out.append((b, prev_closed))
        prev_closed = bool(re.search(r"[。！？”）)]$", b))
    return out

sec_rows, para_rows, intro_rows, first_para_rows = [], [], [], []
stat = collections.Counter(); files_ok = files_wrapped = 0

for f in sorted(ROOT.glob("**/*.md")):
    try: text = f.read_text(encoding="utf-8", errors="ignore")
    except Exception: continue
    journal = f.parts[len(ROOT.parts)].split("_")[0]
    hs = headings(text)
    if not hs: stat["无节标题"] += 1; continue
    ref = re.search(r"(?m)^(?:#+\s*)?参考文献", text)
    end_all = ref.start() if ref else len(text)
    all_raw = [clean(b) for b in re.split(r"\n\s*\n", text[:end_all])]
    heads = running_heads(all_raw, f.stem)
    body_lens = [len(b) for b in all_raw[1:] if b]
    wrapped = (statistics.median(body_lens) < 80) if body_lens else True
    files_wrapped += wrapped; files_ok += (not wrapped)
    seen = set(); sec_idx = 0
    for i, (s, e, title) in enumerate(hs):
        body_end = hs[i+1][0] if i + 1 < len(hs) else end_all
        if body_end <= e: continue
        raw = [clean(b) for b in re.split(r"\n\s*\n", text[e:body_end])]
        blocks = prepare_blocks(raw, heads)
        if not blocks: continue
        ttype = classify(title, seen)
        seen.add(ttype if ttype in TYPES else "拓展")
        sec_idx += 1; stat[ttype] += 1
        texts = [b for b, _ in blocks]
        ss = sentences("".join(texts))
        if ss:
            sec_rows.append((journal, f.stem, ttype, title, sec_idx, ss[0], sum(map(len, texts))))
            if ttype == "引言":
                for k, sent in enumerate(ss[:3], 1): intro_rows.append((journal, f.stem, k, sent))
        if wrapped: continue
        p_idx = 0
        for j, (b, clean_start) in enumerate(blocks):
            if len(b) < 60: continue
            bs = sentences(b)
            if not bs: continue
            p_idx += 1
            if not clean_start: continue                                   # 被页码切断的后半段，不算段首
            para_rows.append((journal, f.stem, ttype, title, sec_idx, p_idx, bs[0], len(b), len(bs)))
            if ttype == "引言" and j == 0 and re.search(r"[。！？”）)]$", b) and 2 <= len(bs) <= 20 and 120 <= len(b) <= 900:
                for k, sent in enumerate(bs, 1): first_para_rows.append((journal, f.stem, k, len(bs), sent))

def dump(name, header, rows):
    with (OUT / name).open("w", encoding="utf-8") as w:
        w.write("\t".join(header) + "\n")
        for r in rows: w.write("\t".join(str(x) for x in r) + "\n")
    print(name, len(rows), "行")

dump("节首句.tsv", ["期刊", "文件", "节类型", "节标题", "节序", "节首句", "节字数"], sec_rows)
dump("段首句.tsv", ["期刊", "文件", "节类型", "节标题", "节序", "段序", "段首句", "段字数", "段句数"], para_rows)
dump("引言前三句.tsv", ["期刊", "文件", "句序", "句"], intro_rows)
dump("引言首段各句.tsv", ["期刊", "文件", "句序", "段句数", "句"], first_para_rows)

with (OUT / "抽取统计.md").open("w", encoding="utf-8") as w:
    w.write("# 抽取统计\n\n")
    w.write(f"- 有节标题的文件 {files_ok + files_wrapped} 篇；段落边界可靠（段首句.tsv 与 引言首段各句.tsv 只用这些）{files_ok} 篇；每行成段、只用节首句 {files_wrapped} 篇；无节标题 {stat['无节标题']} 篇\n")
    w.write("- 各节类型的节数（含带关键词的小节）：" + "、".join(f"{k} {v}" for k, v in stat.most_common() if k != "无节标题") + "\n")
    by_type = collections.Counter(r[2] for r in para_rows)
    w.write("- 段首句按节类型：" + "、".join(f"{k} {v}" for k, v in by_type.most_common()) + "\n")
    w.write(f"- 引言前三句 {len(intro_rows)} 句；引言首段各句 {len(first_para_rows)} 句（{len({r[1] for r in first_para_rows})} 篇）\n")
    w.write("- 引言节按期刊：" + "、".join(f"{k} {v}" for k, v in collections.Counter(r[0] for r in sec_rows if r[2] == '引言').most_common()) + "\n")
print(open(OUT / "抽取统计.md", encoding="utf-8").read())
