# -*- coding: utf-8 -*-
# INPUT: --run RUN_DIR（输出_*.md、输出_*_meta.json、输入包_meta.json、盲标顺序.json、盲标结果<后缀>.json 或 盲标结果<后缀>_<n>.json、盲标_meta<后缀>.json）；--suffix 与 judge.py 相同；用例 材料.md；技能 scripts/lint.py、quote_check.py、phrase_freq.py
# OUTPUT: RUN_DIR/分数表<后缀>.md 与 RUN_DIR/分数<后缀>.json（每个输出的机械指标、盲标指标、13 项检查与总分，标明裁判）；追加或覆盖 <工作目录>/历史.tsv 的对应行（run_id 带后缀）
# POS: 回归测试第 4 步：机械校加盲标，出分数表并记历史
import argparse, collections, csv, datetime, json, pathlib, re, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import (SCRIPTS, read, write, body, sents, outputs, load_meta, case_dir, run_root, output_tokens)

# ---- 词接断点：照 句子结构统计 F 路脚本的 link() 复制，只报不判 ----
STOP = set("的了是在和与对及其而并也就都把被为以于之从由等着过将这那此该或即所则不有一个中上下来去到说要会能可以及")
CONN = re.compile(r"^(然而|因此|此外|同时|与此同时|其次|首先|最后|一方面|另一方面|事实上|在此背景下|然后|进而|由此|但是|但|而|并且|因而|所以|换言之|具体而言|可见|总之)[，,]?")
ANAPHORA = re.compile(r"^(这|该|其|此|上述|前述|以上|二者|两者|三者|它|它们|他们|后者|前者|同一|这一|这些|这种|这类|这就|由此)")
GENERIC = {"中国", "我国", "企业", "经济", "发展", "社会", "政策", "研究", "问题", "影响", "重要", "国家", "地区", "政府", "市场", "产业", "劳动", "就业"}


def grams(s, n=2):
    s = re.sub(r"[^一-鿿]", " ", s)
    out = set()
    for w in s.split():
        for i in range(len(w) - n + 1):
            g = w[i:i + n]
            if not (set(g) & STOP):
                out.add(g)
    return out


def head(s):
    s = CONN.sub("", s.strip())
    return re.split(r"[，；：,;:]", s, maxsplit=1)[0], s


def link(prev, cur):
    """返回承接类型：回指 / 词接首分句 / 词接句内 / 无"""
    h, full = head(cur)
    if ANAPHORA.match(h):
        return "回指"
    g1 = grams(prev) | grams(prev, 3)
    g1 = {g for g in g1 if g not in GENERIC}
    if grams(h) & g1 or grams(h, 3) & g1:
        return "词接首分句"
    if grams(full) & g1 or grams(full, 3) & g1:
        return "词接句内"
    return "无"


# ---- 机械指标 ----
CHECKS = ["lint 问题数 = 0", "引文全部命中", "字数 300–400 且 句数 5–7", "\"本文\" = 0", "法条 = 0",
          "文件全名 ≤ 2、引号原话 ≤ 2、含数字句 ≤ 1", "含分号句 = 0", "换话题并列 ≤ 1", "第 2 句不并列",
          "伪翻转 = 0", "推进率 ≥ 2/3", "末句收束", "塞句 = 0"]
PUSH = ["缩小", "举证", "原因", "推论", "翻转"]


