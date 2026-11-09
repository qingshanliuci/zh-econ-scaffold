# -*- coding: utf-8 -*-
# INPUT: --case 用例目录；--models、--reps 传给 run_models；--judge cli|deepseek|file、--judge-model、--batch、--suffix 传给 judge 与 score；--only-score RUN_DIR 跳过拼包与写手，只对已有输出盲标与打分
# OUTPUT: 顺序跑 build_bundle → run_models → judge → score，最后打印分数表路径与 history.py 的本用例摘要；opus 或裁判走 file 模式时打印还缺哪一步、文件在哪，退出码 0
# POS: 回归测试的一键入口
import argparse, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import outputs, load_meta


def step(script, *args):
    print(f"\n==== {script} {' '.join(args)}", flush=True)
    r = subprocess.run([sys.executable, str(HERE / script)] + list(args))
    if r.returncode != 0:
        sys.exit(f"{script} 失败，退出码 {r.returncode}")


def main():
    ap = argparse.ArgumentParser(description="回归测试一键跑")
    ap.add_argument("--case")
    ap.add_argument("--models", default="deepseek-flash,deepseek-v4-pro,opus")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--judge", choices=["cli", "deepseek", "file"], default="cli")
    ap.add_argument("--judge-model", help="cli 默认 opus；deepseek 默认 deepseek-v4-pro")
    ap.add_argument("--batch", action="store_true", help="裁判整批一次判；默认按段并行")
    ap.add_argument("--suffix", default="", help="盲标结果与分数表文件名后缀，同一 run 换裁判时区分")
    ap.add_argument("--only-score", metavar="RUN_DIR")
    a = ap.parse_args()

    if a.only_score:
        run = pathlib.Path(a.only_score).expanduser().resolve()
    else:
        if not a.case:
            ap.error("要么 --case，要么 --only-score")
        sys.path.insert(0, str(HERE))
        from build_bundle import build
        print("\n==== build_bundle.py", flush=True)
        run, _ = build(a.case)
        print(run)
        step("run_models.py", "--run", str(run), "--models", a.models, "--reps", str(a.reps))
        pending = [run / f"输出_opus_r{k}.md" for k in range(1, a.reps + 1)] if (run / "待写_说明.txt").exists() else []
        pending = [p for p in pending if not p.exists()]
        if pending:
            print("\n还缺 opus 的输出，盲标与打分暂停。")
            print(f"- 按 {run / '待写_说明.txt'} 写好：" + "、".join(p.name for p in pending))
            print(f"- 然后运行：python3 {HERE / 'run_all.py'} --only-score {run} --judge {a.judge}")
            return

    if not outputs(run):
        sys.exit(f"{run} 里没有 输出_*.md")
    S = a.suffix
    jargs = ["--run", str(run), "--judge", a.judge] + (["--judge-model", a.judge_model] if a.judge_model else []) \
        + (["--suffix", S] if S else []) + (["--batch"] if a.batch else [])
    step("judge.py", *jargs)
    if not ((run / f"盲标结果{S}.json").exists() or list(run.glob(f"盲标结果{S}_[0-9]*.json"))):
        sx = f" --suffix {S}" if S else ""
        print("\n裁判走了 file 模式，打分暂停。")
        print(f"- 把 {run / '待判_裁判提示.md'} 交给裁判，回复的 JSON 存为 {run / f'盲标结果{S}.json'}")
        print(f"  （或存成任意文件后：python3 {HERE / 'judge.py'} --run {run}{sx} --ingest 文件.json）")
        print(f"- 然后运行：python3 {HERE / 'score.py'} --run {run}{sx}")
        return
    step("score.py", "--run", str(run), *(["--suffix", S] if S else []))
    print(f"\n分数表：{run / f'分数表{S}.md'}")
    case = load_meta(run).get("用例")
    step("history.py", "--case", case)


if __name__ == "__main__":
    main()
