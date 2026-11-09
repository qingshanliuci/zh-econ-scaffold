# -*- coding: utf-8 -*-
# INPUT: <工作目录>/历史.tsv（score.py 追加）；--case 用例名（不给则全部）；--last 每个用例×模型显示最近几次（默认 5）；--file 另指历史表
# OUTPUT: 终端表：按用例、模型分组，最近 N 次的 日期、run、技能 commit、总分、换话题并列、伪翻转、推进率
# POS: 回归测试的回看层：改规则后一眼看分数动没动
import argparse, collections, csv, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import WORK


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
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["用例"], r["模型"])].append(r)
    for (c, m), rs in sorted(groups.items()):
        rs.sort(key=lambda r: (r["run_id"], int(r["rep"] or 1)))
        print(f"\n{c} · {m}")
        print("  日期        技能commit  rep  总分   换话题并列  伪翻转  推进率  run")
        for r in rs[-last:]:
            commit = r["技能commit"] + ("*" if r["脏否"] == "1" else "")
            print(f"  {r['日期']:<11} {commit:<10}  {r['rep']:<3}  {r['总分']:<5}  {r['换话题并列']:<10}  {r['伪翻转']:<6}  {r['推进率']:<6}  {r['run_id']}")
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
