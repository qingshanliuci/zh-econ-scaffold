# -*- coding: utf-8 -*-
# INPUT: --run RUN_DIR（含 输出_*.md 与 输入包_meta.json）；用例 题目.md 的 X： Y： 两行；judge_prompt.md；--judge cli|deepseek|file；--judge-model；--judges N；--batch（整批一次判，默认按段并行）；--ingest 外部 JSON；--suffix 结果文件名后缀（同一 run 换裁判时区分）
# OUTPUT: RUN_DIR/盲标输入.md（标签与正文）、盲标顺序.json（标签 → 文件名）、盲标结果<后缀>.json（N>1 时 盲标结果<后缀>_<n>.json）、盲标_meta<后缀>.json（裁判是谁、模式 perpara／batch、每段与总耗时、成本）；默认每段单独一次调用、线程并行，各段 JSON 合成同一结构，每段对象带 一句话；解析失败存 盲标结果<后缀>_原文[_标签].txt 并退出 3；file 模式写 待判_裁判提示.md
# POS: 回归测试第 3 步：把各输出的正文打乱匿名，交裁判逐对标句间关系
import argparse, json, pathlib, random, re, sys, threading, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import (REGRESS, JUDGE_SYSTEM, NOT_LOGGED_MSG, LABELS, RELATIONS, read, write, body, outputs,
                    stable_seed, load_meta, case_dir, parse_topic, deepseek, claude, claude_logged_in)


def extract_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("回复里没有 { … }")
    return json.loads(text[i:j + 1])


def validate(obj, labels=None):
    if not isinstance(obj, dict) or not isinstance(obj.get("段落"), list):
        raise ValueError("缺 段落 列表")
    seen = set()
    for d in obj["段落"]:
        if not isinstance(d, dict) or "标签" not in d or not isinstance(d.get("句对"), list):
            raise ValueError("某段缺 标签 或 句对 列表")
        for p in d["句对"]:
            if p.get("关系") not in RELATIONS:
                raise ValueError(f"{d['标签']} {p.get('对')} 的关系「{p.get('关系')}」不在七类里")
        seen.add(d["标签"])
    if labels is not None and set(labels) - seen:
        raise ValueError("缺这些标签的判定：" + "、".join(sorted(set(labels) - seen)))
    return obj


def prepare(run):
    """抽正文、打乱、写 盲标输入.md 与 盲标顺序.json；返回 (提示头, [(标签, 正文)])；提示头 = judge_prompt.md + X/Y 行"""
    items, empty = [], []
    for path, model, rep in outputs(run):
        p = body(read(path))
        (items if p else empty).append((path.name, p))
    rnd = random.Random(stable_seed(run.name))
    rnd.shuffle(items)
    order = {LABELS[i]: name for i, (name, _) in enumerate(items)}
    write(run / "盲标顺序.json", json.dumps({"顺序": order, "无正文": [n for n, _ in empty]}, ensure_ascii=False, indent=1))
    blind = blind_text([(LABELS[i], p) for i, (_, p) in enumerate(items)])
    write(run / "盲标输入.md", blind)
    for n, _ in empty:
        print(f"无正文：{n}")
    topic = parse_topic(read(case_dir(run) / "题目.md"))
    header = read(REGRESS / "judge_prompt.md").rstrip("\n") + \
        f"\n\n本题的解释变量 X：{topic['X']}；被解释变量 Y：{topic['Y']}\n\n"
    return header, [(LABELS[i], p) for i, (_, p) in enumerate(items)]


def blind_text(pairs):
    return "\n\n".join(f"## {lab}\n\n{p}" for lab, p in pairs) + "\n"


def call(backend, model, prompt):
    """返回 (回复原文, meta)"""
    if backend == "deepseek":
        text, _, meta = deepseek(model, prompt, JUDGE_SYSTEM)
    else:
        text, meta = claude(model, prompt, system=JUDGE_SYSTEM)
    return text, meta


PERPARA_NOTE = ("\n本次只给你一段。顶层的\"一句话\"改写这一段自己哪处推进最顺、哪处最松，"
                "不与别的段比较。\n\n")


def judge_perpara(run, backend, model, header, pairs, suffix):
    """每段单独一次调用、线程并行；合成 {"段落": [...]}，每段对象带 一句话；返回 (结果或 None, 每段 meta)"""
    got, metas, errs = {}, {}, {}

    def one(lab, p):
        try:
            text, meta = call(backend, model, header + PERPARA_NOTE + blind_text([(lab, p)]))
        except Exception as e:
            errs[lab] = f"{type(e).__name__}: {e}"; metas[lab] = {"error": errs[lab]}
            return
        metas[lab] = meta
        try:
            obj = validate(extract_json(text), [lab])
        except ValueError as e:
            write(run / f"盲标结果{suffix}_原文_{lab}.txt", text)
            errs[lab] = f"解析失败（{e}）"
            return
        d = next(x for x in obj["段落"] if x["标签"] == lab)
        if obj.get("一句话") and not d.get("一句话"):
            d["一句话"] = obj["一句话"]
        got[lab] = d
        print(f"  {lab} 判完 {meta['seconds']} 秒", flush=True)

    ts = [threading.Thread(target=one, args=(lab, p)) for lab, p in pairs]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    for lab, e in errs.items():
        print(f"{lab}：{e}" + (f"；原文在 {run / f'盲标结果{suffix}_原文_{lab}.txt'}" if "解析" in e else ""))
    if errs:
        return None, metas
    return {"段落": [got[lab] for lab, _ in pairs]}, metas


