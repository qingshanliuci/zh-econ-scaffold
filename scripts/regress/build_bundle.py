# -*- coding: utf-8 -*-
# INPUT: --case 用例目录（含 题目.md、材料.md）；技能 SKILL.md 与 references 里的规则文件（默认六份，--rules 可改）；技能仓库的 git 状态
# OUTPUT: RUN_DIR/输入包.md（题目 → 技能文件 → 材料 → 收尾一句）与 RUN_DIR/输入包_meta.json（用例、技能 commit 与是否有未提交改动、各技能文件 sha1 前 8 位与字数）；打印 RUN_DIR
# POS: 回归测试第 1 步：给各家模型拼一字不差的同一份输入
import argparse, datetime, hashlib, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import SKILL, WORK, read, write, hanzi, git

DEFAULT_RULES = "intro-thinking,register-rules,sentence-chaining,first-sentences,landing-the-question,sentence-functions"


def build(case, out=None, rules=DEFAULT_RULES):
    case = pathlib.Path(case).expanduser().resolve()
    name = case.name
    topic, material = read(case / "题目.md"), read(case / "材料.md")
    commit = git("rev-parse", "--short", "HEAD") or "nogit"
    dirty = bool(git("status", "--porcelain"))
    now = datetime.datetime.now()
    run = pathlib.Path(out).expanduser() if out else WORK / "runs" / f"{now:%Y%m%d-%H%M}_{name}_{commit}"
    run.mkdir(parents=True, exist_ok=True)
    files = ["SKILL.md"] + [f"references/{r.strip()}.md" for r in rules.split(",") if r.strip()]
    parts, finfo = [topic.rstrip("\n")], []
    for i, rel in enumerate(files, 1):
        txt = read(SKILL / rel)
        parts.append(f"\n\n---\n\n# 技能文件 {i}：{rel}\n\n" + txt)
        finfo.append({"文件": rel, "sha1": hashlib.sha1(txt.encode("utf-8")).hexdigest()[:8],
                      "字符数": len(txt), "汉字数": hanzi(txt)})
    parts.append("\n\n---\n\n" + material.strip("\n"))
    parts.append("\n\n---\n\n现在开始。只输出四部分。")
    bundle = "".join(parts)
    write(run / "输入包.md", bundle)
    meta = {"用例": name, "技能commit": commit, "有未提交改动": dirty, "生成时间": now.strftime("%Y-%m-%d %H:%M"),
            "技能文件": finfo, "输入包字符数": len(bundle), "输入包汉字数": hanzi(bundle)}
    write(run / "输入包_meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    return run, meta


def main():
    ap = argparse.ArgumentParser(description="拼回归测试输入包")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out")
    ap.add_argument("--rules", default=DEFAULT_RULES, help="references 里的文件名，逗号分隔，不带扩展")
    a = ap.parse_args()
    run, meta = build(a.case, a.out, a.rules)
    print(run)
    print(f"输入包 {meta['输入包字符数']} 字符，汉字 {meta['输入包汉字数']}；技能 {meta['技能commit']}"
          + ("（有未提交改动）" if meta["有未提交改动"] else ""))


if __name__ == "__main__":
    main()