def tool(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def mechanical(p, material):
    ss = sents(p)
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "正文.md"
        write(f, "> " + p + "\n")
        _, out, err = tool([str(SCRIPTS / "lint.py"), str(f), "--json"])
        lj = json.loads(out)
        r0 = lj["段落"][0]
        _, qout, qerr = tool([str(SCRIPTS / "quote_check.py"), str(f), "--source", str(material)])
    m = re.search(r"共 (\d+) 条引文，(\d+) 条未命中", qout)
    nq, miss = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if not m and "没有引号内文字" not in qout:
        print("quote_check 输出无法解析：" + (qout + qerr)[:200])
        miss = None
    rare0 = None
    if ss:
        code, pout, perr = tool([str(SCRIPTS / "phrase_freq.py"), ss[0], "--json"])
        try:
            pj = json.loads(pout)
            rare0 = sum(1 for x in pj["结果"][0]["少见片段"] if x["长度"] >= 3 and x["篇数"] == 0)
        except (ValueError, KeyError, IndexError):
            print("phrase_freq 不可用：" + (pout + perr).strip()[:200])
    mat = r0.get("首段材料", {})
    return {"lint问题": lj["问题总数"], "lint提示": lj["提示总数"], "lint问题明细": r0["问题"],
            "文件全名": mat.get("文件全名", 0), "引号原话": mat.get("引号原话", 0), "含数字句": mat.get("含数字句", 0),
            "法条": mat.get("法条", 0), "然而": r0["然而"], "句首衔接词": r0["句首衔接词"],
            "字数": r0["字数"], "句数": r0["句数"], "引文数": nq, "引文未命中": miss,
            "首句零篇三字以上片段": rare0, "本文": p.count("本文"),
            "分号句": sum(1 for s in ss if "；" in s), "分号句位置": [i + 1 for i, s in enumerate(ss) if "；" in s],
            "词接断点": sum(1 for i in range(len(ss) - 1) if link(ss[i], ss[i + 1]) == "无")}


# ---- 盲标：多个裁判逐对多数票 ----
def most(xs, default=""):
    xs = [x for x in xs if x not in (None, "")]
    return collections.Counter(xs).most_common(1)[0][0] if xs else default


def merge(paras):
    """同一标签的几份判定合成一份：每对先投 并列／非并列（平票算并列），再在胜方里取最多的关系"""
    if len(paras) == 1:
        return paras[0]
    keys = []
    for d in paras:
        for p in d["句对"]:
            if p.get("对") not in keys:
                keys.append(p.get("对"))
    pairs = []
    for k in keys:
        votes = [p for d in paras for p in d["句对"] if p.get("对") == k]
        par = [p for p in votes if p["关系"] == "并列"]
        side = par if 2 * len(par) >= len(votes) else [p for p in votes if p["关系"] != "并列"]
        pairs.append({"对": k, "关系": most([p["关系"] for p in side]),
                      "并列种类": most([p.get("并列种类") for p in side]) if side is par else "",
                      "伪翻转": (2 * sum(1 for p in side if p.get("伪翻转")) > len(side)) if side is par else False,
                      "票数": f"{len(side)}/{len(votes)}"})
    howe = collections.defaultdict(list)
    for d in paras:
        for x in d.get("然而") or []:
            howe[x.get("句")].append(bool(x.get("前句有预期")))
    counts = sorted(len(d.get("塞句") or []) for d in paras)
    med = counts[len(counts) // 2]
    return {"标签": paras[0]["标签"], "句对": pairs,
            "然而": [{"句": s, "前句有预期": 2 * sum(v) > len(v)} for s, v in howe.items()],
            "塞句": next(d.get("塞句") or [] for d in paras if len(d.get("塞句") or []) == med),
            "末句收束": 2 * sum(1 for d in paras if d.get("末句收束")) > len(paras),
            "最像凑的一句": paras[0].get("最像凑的一句")}


def pair_end(k):
    m = re.search(r"(\d+)\s*$", str(k))
    return int(m.group(1)) if m else None


def blind_metrics(d):
    rel = collections.Counter(p["关系"] for p in d["句对"])
    swap = sum(1 for p in d["句对"] if p["关系"] == "并列" and p.get("并列种类") == "换话题")
    second = next((p for p in d["句对"] if str(p.get("对", "")).replace(" ", "").startswith("1→2")), None)
    fake = {pair_end(p.get("对")) for p in d["句对"] if p["关系"] == "并列" and p.get("伪翻转")}
    fake |= {x.get("句") for x in (d.get("然而") or []) if x.get("前句有预期") is False}
    denom = sum(v for k, v in rel.items() if k != "收束")
    push = sum(rel[k] for k in PUSH)
    return {"关系计数": {k: rel.get(k, 0) for k in ["缩小", "举证", "原因", "推论", "翻转", "并列", "收束"]},
            "换话题并列": swap, "第2句并列": bool(second and second["关系"] == "并列"),
            "伪翻转": len(fake), "推进率": round(push / denom, 3) if denom else 0.0,
            "末句收束": bool(d.get("末句收束")), "塞句": len(d.get("塞句") or []),
            "最像凑的一句": d.get("最像凑的一句")}


def checks(m, b):
    if m is None or b is None:
        return [False] * 13
    return [m["lint问题"] == 0, m["引文未命中"] == 0, 300 <= m["字数"] <= 400 and 5 <= m["句数"] <= 7,
            m["本文"] == 0, m["法条"] == 0, m["文件全名"] <= 2 and m["引号原话"] <= 2 and m["含数字句"] <= 1,
            m["分号句"] == 0, b["换话题并列"] <= 1, not b["第2句并列"], b["伪翻转"] == 0,
            b["推进率"] >= 2 / 3, b["末句收束"], b["塞句"] == 0]


def load_judges(run, suffix=""):
    pat = re.compile(re.escape(f"盲标结果{suffix}") + r"_(\d+)\.json")
    multi = sorted((int(m.group(1)), p) for p in run.glob(f"盲标结果{suffix}_*.json") if (m := pat.fullmatch(p.name)))
    single = run / f"盲标结果{suffix}.json"
    files = [p for _, p in multi] or ([single] if single.exists() else [])
    return [json.loads(read(f)) for f in files]


def judge_who(run, suffix, n):
    p = run / f"盲标_meta{suffix}.json"
    if not p.exists():
        return f"未记录 ×{n}"
    j = json.loads(read(p))
    return f"{j.get('后端')} {j.get('模型')} ×{n}"


HIST_COLS = ["run_id", "日期", "用例", "技能commit", "脏否", "模型", "rep", "总分", "通过项", "换话题并列", "伪翻转",
             "推进率", "lint问题", "字数", "句数", "秒", "输出token"]


def append_history(path, rows):
    old = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            old = list(csv.DictReader(f, delimiter="\t"))
    keys = {(r["run_id"], r["模型"], r["rep"]) for r in rows}
    old = [r for r in old if (r["run_id"], r["模型"], r["rep"]) not in keys]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HIST_COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in old + rows:
            w.writerow(r)


def fmt(v):
    return "—" if v is None else v


def score(run, suffix=""):
    run = pathlib.Path(run).expanduser().resolve()
    meta = load_meta(run)
    if not meta:
        sys.exit(f"缺 {run / '输入包_meta.json'}")
    material = case_dir(run, meta) / "材料.md"
    order_file = run / "盲标顺序.json"
    judges = load_judges(run, suffix)
    if not judges or not order_file.exists():
        sys.exit(f"缺 盲标结果{suffix}.json：先跑 judge.py --run {run}，或用 --ingest 导入")
    who = judge_who(run, suffix, len(judges))
    order = json.loads(read(order_file))["顺序"]
    by_file = {v: k for k, v in order.items()}
    per_label = collections.defaultdict(list)
    for j in judges:
        for d in j["段落"]:
            per_label[d["标签"]].append(d)
    one_line = [j.get("一句话", "") for j in judges]

    res = []
    for path, model, rep in outputs(run):
        p = body(read(path))
        mp = run / (path.stem + "_meta.json")
        om = json.loads(read(mp)) if mp.exists() else {}
        lab = by_file.get(path.name)
        m = mechanical(p, material) if p else None
        b = blind_metrics(merge(per_label[lab])) if (p and lab and per_label.get(lab)) else None
        if p and b is None:
            print(f"{path.name}：裁判结果里没有它的标签 {lab}")
        ck = checks(m, b)
        cj = None
        if b and isinstance(b.get("最像凑的一句"), dict):
            i = b["最像凑的一句"].get("句")
            ss = sents(p)
            cj = {"句": i, "原句": ss[i - 1] if isinstance(i, int) and 0 < i <= len(ss) else "",
                  "理由": b["最像凑的一句"].get("理由", "")}
        res.append({"文件": path.name, "列名": path.stem[len("输出_"):], "模型": model, "rep": rep, "标签": lab,
                    "正文": p, "机械": m, "盲标": b, "检查": ck, "通过": sum(ck), "最像凑": cj,
                    "秒": om.get("seconds"), "输出token": output_tokens(om)})

    cols = [r["列名"] for r in res]
    L = ["# 分数表（自动生成）", "",
         f"run：{run.name}　用例：{meta.get('用例')}　技能：{meta.get('技能commit')}" + ("（有未提交改动）" if meta.get("有未提交改动") else "")
         + f"　裁判：{who}", "",
         "| 检查项 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for i, name in enumerate(CHECKS):
        L.append(f"| {i + 1}. {name} | " + " | ".join("✓" if r["检查"][i] else "✗" for r in res) + " |")
    def row(name, f):
        L.append(f"| {name} | " + " | ".join(str(fmt(f(r))) for r in res) + " |")
    row("**总分**", lambda r: f"**{r['通过']}/13**")
    row("推进率", lambda r: r["盲标"] and r["盲标"]["推进率"])
    row("换话题并列", lambda r: r["盲标"] and r["盲标"]["换话题并列"])
    row("伪翻转", lambda r: r["盲标"] and r["盲标"]["伪翻转"])
    row("字数", lambda r: r["机械"] and r["机械"]["字数"])
    row("句数", lambda r: r["机械"] and r["机械"]["句数"])
    row("分号句（第几句）", lambda r: r["机械"] and (f"{r['机械']['分号句']}（{'、'.join(map(str, r['机械']['分号句位置']))}）" if r["机械"]["分号句"] else 0))
    row("lint 问题／提示", lambda r: r["机械"] and f"{r['机械']['lint问题']}／{r['机械']['lint提示']}")
    row("引文 数／未命中", lambda r: r["机械"] and f"{r['机械']['引文数']}／{fmt(r['机械']['引文未命中'])}")
    row("词接断点（只报）", lambda r: r["机械"] and r["机械"]["词接断点"])
    row("首句零篇三字片段（只报）", lambda r: r["机械"] and r["机械"]["首句零篇三字以上片段"])
    row("耗时（秒）", lambda r: r["秒"])
    row("输出 token", lambda r: r["输出token"])
    L += ["", "## 最像凑的一句", ""]
    for r in res:
        c = r["最像凑"]
        L.append(f"- {r['列名']}：" + (f"第 {c['句']} 句「{c['原句']}」——{c['理由']}" if c else ("无正文" if not r["正文"] else "无")))
    L += ["", "## 裁判一句话", ""] + [f"- {s}" for s in one_line if s]
    L += ["", "## 盲标顺序揭晓", ""] + [f"- {k} = {v}" for k, v in order.items()]
    nobody = [r["文件"] for r in res if not r["正文"]]
    if nobody:
        L.append("- 无正文：" + "、".join(nobody))
    write(run / f"分数表{suffix}.md", "\n".join(L) + "\n")
    write(run / f"分数{suffix}.json", json.dumps({"run": run.name, "meta": meta, "裁判": who, "检查项": CHECKS, "裁判一句话": one_line,
                                        "输出": res}, ensure_ascii=False, indent=1))

    date = (meta.get("生成时间") or datetime.date.today().isoformat())[:10]
    rows = [{"run_id": run.name + suffix, "日期": date, "用例": meta.get("用例"), "技能commit": meta.get("技能commit"),
             "脏否": int(bool(meta.get("有未提交改动"))), "模型": r["模型"], "rep": str(r["rep"]),
             "总分": f"{r['通过']}/13", "通过项": "".join("1" if c else "0" for c in r["检查"]),
             "换话题并列": fmt(r["盲标"] and r["盲标"]["换话题并列"]), "伪翻转": fmt(r["盲标"] and r["盲标"]["伪翻转"]),
             "推进率": fmt(r["盲标"] and r["盲标"]["推进率"]), "lint问题": fmt(r["机械"] and r["机械"]["lint问题"]),
             "字数": fmt(r["机械"] and r["机械"]["字数"]), "句数": fmt(r["机械"] and r["机械"]["句数"]),
             "秒": fmt(r["秒"]), "输出token": fmt(r["输出token"])} for r in res]
    append_history(run_root(run) / "历史.tsv", rows)
    print("\n".join(L))
    return run / f"分数表{suffix}.md"


def main():
    ap = argparse.ArgumentParser(description="机械校加盲标出分数表")
    ap.add_argument("--run", required=True)
    ap.add_argument("--suffix", default="", help="与 judge.py 的 --suffix 相同")
    a = ap.parse_args()
    print(score(a.run, a.suffix))


if __name__ == "__main__":
    main()
