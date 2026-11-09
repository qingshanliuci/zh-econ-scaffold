# -*- coding: utf-8 -*-
# INPUT: 技能目录（本文件上两级）；工作目录 ~/学术文献夹/方法/技能回归测试_工作/（cases/、runs/、历史.tsv）；~/.claude/secrets/deepseek_search.env 的 DEEPSEEK_API_KEY；claude 命令行
# OUTPUT: 回归测试各脚本共用的函数：路径常量、正文抽取与切句、题目头解析、输出文件名解析、DeepSeek 接口调用、claude 命令行探测与调用
# POS: scripts/regress/ 的公共层；build_bundle / run_models / judge / score / history / run_all 都 import 它
import hashlib, json, pathlib, re, shutil, subprocess, tempfile, time, urllib.request

SKILL = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL / "scripts"
REGRESS = SCRIPTS / "regress"
WORK = pathlib.Path("~/学术文献夹/方法/技能回归测试_工作").expanduser()
KEY_FILE = pathlib.Path("~/.claude/secrets/deepseek_search.env").expanduser()
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
WRITER_SYSTEM = "你是中文经济学论文写手，严格按用户给的技能文件工作，只输出要求的内容。"
JUDGE_SYSTEM = "你是中文经济学顶刊的审稿人，严格按用户给的口径判断，只输出一个 JSON 对象。"
NOT_LOGGED_MSG = "claude 命令行未登录，请在终端运行 `claude /login`；本次 {what} 改为 file 模式"
LABELS = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
RELATIONS = ["缩小", "举证", "原因", "推论", "翻转", "并列", "收束"]
OUT_RE = re.compile(r"^输出_(?P<model>.+?)(?:_r(?P<rep>\d+))?\.md$")


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


def write(p, s):
    pathlib.Path(p).write_text(s, encoding="utf-8")


def hanzi(s):
    return len(re.findall(r"[一-鿿]", s))


def run_root(run_dir):
    """run 目录在 <工作目录>/runs/<id>/，工作目录取它的上两级"""
    return pathlib.Path(run_dir).resolve().parent.parent


def load_meta(run_dir):
    p = pathlib.Path(run_dir) / "输入包_meta.json"
    return json.loads(read(p)) if p.exists() else {}


def case_dir(run_dir, meta=None):
    meta = meta if meta is not None else load_meta(run_dir)
    return run_root(run_dir) / "cases" / meta.get("用例", "")


def parse_topic(text):
    """题目.md 的机读头：题目： X： Y： 层面："""
    out = {}
    for key in ("题目", "X", "Y", "层面"):
        m = re.search(r"^" + key + r"[：:]\s*(.+)$", text, re.M)
        out[key] = m.group(1).strip() if m else ""
    return out


def body(text):
    """第一个长度 ≥80 字的 `> ` 引文块（连续的 > 行拼成一块）"""
    blocks, cur = [], []
    for l in text.splitlines():
        if l.startswith(">"):
            cur.append(l.lstrip("> ").strip())
        elif cur:
            blocks.append("".join(cur)); cur = []
    if cur:
        blocks.append("".join(cur))
    blocks = [b for b in blocks if len(b) >= 80]
    return blocks[0] if blocks else ""


def sents(p):
    """按 。！？ 切句，句末的引号、括号随前句"""
    out = re.findall(r"[^。！？]*[。！？]+[”\"’」）)]*", p)
    rest = p[sum(len(s) for s in out):]
    if rest.strip():
        out.append(rest)
    return [s.strip() for s in out if s.strip()]


def outputs(run_dir):
    """run 目录里的输出文件，排除 _reasoning 与 待写_；返回 [(path, 模型, rep)]，rep 缺省为 1"""
    res = []
    for p in sorted(pathlib.Path(run_dir).glob("输出_*.md")):
        if p.stem.endswith("_reasoning"):
            continue
        m = OUT_RE.match(p.name)
        if m:
            res.append((p, m.group("model"), int(m.group("rep") or 1)))
    return res


def stable_seed(s):
    return int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16) % (2 ** 32)


