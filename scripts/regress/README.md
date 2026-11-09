# 回归测试

技能每改一次，用一条命令让几家模型按同一份输入重写同一段（默认引言第一段），机械校加"句间关系盲标"，出一张 13 项分数表，并把分数追加进历史表。用来回答"这次改规则，分数动没动"。

Python 3 标准库，无第三方依赖。

## 目录约定

代码在本目录；用例与运行结果放在工作目录（默认 `~/学术文献夹/方法/技能回归测试_工作/`，不进仓库）：

```
<工作目录>/
  cases/<用例名>/题目.md     机读头四行 + 任务说明
  cases/<用例名>/材料.md     范文首句、词表、事实清单等，冻结后不再改
  runs/<YYYYMMDD-HHMM>_<用例名>_<技能commit>/   每次运行一个目录
  历史.tsv                   每次运行每个输出一行
```

`run` 目录必须在 `<工作目录>/runs/` 下：脚本从它往上两级找 `cases/` 与 `历史.tsv`。

## 怎么建用例

1. 新建 `cases/<用例名>/`。
2. `题目.md` 开头四行机读头（裁判要用 X、Y）：

   ```
   题目：……
   X：……
   Y：……
   层面：……
   ```

   后面写给写手的任务说明与硬要求（字数、句数、只输出几部分等）。
3. `材料.md`：写手可用的全部材料（事实清单、范文首句、词表）。引号原话会拿它逐字核对，所以政策原文要原样放进来。
4. 定稿后不再改，否则前后分数不可比。

## 怎么跑

```bash
cd <技能目录>
# 一键：拼包 → 三家写 → 盲标 → 打分 → 打印历史
python3 scripts/regress/run_all.py --case ~/学术文献夹/方法/技能回归测试_工作/cases/<用例名>

# 只对已有输出重新盲标与打分（换裁判、老目录干跑）
python3 scripts/regress/run_all.py --only-score <RUN_DIR> --judge deepseek --suffix _deepseek

# 看历史
python3 scripts/regress/history.py --case <用例名> --last 5
```

分步：

| 脚本 | 作用 | 常用参数 |
|---|---|---|
| `build_bundle.py` | 拼 `输入包.md`：题目 → SKILL.md 与六份规则 → 材料 → "现在开始"；记 `输入包_meta.json`（技能 commit、是否有未提交改动、各文件 sha1） | `--case`、`--out`、`--rules` |
| `run_models.py` | 各模型并行写，存 `输出_<模型>[_nothink]_r<k>.md` 与同名 `_meta.json`、`_reasoning.md` | `--models deepseek-flash,deepseek-v4-pro,opus`、`--reps`、`--no-think`、`--opus-via cli\|file` |
| `judge.py` | 抽正文、按目录名定种子打乱成 甲乙丙…，交裁判标相邻句关系 | `--judge cli\|deepseek\|file`、`--judge-model`、`--judges N`、`--ingest`、`--suffix` |
| `score.py` | 调 lint / quote_check / phrase_freq 加盲标结果，出 `分数表.md`、`分数.json`，写历史 | `--suffix` |
| `history.py` | 按用例、模型打印最近几次分数 | `--case`、`--last` |
| `run_all.py` | 串起以上四步 | `--case`、`--only-score`、`--judge`、`--judge-model`、`--suffix` |

DeepSeek 的密钥从 `~/.claude/secrets/deepseek_search.env` 的 `DEEPSEEK_API_KEY=` 读，只进请求头，不打印、不写文件。

claude 命令行后端固定用 `claude -p --model <模型> --no-session-persistence --output-format json --setting-sources project --system-prompt …`，提示从 stdin 喂，子进程在空临时目录里跑，避免读到用户自己的 CLAUDE.md。不要加 `--bare`（会跳过登录凭据）。

同一个 run 换裁判再判一次：给 `--suffix`（如 `_deepseek`），结果存 `盲标结果_deepseek.json`、`分数表_deepseek.md`，历史表里 run_id 也带这个后缀；表头写明裁判是谁。盲标顺序由目录名决定，换裁判不变。

`--judges N` 判 N 次，逐对多数票（并列／非并列，平票算并列）。

## file 模式怎么接力

claude 命令行未登录（或不可用）时，opus 写手与 cli 裁判自动降级为 file 模式，`run_all.py` 打印还缺哪一步后以 0 退出。

- **opus 写手**：脚本写 `待写_opus_r<k>.md`（就是输入包）与 `待写_说明.txt`。让人或 Claude Code 会话里的 Opus 子代理读该文件，把回复整个存为 `输出_opus_r<k>.md`，再跑 `run_all.py --only-score <RUN_DIR>`。
- **裁判**：脚本写 `待判_裁判提示.md`。把回复的 JSON 存为 `盲标结果.json`，或存成任意文件后 `judge.py --run <RUN_DIR> --ingest 文件.json`（会校验结构），再跑 `score.py --run <RUN_DIR>`。注意 `--only-score` 会重新盲标，接力裁判结果时直接跑 `score.py`。

## 13 项检查

| # | 检查项 | 来源 |
|---|---|---|
| 1 | lint 问题数 = 0 | `lint.py --json` |
| 2 | 引号原话全部在 材料.md 里逐字命中（无引文算过） | `quote_check.py` |
| 3 | 字数 300–400 且句数 5–7 | lint |
| 4 | "本文" = 0 | 自算 |
| 5 | 法条 = 0 | lint 首段材料 |
| 6 | 文件全名 ≤ 2、引号原话 ≤ 2、含数字句 ≤ 1 | lint 首段材料 |
| 7 | 含全角分号的句子 = 0 | 自算 |
| 8 | 换话题并列 ≤ 1 | 盲标 |
| 9 | 第 2 句（1→2）不是并列 | 盲标 |
| 10 | 伪翻转 = 0（关系=并列且伪翻转，或"然而"前句无预期） | 盲标 |
| 11 | 推进率 ≥ 2/3：（缩小+举证+原因+推论+翻转）／非收束对数 | 盲标 |
| 12 | 末句收束 | 盲标 |
| 13 | 塞句 = 0 | 盲标 |

总分 = 通过项数／13。没抽到正文（第一个 ≥80 字的 `> ` 引文块）的输出 13 项全不过。另报不判：词接断点（后句与前句无回指、无共用词的对数）、首句里在顶刊首句语料中 0 篇的三字以上片段个数（`phrase_freq.py` 需本地统计表，没有就显示 —）。

裁判口径在 `judge_prompt.md`，改口径先改那里，改后历史分数不再可比。

## 历史表字段（`历史.tsv`，制表符分隔）

| 字段 | 含义 |
|---|---|
| run_id | run 目录名（换裁判时带 `--suffix`） |
| 日期 | 输入包生成日期 |
| 用例 | 用例名 |
| 技能commit | 拼包时技能仓库的短哈希 |
| 脏否 | 1 = 拼包时技能有未提交改动 |
| 模型 | 如 deepseek-v4-pro、deepseek-flash_nothink、opus |
| rep | 第几次重复（老文件名没有 `_r<k>` 记 1） |
| 总分 | 如 11/13 |
| 通过项 | 13 位 1/0，顺序同上表 |
| 换话题并列、伪翻转、推进率 | 盲标指标 |
| lint问题、字数、句数 | 机械指标 |
| 秒、输出token | 写手耗时与输出 token（有则记） |

同一 run_id + 模型 + rep 重跑会覆盖该行。
