# -*- coding: utf-8 -*-
# INPUT: <工作目录>/历史.tsv（score.py 追加）；--case 用例名（不给则全部）；--last 每个用例×模型显示最近几个 run（默认 5；同一 run 的各 rep 各占一行，多 rep 另加均值行）；--file 另指历史表
# OUTPUT: 终端表：按用例、模型分组，最近 N 次的 日期、run、技能 commit、总分、换话题并列、伪翻转、推进率
# POS: 回归测试的回看层：改规则后一眼看分数动没动
import argparse, collections, csv, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import WORK


def num(v):
    try:
        return float(v.split("/")[0]) if "/" in v else float(v)
    except (ValueError, AttributeError):
        return None


def mean(rs, key):
    xs = [x for x in (num(r[key]) for r in rs) if x is not None]
    if not xs:
        return "—"
    v = sum(xs) / len(xs)
    return f"{v:.1f}/13" if key == "总分" else f"{v:.2f}"


def show(case=None, last=5, path=None):
    path = pathlib.Path(path).expanduser() if path else WORK / "历史.tsv"
    if not path.exists():
        print(f"还没有历史表：{path}")
        return
    with path.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if not case or r["用例"] == case]
    if not rows:
        print(f"历史表里没有用例 {case} 的记录")
        return
    # 按 run 分组；run 的先后取它在历史表里第一次出现的位置（score.py 追加写，越靠后越新）。
    # 不按 run_id 字符串排序：带时间的 run_id（数字）与"干跑"之类的中文 run_id 排不到一起
    groups = collections.defaultdict(dict)
    for i, r in enumerate(rows):
        groups[(r["用例"], r["模型"])].setdefault(r["run_id"], []).append(r)
    for (c, m), runs in sorted(groups.items()):
        print(f"\n{c} · {m}")
        print("  日期        技能commit  rep   总分     换话题并列  伪翻转  推进率  run")
        for run_id in list(runs)[-last:]:
            rs = sorted(runs[run_id], key=lambda r: int(r["rep"] or 1))
            for r in rs:
                commit = r["技能commit"] + ("*" if r["脏否"] == "1" else "")
                print(f"  {r['日期']:<11} {commit:<10}  {r['rep']:<4}  {r['总分']:<7}  {r['换话题并列']:<10}  {r['伪翻转']:<6}  {r['推进率']:<6}  {run_id}")
            if len(rs) > 1:
                print(f"  {'':<11} {'':<10}  均值  {mean(rs, '总分'):<7}  {mean(rs, '换话题并列'):<10}  {'':<6}  {mean(rs, '推进率'):<6}  （{len(rs)} 次）")
    print("\n（commit 后带 * 表示当时技能有未提交改动）")


def main():
    ap = argparse.ArgumentParser(description="回看回归测试历史")
    ap.add_argument("--case")
    ap.add_argument("--last", type=int, default=5)
    ap.add_argument("--file")
    a = ap.parse_args()
    show(a.case, a.last, a.file)


if __name__ == "__main__":
    main()
