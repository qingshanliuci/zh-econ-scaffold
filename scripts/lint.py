#!/usr/bin/env python3
# INPUT: 一个 markdown 或纯文本稿；默认只检查以 "> " 开头的引文块（正文），--all 检查全部非标题段落
# OUTPUT: 终端报告：禁用词、叙事时间词、"然而"每段次数、句首引导词后缺逗号、收段轻词、句长、句首衔接词占比；--json 输出机器可读；有问题退出码 1
# POS: zh-econ-scaffold 工具层的语感 lint：机械能查的先机械查，查不出的留给审稿人；规则来自 2370 篇顶刊的衔接词与用词统计
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

# 只按句号、问号、叹号切句；分号留在句内，否则带文献括号的长句会被切碎、句长失真
SENT_SPLIT = re.compile(r'(?<=[。！？])')


def paragraphs(text, all_paras):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('> '):
            out.append(s[2:].strip())
        elif all_paras and not s.startswith(('#', '|', '-', '*', '```', '<', '[')):
            out.append(s)
    return out


def sentences(p):
    return [s.strip() for s in SENT_SPLIT.split(p) if s.strip()]


def check_paragraph(idx, p):
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
    return {'段': idx, '字数': chars, '句数': n, '均句长': round(avg, 1), '然而': k,
            '句首衔接词': conn_start, '问题': issues}


def main():
    ap = argparse.ArgumentParser(description='中文经济学稿件语感 lint')
    ap.add_argument('file')
    ap.add_argument('--all', action='store_true', help='检查全部非标题段落，而不只是 "> " 引文块')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    text = open(a.file, encoding='utf-8').read()
    paras = paragraphs(text, a.all)
    if not paras:
        print('没有找到正文段落：默认只查以 "> " 开头的引文块，可加 --all'); sys.exit(2)
    reports = [check_paragraph(i + 1, p) for i, p in enumerate(paras)]
    bad = sum(len(r['问题']) for r in reports)
    if a.json:
        print(json.dumps({'段落': reports, '问题总数': bad}, ensure_ascii=False, indent=1))
    else:
        for r in reports:
            print(f"第 {r['段']} 段：{r['字数']} 字，{r['句数']} 句，均句长 {r['均句长']}，然而 {r['然而']} 次，句首衔接词 {r['句首衔接词']} 句")
            for it in r['问题']:
                print('  - ' + it)
        print(f'共 {len(reports)} 段，{bad} 个问题' if bad else f'共 {len(reports)} 段，未发现问题')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