def git(*args):
    r = subprocess.run(["git", "-C", str(SKILL)] + list(args), capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


# ---------- DeepSeek ----------

def deepseek_key():
    for l in KEY_FILE.read_text(encoding="utf-8").splitlines():
        if l.startswith("DEEPSEEK_API_KEY="):
            k = l.split("=", 1)[1].strip().strip('"').strip("'")
            if k:
                return k
    raise RuntimeError("没读到 DEEPSEEK_API_KEY（%s）" % KEY_FILE)


def deepseek(model, user, system, no_think=False, max_tokens=32000, timeout=900):
    """返回 (content, reasoning, meta)；密钥只进请求头，不进返回值"""
    body_ = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
             "max_tokens": max_tokens, "stream": False}
    if no_think:
        body_["thinking"] = {"type": "disabled"}
    req = urllib.request.Request(DEEPSEEK_URL, data=json.dumps(body_, ensure_ascii=False).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + deepseek_key(), "Content-Type": "application/json"})
    t0 = time.time()
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    dt = time.time() - t0
    msg = resp["choices"][0]["message"]
    meta = {"model": resp.get("model", model), "seconds": round(dt, 1), "usage": resp.get("usage"),
            "finish_reason": resp["choices"][0].get("finish_reason"),
            "reasoning_chars": len(msg.get("reasoning_content") or ""), "error": None}
    return msg.get("content") or "", msg.get("reasoning_content") or "", meta


# ---------- claude 命令行 ----------

def claude_cmd(model, system=None):
    # 只读项目级设置，且 cwd 设为空目录，避免加载用户全局 CLAUDE.md 污染输出；不加 --bare（它会跳过 claude.ai 登录凭据）
    cmd = ["claude", "-p", "--model", model, "--no-session-persistence", "--output-format", "json",
           "--setting-sources", "project"]
    if system:
        cmd += ["--system-prompt", system]
    return cmd


def claude_run(model, user, system=None, timeout=1800):
    """在空临时目录里跑 claude -p；返回 (解析后的 JSON 或 None, 原始输出, 秒)"""
    d = tempfile.mkdtemp(prefix="zh-regress-")
    try:
        t0 = time.time()
        r = subprocess.run(claude_cmd(model, system), input=user, capture_output=True, text=True, timeout=timeout, cwd=d)
        dt = time.time() - t0
    finally:
        shutil.rmtree(d, ignore_errors=True)
    try:
        return json.loads(r.stdout), r.stdout + r.stderr, dt
    except ValueError:
        return None, r.stdout + r.stderr, dt


def claude_logged_in():
    """用一句话探测；返回 (是否可用, 原因)；原因为"未登录"时调用方打印 NOT_LOGGED_MSG"""
    try:
        j, raw, _ = claude_run("haiku", "回复 ok", timeout=120)
    except FileNotFoundError:
        return False, "找不到 claude 命令"
    except subprocess.TimeoutExpired:
        return False, "claude 探测超时"
    if j is None:
        return False, "claude 输出不是 JSON：" + raw[:200]
    if j.get("is_error") and "Not logged in" in str(j.get("result", "")):
        return False, "未登录"
    if j.get("is_error"):
        return False, "claude 报错：" + str(j.get("result", ""))[:200]
    return True, ""


def claude(model, user, system=None, timeout=1800):
    """返回 (content, meta)；出错抛 RuntimeError（is_error 时消息为 result 原文）"""
    j, raw, dt = claude_run(model, user, system, timeout)
    if j is None:
        raise RuntimeError("claude 输出不是 JSON：" + raw[:300])
    if j.get("is_error"):
        raise RuntimeError(str(j.get("result", ""))[:1000])
    meta = {"model": model, "seconds": round(dt, 1), "usage": j.get("usage"), "finish_reason": j.get("stop_reason"),
            "error": None}
    for k in ("modelUsage", "duration_ms", "total_cost_usd"):
        if j.get(k) is not None:
            meta[k] = j[k]
    return j.get("result") or "", meta


def output_tokens(meta):
    u = (meta or {}).get("usage") or {}
    return u.get("completion_tokens", u.get("output_tokens"))
