#!/usr/bin/env python3
# INPUT: 一个 markdown 或纯文本稿；默认只检查以 "> " 开头的引文块（正文），--all 检查全部非标题段落
# OUTPUT: 终端报告：禁用词、叙事时间词、"然而"每段次数、句首引导词后缺逗号、收段轻词、句长、句首衔接词占比；首段另查首句禁区词与"本文"起句、材料密度（文件全名、引号原话、含数字句、法条）、相邻两句跳材料，首句功能是定义／数据／文件／理论引述时给"提示"（不计入问题数）；--json 输出机器可读；有问题退出码 1
# POS: zh-econ-scaffold 工具层的语感 lint：机械能查的先机械查，查不出的留给审稿人；规则来自 2370 篇顶刊的衔接词与用词统计、3351 篇各节第一句统计（references/first-sentences.md）
import re, sys, json, argparse

BANNED = ['——', '—', '重构', '张力', '赋能', '抓手', '至关重要', '值得注意的是', '在一定程度上',
          '赓续', '擘画', '锚点', '基石', '消解', '弥合', '掣肘', '桎梏', '困局', '迷思', '图景',
          '底色', '症结', '场域', '脉络', '语境', '要么']
NARRATIVE = ['此后', '在此背景下', '同一时期', '恰在', '恰逢', '正是', '犹如', '恰好']
LIGHT_END = ['有待检验', '有待探讨', '值得研究', '有待回答', '有待进一步研究', '有待进一步探讨']
# 句首独立引导词与两可词：出现在句首时后面要带逗号
OPENERS = ['此外', '然而', '另一方面', '一方面', '其次', '再次', '具体而言', '具体来说', '换言之', '基于此',
           '为此', '事实上', '值得注意的是', '首先', '最后', '进一步地', '进一步', '不过', '同时', '因此',
           '由此可见', '综上', '综上所述', '鉴于此', '有鉴于此', '与此同时', '例如', '由此', '总之', '可见',
           '需要指出的是', '需要说明的是']
# 顶刊里不开句的句中缝合词
NO_OPEN = ['但', '而', '即', '从而', '进而', '使得', '导致', '则', '并且', '而且', '却']
CONN_START = OPENERS + NO_OPEN + ['但是', '所以', '于是', '并']

# 首句禁区词：2547 篇引言第一句里的篇数（references/first-sentences.md），None 表示"接近零"
FIRST_BANNED = {'系于': 0, '归根结底': 2, '毋庸置疑': 2, '众所周知': 2, '值得注意的是': 2, '不可忽视的是': None,
                '不言而喻': None, '综上所述': None, '学术界普遍认为': None, '有待检验': None, '有待探讨': None,
                '恰在': None, '恰逢': None, '取决于': 3, '至关重要': 18, '的基础，也是': 0}
QUOTE_RE = re.compile(r'“([^“”]+)”|「([^「」]+)」')
CITE_RE = re.compile(r'[（(][^（）()]*\d{4}[a-z]?[）)]')
LAW_RE = re.compile(r'(按照|根据|依据|依照)《[^》]+法》|第[一二三四五六七八九十百零〇]+条|《[^》]*(法|规定|条例|办法|细则)》(要求|规定|明确|指出|提出)')
DEFINE_RE = re.compile(r'^[^，。；]{1,30}是指|^所谓')
MAT_ORDER = ['文件', '引号原话', '数字', '文献']
LEAD_STRIP = re.compile(r'^(一方面|另一方面|此外|同时|与此同时|其次|再次|首先|最后|然而|因此|具体而言|事实上)，')

# 只按句号、问号、叹号切句；分号留在句内，否则带文献括号的长句会被切碎、句长失真
SENT_SPLIT = re.compile(r'(?<=[。！？])')


def paragraphs(text, all_paras, with_section=False):
    """with_section=True 时返回 (节号, 段)：以 # 标题分节，同一稿里并列的几个版本各算各的首段"""
    out, sec = [], 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            sec += 1
            continue
        if s.startswith('> '):
            out.append((sec, s[2:].strip()))
        elif all_paras and not s.startswith(('|', '-', '*', '```', '<', '[')):
            out.append((sec, s))
    return out if with_section else [p for _, p in out]


