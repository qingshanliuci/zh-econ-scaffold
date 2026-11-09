# -*- coding: utf-8 -*-
# INPUT: --run RUN_DIR（含 输出_*.md 与 输入包_meta.json）；用例 题目.md 的 X： Y： 两行；judge_prompt.md；--judge cli|deepseek|file；--judge-model；--judges N；--ingest 外部 JSON；--suffix 结果文件名后缀（同一 run 换裁判时区分）
# OUTPUT: RUN_DIR/盲标输入.md（标签与正文）、盲标顺序.json（标签 → 文件名）、盲标结果<后缀>.json（N>1 时 盲标结果<后缀>_<n>.json）、盲标_meta<后缀>.json（裁判是谁、耗时）；解析失败存 盲标结果<后缀>_原文.txt 并退出 3；file 模式写 待判_裁判提示.md
# POS: 回归测试第 3 步：把各输出的正文打乱匿名，交裁判逐对标句间关系
import argparse, json, pathlib, random, re, sys
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
    """抽正文、打乱、写 盲标输入.md 与 盲标顺序.json；返回 (裁判提示, 标签列表)"""
    items, empty = [], []
    for path, model, rep in outputs(run):
        p = body(read(path))
        (items if p else empty).append((path.name, p))
    rnd = random.Random(stable_seed(run.name))
    rnd.shuffle(items)
    order = {LABELS[i]: name for i, (name, _) in enumerate(items)}
    write(run / "盲标顺序.json", json.dumps({"顺序": order, "无正文": [n for n, _ in empty]}, ensure_ascii=False, indent=1))
    blind = "\n\n".join(f"## {LABELS[i]}\n\n{p}" for i, (_, p) in enumerate(items))
    write(run / "盲标输入.md", blind + "\n")
    for n, _ in empty:
        print(f"无正文：{n}")
    topic = parse_topic(read(case_dir(run) / "题目.md"))
    prompt = read(REGRESS / "judge_prompt.md").rstrip("\n") + \
        f"\n\n本题的解释变量 X：{topic['X']}；被解释变量 Y：{topic['Y']}\n\n" + blind + "\n"
    return prompt, list(order)


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


def judge(run, backend="cli", model=None, judges=1, ingest=None, suffix=""):
    run = pathlib.Path(run).expanduser().resolve()
    if ingest:
        order = json.loads(read(run / "盲标顺序.json"))["顺序"]
        save_result(run, read(pathlib.Path(ingest).expanduser()), list(order), 1, 1, suffix)
        judge_meta(run, suffix, {"后端": "ingest", "模型": "外部导入", "次数": 1, "来源": pathlib.Path(ingest).name})
        return "ingest"
    if not load_meta(run):
        sys.exit(f"缺 {run / '输入包_meta.json'}（要从里面取用例名）")
    for old in run.glob(f"盲标结果{suffix}*"):
        if re.fullmatch(re.escape(f"盲标结果{suffix}") + r"(_\d+)?(_原文\.txt|\.json)", old.name):
            old.unlink()
    prompt, labels = prepare(run)
    if not labels:
        sys.exit("没有任何带正文的输出，无从盲标")
    if backend == "cli":
        ok, why = claude_logged_in()
        if not ok:
            print(NOT_LOGGED_MSG.format(what="裁判") if why == "未登录" else f"claude 命令行不可用（{why}）；本次裁判改为 file 模式")
            backend = "file"
    if backend == "file":
        to_file(run, prompt, suffix)
        judge_meta(run, suffix, {"后端": "file", "模型": "外部裁判", "次数": 1})
        return "file"
    metas = []
    for n in range(1, judges + 1):
        if backend == "deepseek":
            m = model or "deepseek-v4-pro"
            text, _, meta = deepseek(m, prompt, JUDGE_SYSTEM)
        else:
            m = model or "opus"
            text, meta = claude(m, prompt, system=JUDGE_SYSTEM)
        metas.append(meta)
        print(f"裁判 {n}/{judges}（{backend} {m}）{meta['seconds']} 秒")
        save_result(run, text, labels, n, judges, suffix)
    judge_meta(run, suffix, {"后端": backend, "模型": m, "次数": judges, "各次": metas})
    return backend


def main():
    ap = argparse.ArgumentParser(description="句间关系盲标")
    ap.add_argument("--run", required=True)
    ap.add_argument("--judge", choices=["cli", "deepseek", "file"], default="cli")
    ap.add_argument("--judge-model", help="cli 默认 opus；deepseek 默认 deepseek-v4-pro")
    ap.add_argument("--judges", type=int, default=1)
    ap.add_argument("--ingest", help="导入外部生成的裁判 JSON（存为 盲标结果<后缀>.json）")
    ap.add_argument("--suffix", default="", help="结果文件名后缀，如 _deepseek；score.py 用同一后缀读")
    a = ap.parse_args()
    judge(a.run, a.judge, a.judge_model, a.judges, a.ingest, a.suffix)


if __name__ == "__main__":
    main()
