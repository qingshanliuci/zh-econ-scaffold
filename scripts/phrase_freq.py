#!/usr/bin/env python3
# INPUT: 候选句（命令行位置参数，或 --file 稿.md 取 "> " 引文块每段第一句，加 --all-sentences 取全部句）；参考句集 TSV（默认作者本机 节首句.tsv，--type 选节类型，--col 选列，同一文件同一节类型取节序最小的一条）
# OUTPUT: 每句的少见片段表（2 至 6 字汉字片段在参考句集里出现的篇数与占比，嵌套折叠）、命中的骨架及其现场篇数、禁区词及其篇数、末行结论；--json 机器可读；--strict 时有 3 字以上片段 0 篇或命中禁区词退出码 1
# POS: zh-econ-scaffold 工具层的用词频度核对：写第一句后查"顶刊第一句里有没有人这样说"，补 lint.py 查不到的搭配生僻
import re, sys, csv, json, argparse, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint import paragraphs, sentences  # noqa: E402

DEFAULT_TSV = os.path.expanduser('~/学术文献夹/方法/句子结构统计_工作/结果/节首句.tsv')

STOP_CHARS = set('的了是在和与对及其而并也就都把被为以于之从由等着过将这那此该或即所则')

SKELETONS = [
    ('党的___提出／指出／强调', r'党的.{1,12}(提出|指出|强调)'),
    ('随着___起句', r'^随着'),
    ('近年来起句', r'^近年来'),
    ('自___以来起句', r'^自.{1,15}以来'),
    ('改革开放起句', r'^改革开放'),
    ('当前／目前起句', r'^(当前|目前)'),
    ('在___背景／进程下起句', r'^在.{1,20}(背景|进程)下'),
    ('是___的重要', r'是.{1,30}的重要'),
    ('是___的关键', r'是.{1,30}的关键'),
    ('是___的基础', r'是.{1,30}的基础'),
    ('既是___也是', r'既是.{1,30}也是'),
    ('不仅___也／而且／更', r'不仅.{1,30}(也|而且|更)'),
    ('事关／关乎／关系到', r'(事关|关乎|关系到)'),
    ('历来／一直／始终是', r'(历来|一直|始终)是'),
    ('（作者，年）文献括号', r'[（(][^）)]*\d{4}[）)]'),
    ('《》文件名', r'《[^》]+》'),
    ('含数字', r'\d'),
]

FORBIDDEN = ['系于', '归根结底', '毋庸置疑', '众所周知', '值得注意的是', '不可忽视的是', '不言而喻', '综上所述',
             '学术界普遍认为', '有待检验', '有待探讨', '恰在', '恰逢', '取决于', '至关重要', '日益凸显']

PUNCT = str.maketrans({',': '，', ';': '；', ':': '：', '(': '（', ')': '）', '?': '？', '!': '！'})


def norm(s):
    return s.translate(PUNCT).strip()


def load_refs(path, types, col):
    best = {}
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if types and r.get('节类型') not in types:
                continue
            try:
                k = int(r.get('节序') or 0)
            except ValueError:
                k = 0
            key = (r.get('文件'), r.get('节类型'))  # 多选节类型时每类各取一条
            if key not in best or k < best[key][0]:
                best[key] = (k, norm(r.get(col) or ''))
    return [v[1] for v in best.values()]


def strip_material(s):
    s = re.sub(r'《[^》]*》|“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"', ' ', s)
    s = re.sub(r'[\d.%％]+', ' ', s)
    # 在"的""是""了"处断开：跨这几个字的片段多是两个短语硬拼，篇数为零也说明不了什么；"是___的关键"这类搭配交给骨架表
    s = re.sub(r'(?<!目)的(?!确)', ' ', s)
    s = re.sub(r'(?<![但于就还凡正总而不可只其别即要若或])是(?!否)', ' ', s)
    return re.sub(r'(?<![为除])了(?!解)', ' ', s)


def runs(s):
    return re.findall(r'[一-鿿]+', strip_material(s))


def grams(s):
    out = {}
    for run in runs(s):
        for n in range(2, 7):
            for i in range(len(run) - n + 1):
                g = run[i:i + n]
                if not all(c in STOP_CHARS for c in g) and g not in out:
                    out[g] = run[max(0, i - 2):i + n + 2]
    return out


def doc_count(g, refs, cache):
    if g not in cache:
        cache[g] = sum(1 for r in refs if g in r)
    return cache[g]


def subs(g):
    return [g[i:i + n] for n in range(2, len(g)) for i in range(len(g) - n + 1)]