def save_result(run, text, labels, n, total, suffix=""):
    try:
        obj = validate(extract_json(text), labels)
    except ValueError as e:
        raw = run / f"盲标结果{suffix}_原文.txt"
        write(raw, text)
        print(f"裁判回复解析失败（{e}）；原文存在 {raw}")
        sys.exit(3)
    name = f"盲标结果{suffix}.json" if total == 1 else f"盲标结果{suffix}_{n}.json"
    write(run / name, json.dumps(obj, ensure_ascii=False, indent=1))
    print(f"已存 {run / name}")


def to_file(run, prompt, suffix=""):
    write(run / "待判_裁判提示.md", prompt)
    print(f"请把裁判回复的 JSON 存为 {run / f'盲标结果{suffix}.json'}，或用 --ingest 导入（裁判提示在 {run / '待判_裁判提示.md'}）")


def judge_meta(run, suffix, info):
    write(run / f"盲标_meta{suffix}.json", json.dumps(info, ensure_ascii=False, indent=1))


def judge(run, backend="cli", model=None, judges=1, ingest=None, suffix="", batch=False):
    run = pathlib.Path(run).expanduser().resolve()
    if ingest:
        order = json.loads(read(run / "盲标顺序.json"))["顺序"]
        save_result(run, read(pathlib.Path(ingest).expanduser()), list(order), 1, 1, suffix)
        judge_meta(run, suffix, {"后端": "ingest", "模型": "外部导入", "次数": 1, "来源": pathlib.Path(ingest).name})
        return "ingest"
    if not load_meta(run):
        sys.exit(f"缺 {run / '输入包_meta.json'}（要从里面取用例名）")
    for old in run.glob(f"盲标结果{suffix}*"):
        if re.fullmatch(re.escape(f"盲标结果{suffix}") + r"(_\d+)?(_原文(_.)?\.txt|\.json)", old.name):
            old.unlink()
    header, pairs = prepare(run)
    prompt, labels = header + blind_text(pairs), [lab for lab, _ in pairs]
    if not labels:
        sys.exit("没有任何带正文的输出，无从盲标")
    if backend == "cli":
        ok, why = claude_logged_in()
        if not ok:
            print(NOT_LOGGED_MSG.format(what="裁判") if why == "未登录" else f"claude 命令行不可用（{why}）；本次裁判改为 file 模式")
            backend = "file"
    if backend == "file":
        to_file(run, prompt, suffix)
        judge_meta(run, suffix, {"后端": "file", "模型": "外部裁判", "模式": "batch", "次数": 1})
        return "file"
    m = model or ("deepseek-v4-pro" if backend == "deepseek" else "opus")
    mode = "batch" if batch else "perpara"
    rounds, t_all = [], time.time()
    for n in range(1, judges + 1):
        t0 = time.time()
        if batch:
            text, meta = call(backend, m, prompt)
            rounds.append({"秒": meta["seconds"], "成本": meta.get("total_cost_usd"), "调用": meta})
            print(f"裁判 {n}/{judges}（{backend} {m}，整批）{meta['seconds']} 秒")
            save_result(run, text, labels, n, judges, suffix)
            continue
        print(f"裁判 {n}/{judges}（{backend} {m}，按段并行 {len(pairs)} 段）", flush=True)
        obj, metas = judge_perpara(run, backend, m, header, pairs, suffix)
        wall = round(time.time() - t0, 1)
        costs = [x.get("total_cost_usd") for x in metas.values() if x.get("total_cost_usd") is not None]
        rounds.append({"秒": wall, "成本": round(sum(costs), 4) if costs else None,
                       "每段秒": {lab: metas.get(lab, {}).get("seconds") for lab in labels}, "每段": metas})
        if obj is None:
            judge_meta(run, suffix, {"后端": backend, "模型": m, "模式": mode, "次数": judges, "各次": rounds})
            sys.exit(3)
        name = f"盲标结果{suffix}.json" if judges == 1 else f"盲标结果{suffix}_{n}.json"
        write(run / name, json.dumps(obj, ensure_ascii=False, indent=1))
        print(f"已存 {run / name}（{wall} 秒）")
    costs = [r["成本"] for r in rounds if r["成本"] is not None]
    judge_meta(run, suffix, {"后端": backend, "模型": m, "模式": mode, "次数": judges,
                             "总秒": round(time.time() - t_all, 1), "总成本": round(sum(costs), 4) if costs else None,
                             "各次": rounds})
    return backend


def main():
    ap = argparse.ArgumentParser(description="句间关系盲标")
    ap.add_argument("--run", required=True)
    ap.add_argument("--judge", choices=["cli", "deepseek", "file"], default="cli")
    ap.add_argument("--judge-model", help="cli 默认 opus；deepseek 默认 deepseek-v4-pro")
    ap.add_argument("--judges", type=int, default=1)
    ap.add_argument("--ingest", help="导入外部生成的裁判 JSON（存为 盲标结果<后缀>.json）")
    ap.add_argument("--suffix", default="", help="结果文件名后缀，如 _deepseek；score.py 用同一后缀读")
    ap.add_argument("--batch", action="store_true", help="整批一次判（旧模式）；默认每段单独一次、并行")
    a = ap.parse_args()
    judge(a.run, a.judge, a.judge_model, a.judges, a.ingest, a.suffix, a.batch)


if __name__ == "__main__":
    main()
