# -*- coding: utf-8 -*-
# INPUT: --run RUN_DIR（含 输入包.md）；--models 逗号分隔（deepseek-flash、deepseek-v4-pro、opus）；--reps 次数；--no-think（DeepSeek 关思考）；--opus-via cli|file；DeepSeek 密钥（common.deepseek_key，只读不打印）；claude 命令行
# OUTPUT: RUN_DIR/输出_<模型>[_nothink]_r<k>.md、同名 _reasoning.md（有则写）、同名 _meta.json（seconds、usage、finish_reason、error）；opus 走 file 模式时写 待写_opus_r<k>.md 与 待写_说明.txt
# POS: 回归测试第 2 步：几家模型并行按同一输入包写；任一失败不影响其他
import argparse, json, pathlib, shutil, sys, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import WRITER_SYSTEM, NOT_LOGGED_MSG, read, write, deepseek, claude, claude_logged_in

LOCK = threading.Lock()


def say(s):
    with LOCK:
        print(s, flush=True)


def save(run, tag, content, reasoning, meta):
    if content:
        write(run / f"输出_{tag}.md", content)
    if reasoning:
        write(run / f"输出_{tag}_reasoning.md", reasoning)
    write(run / f"输出_{tag}_meta.json", json.dumps(meta, ensure_ascii=False, indent=1))


def job_deepseek(run, bundle, model, rep, no_think):
    tag = f"{model}{'_nothink' if no_think else ''}_r{rep}"
    try:
        content, reasoning, meta = deepseek(model, bundle, WRITER_SYSTEM, no_think=no_think)
        save(run, tag, content, reasoning, meta)
        say(f"完成 {tag}：{meta['seconds']} 秒，finish_reason={meta['finish_reason']}")
    except Exception as e:
        save(run, tag, "", "", {"model": model, "error": f"{type(e).__name__}: {e}"})
        say(f"失败 {tag}：{type(e).__name__}: {e}")


def job_opus_cli(run, bundle, rep):
    tag = f"opus_r{rep}"
    try:
        content, meta = claude("opus", bundle, system=WRITER_SYSTEM)
        save(run, tag, content, "", meta)
        say(f"完成 {tag}：{meta['seconds']} 秒")
    except Exception as e:
        save(run, tag, "", "", {"model": "opus", "error": f"{type(e).__name__}: {e}"})
        say(f"失败 {tag}：{type(e).__name__}: {e}")


def opus_file(run, reps):
    for k in reps:
        shutil.copyfile(run / "输入包.md", run / f"待写_opus_r{k}.md")
    lines = ["opus 一路走 file 模式：脚本不调用模型，需要人或 Claude Code 会话里的 Opus 子代理接力。", ""]
    for k in reps:
        lines.append(f"- 读 {run / f'待写_opus_r{k}.md'}，把回复整个（不删不改）存为 {run / f'输出_opus_r{k}.md'}")
    lines += ["", f"system 提示：{WRITER_SYSTEM}", "",
              f"存好后运行：python3 {pathlib.Path(__file__).resolve().parent / 'run_all.py'} --only-score {run}"]
    write(run / "待写_说明.txt", "\n".join(lines) + "\n")
    say(f"opus 待写：见 {run / '待写_说明.txt'}")


def run_models(run, models, reps=1, no_think=False, opus_via="cli"):
    run = pathlib.Path(run).expanduser().resolve()
    bundle = read(run / "输入包.md")
    rr = list(range(1, reps + 1))
    if "opus" in models and opus_via == "cli":
        ok, why = claude_logged_in()
        if not ok:
            say(NOT_LOGGED_MSG.format(what="opus 一路") if why == "未登录" else f"claude 命令行不可用（{why}）；本次 opus 一路改为 file 模式")
            opus_via = "file"
    threads = []
    for m in models:
        if m == "opus":
            if opus_via == "file":
                opus_file(run, rr)
            else:
                threads += [threading.Thread(target=job_opus_cli, args=(run, bundle, k)) for k in rr]
        elif m.startswith("deepseek"):
            threads += [threading.Thread(target=job_deepseek, args=(run, bundle, m, k, no_think)) for k in rr]
        else:
            say(f"跳过未知模型 {m}")
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return opus_via


def main():
    ap = argparse.ArgumentParser(description="几家模型按同一输入包写")
    ap.add_argument("--run", required=True)
    ap.add_argument("--models", default="deepseek-flash,deepseek-v4-pro,opus")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--opus-via", choices=["cli", "file"], default="cli")
    a = ap.parse_args()
    run_models(a.run, [m.strip() for m in a.models.split(",") if m.strip()], a.reps, a.no_think, a.opus_via)


if __name__ == "__main__":
    main()