def sentences(p):
    return [s.strip() for s in SENT_SPLIT.split(p) if s.strip()]


def quotes(s, min_len=6):
    out = [next(g for g in m.groups() if g) for m in QUOTE_RE.finditer(s)]
    pos = [i for i, ch in enumerate(s) if ch == '"']
    out += [s[a + 1:b] for a, b in zip(pos[0::2], pos[1::2])]
    return [q for q in out if len(re.sub(r'\s', '', q)) >= min_len]


def materials(s):
    """一句里有哪几类材料：文件（书名号）、引号原话（6 字以上）、数字（文献括号里的年份不算）、文献（作者，年）"""
    kinds = set()
    if '《' in s:
        kinds.add('文件')
    if quotes(s):
        kinds.add('引号原话')
    if re.search(r'\d', CITE_RE.sub('', s)):
        kinds.add('数字')
    if CITE_RE.search(s):
        kinds.add('文献')
    return kinds


def material_led(s):
    """材料出现在句子第一个分句里（去掉句首衔接词后），即材料前面没有它要印证的判断"""
    head = re.split(r'[，；：]', LEAD_STRIP.sub('', s), maxsplit=1)[0]
    return bool(materials(head)) or head.startswith(('党的', '国务院', '中共中央'))


def check_first(p, sents):
    issues, hints = [], []
    if sents:
        s0 = sents[0]
        for w, n in FIRST_BANNED.items():
            if w in BANNED or w in NARRATIVE:
                continue  # 全文禁用词已在 check_paragraph 报过，不重复计数
            if w in s0:
                cnt = f'{n} 篇' if n is not None else '接近零'
                issues.append(f'首句用了顶刊第一句里几乎没人用的说法「{w}」（2547 篇引言第一句 {cnt}）')
        if s0.startswith('本文'):
            issues.append('首句以"本文"开头（52 篇首段首句 0 次）')
        func = []
        if DEFINE_RE.search(s0):
            func.append('定义')
        if re.search(r'\d', CITE_RE.sub('', s0)):
            func.append('数据')
        if s0.startswith('《'):
            func.append('文件')
        if CITE_RE.search(s0):
            func.append('理论引述')
        if func:
            hints.append(f'首句功能是 {"／".join(func)}，作者要求首段第一句是盖帽子的判断（定性 34.7%、政策引述 19.0% 为常见）')
    # 并列连接词起句：后一句只是换一张材料的信号（references/sentence-chaining.md）
    par = [i + 1 for i, s in enumerate(sents) if re.match(r'^(此外|另外|同时|与此同时|除此之外|还有|再者)[，,]', s)]
    if par:
        hints.append('第 ' + '、'.join(map(str, par)) + ' 句以并列连接词起句：顶刊首段里并列很少，下一句应从上一句推出来，不是换一张材料')
    docs = list(dict.fromkeys(re.findall(r'《([^》]+)》', p)))
    nq = len(quotes(p))
    nnum = sum(1 for s in sents if re.search(r'\d', CITE_RE.sub('', s)))
    nlaw = len(list(LAW_RE.finditer(p)))
    if len(docs) > 2:
        issues.append(f'首段文件全名 {len(docs)} 个（超过 2）：' + '、'.join(f'《{d}》' for d in docs))
    if nq > 2:
        issues.append(f'首段引号原话 {nq} 处（超过 2）')
    if nnum > 1:
        issues.append(f'首段含数字的句子 {nnum} 句（超过 1）')
    if nlaw >= 1:
        issues.append(f'首段法条 {nlaw} 处：首段不引法条，顶刊引言前 600 字里"按照／根据《某法》"0 至 1 篇；制度事实写成判断句，法条留给制度背景节')
    kinds = [materials(s) for s in sents]
    for i in range(len(sents) - 1):
        a, b = kinds[i], kinds[i + 1]
        # 后一句一上来就换另一类材料才算跳；先判断再带材料的句子不算
        if a and b and not (a & b) and material_led(sents[i + 1]):
            fa = '、'.join(k for k in MAT_ORDER if k in a)
            fb = '、'.join(k for k in MAT_ORDER if k in b)
            issues.append(f'相邻两句在不同材料间跳：第 {i + 1} 句（{fa}）与第 {i + 2} 句（{fb}）')
    stats = {'文件全名': len(docs), '引号原话': nq, '含数字句': nnum, '法条': nlaw}
    return issues, hints, stats