def analyze(sent, refs, cache, max_rare):
    N = len(refs)
    gs = grams(sent)
    cnt = {g: doc_count(g, refs, cache) for g in gs}
    # 折叠：只报"最短"的少见片段，即没有任何子片段同样少见；再附左右两半的篇数，看是搭配少见还是词少见
    rows = []
    for g, c in cnt.items():
        if c > max_rare or (len(g) == 2 and c > 0):
            continue
        tier = 0 if c == 0 else 1
        if any(cnt.get(s, N) <= (0 if tier == 0 else max_rare) for s in subs(g) if s in cnt):
            continue
        row = {'片段': g, '上下文': gs[g], '长度': len(g), '篇数': c, '占比': round(c / N * 100, 2) if N else 0}
        if len(g) >= 3:
            l, r = g[:-1], g[1:]
            row['拆开'] = {x: (cnt[x] if x in cnt else doc_count(x, refs, cache)) for x in (l, r)}
        rows.append(row)
    rows.sort(key=lambda x: (x['篇数'], 0 if x['长度'] >= 3 else 1, -x['长度']))
    sk = []
    for name, pat in SKELETONS:
        if re.search(pat, norm(sent)):
            k = sum(1 for r in refs if re.search(pat, r))
            sk.append({'骨架': name, '篇数': k, '占比': round(k / N * 100, 1) if N else 0})
    fb = [{'词': w, '篇数': doc_count(w, refs, cache)} for w in FORBIDDEN if w in sent]
    long_rows = [x for x in rows if x['长度'] >= 3]
    return {'句': sent, '少见片段': rows, '骨架': sk, '禁区词': fb, '最少见': long_rows[:3],
            '有零篇长片段': any(x['篇数'] == 0 for x in long_rows)}


def collect(a):
    if not a.file:
        return a.sentences
    text = open(a.file, encoding='utf-8').read()
    out = []
    for p in paragraphs(text, a.all):
        ss = sentences(p)
        out.extend(ss if a.all_sentences else ss[:1])
    return out


def main():
    ap = argparse.ArgumentParser(description='候选句片段在顶刊参考句集里的篇数')
    ap.add_argument('sentences', nargs='*', help='候选句，可多句')
    ap.add_argument('--file', help='稿件；默认取 "> " 引文块每段第一句')
    ap.add_argument('--all', action='store_true', help='与 --file 合用：也取非引文块的正文段')
    ap.add_argument('--all-sentences', action='store_true', help='与 --file 合用：取全部句子')
    ap.add_argument('--tsv', default=DEFAULT_TSV)
    ap.add_argument('--type', default='引言', help='节类型，逗号分隔可多选；传空串不过滤')
    ap.add_argument('--col', default='节首句')
    ap.add_argument('--max', type=int, default=2, help='少见片段的篇数上限（默认 2）')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    cands = collect(a)
    if not cands:
        print('没有候选句：给位置参数，或 --file 稿.md'); sys.exit(2)
    types = set(t for t in a.type.split(',') if t)
    refs = load_refs(a.tsv, types, a.col)
    if not refs:
        print(f'参考句集为空：{a.tsv} 节类型 {a.type}'); sys.exit(2)
    cache = {}
    res = [analyze(s, refs, cache, a.max) for s in cands]
    if a.json:
        print(json.dumps({'参考篇数': len(refs), '节类型': a.type, '结果': res}, ensure_ascii=False, indent=1))
    else:
        print(f'参考句集：{a.type or "全部"} {len(refs)} 篇（每篇取节序最小的一句）')
        for i, r in enumerate(res, 1):
            print(f'\n第 {i} 句：{r["句"]}')
            if r['禁区词']:
                print('  禁区词：' + '，'.join(f'「{x["词"]}」{x["篇数"]} 篇' for x in r['禁区词']))
            if r['骨架']:
                print('  骨架：' + '，'.join(f'{x["骨架"]} {x["篇数"]} 篇（{x["占比"]}%）' for x in r['骨架']))
            if r['少见片段']:
                print('  少见片段（篇数 ≤ %d）：' % a.max)
                for x in r['少见片段']:
                    tail = ''
                    if '拆开' in x:
                        tail = '  拆开：' + ' ／ '.join(f'{k} {v}' for k, v in x['拆开'].items())
                    print(f'    {x["片段"]}（{x["上下文"]}）  {x["长度"]} 字  {x["篇数"]} 篇  {x["占比"]}%{tail}')
            else:
                print('  少见片段：无')
            if r['最少见']:
                print('  结论：最少见的三字以上片段 ' + '，'.join(f'「{x["片段"]}」{x["篇数"]} 篇' for x in r['最少见']))
            else:
                print(f'  结论：三字以上片段都在 {a.max + 1} 篇以上')
    bad = any(r['有零篇长片段'] or r['禁区词'] for r in res)
    sys.exit(1 if (a.strict and bad) else 0)


if __name__ == '__main__':
    main()