def check_paragraph(idx, p, first=False):
    issues = []
    sents = sentences(p)
    n = len(sents)
    chars = len(re.sub(r'\s', '', p))
    for w in BANNED:
        if w in p:
            issues.append(f'禁用词「{w}」{p.count(w)} 次')
    for w in NARRATIVE:
        if w in p:
            issues.append(f'叙事时间词或文学腔「{w}」{p.count(w)} 次（顶刊每万字不到 0.2）')
    k = p.count('然而')
    if k > 1:
        issues.append(f'"然而"出现 {k} 次，顶刊一段一次')
    conn_start = 0
    for s in sents:
        head = s[:6]
        for op in sorted(OPENERS, key=len, reverse=True):
            if head.startswith(op):
                conn_start += 1
                nxt = s[len(op):len(op) + 1]
                if nxt not in ('，', ','):
                    issues.append(f'句首「{op}」后没有逗号：{s[:18]}…')
                break
        else:
            for w in sorted(NO_OPEN, key=len, reverse=True):
                if head.startswith(w) and not head.startswith(('但是', '即使', '即便', '而且', '则')):
                    conn_start += 1
                    issues.append(f'句中缝合词「{w}」开句（顶刊九成在句中）：{s[:18]}…')
                    break
    if sents:
        last = sents[-1]
        for w in LIGHT_END:
            if w in last:
                issues.append(f'收段用「{w}」，分量太轻（顶刊首段零次）')
    avg = chars / n if n else 0
    if n >= 3 and avg < 40:
        issues.append(f'平均句长 {avg:.0f} 字，偏短（顶刊约 58）')
    if n >= 4 and conn_start / n > 0.35:
        issues.append(f'{conn_start}/{n} 句以衔接词开头，占比过高（顶刊约两成）')
    r = {'段': idx, '字数': chars, '句数': n, '均句长': round(avg, 1), '然而': k,
         '句首衔接词': conn_start, '问题': issues, '提示': []}
    if first:
        fi, fh, st = check_first(p, sents)
        r['问题'] += fi
        r['提示'] = fh
        r['首段材料'] = st
    return r


def main():
    ap = argparse.ArgumentParser(description='中文经济学稿件语感 lint')
    ap.add_argument('file')
    ap.add_argument('--all', action='store_true', help='检查全部非标题段落，而不只是 "> " 引文块')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--no-first', action='store_true', help='不做首段检查（首句禁区词、材料密度、跳材料、首句功能）')
    ap.add_argument('--first-para', type=int, default=1, help='每个标题节里第几段算首段（默认 1）')
    a = ap.parse_args()
    text = open(a.file, encoding='utf-8').read()
    paras = paragraphs(text, a.all, with_section=True)
    if not paras:
        print('没有找到正文段落：默认只查以 "> " 开头的引文块，可加 --all'); sys.exit(2)
    reports, seen = [], {}
    for i, (sec, p) in enumerate(paras):
        seen[sec] = seen.get(sec, 0) + 1
        first = not a.no_first and seen[sec] == a.first_para
        reports.append(check_paragraph(i + 1, p, first))
    bad = sum(len(r['问题']) for r in reports)
    if a.json:
        print(json.dumps({'段落': reports, '问题总数': bad, '提示总数': sum(len(r['提示']) for r in reports)},
                         ensure_ascii=False, indent=1))
    else:
        for r in reports:
            print(f"第 {r['段']} 段：{r['字数']} 字，{r['句数']} 句，均句长 {r['均句长']}，然而 {r['然而']} 次，句首衔接词 {r['句首衔接词']} 句")
            if '首段材料' in r:
                print('  （首段）' + '，'.join(f'{k} {v}' for k, v in r['首段材料'].items()))
            for it in r['问题']:
                print('  - ' + it)
            for it in r['提示']:
                print('  · 提示：' + it)
        nh = sum(len(r['提示']) for r in reports)
        tail = f'，另有 {nh} 条提示' if nh else ''
        print((f'共 {len(reports)} 段，{bad} 个问题' if bad else f'共 {len(reports)} 段，未发现问题') + tail)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
