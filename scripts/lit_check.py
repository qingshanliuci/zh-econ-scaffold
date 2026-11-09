#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# INPUT: 一个 markdown 或纯文本稿，文献综述节正文放在以 "> " 开头的引文块里（每段一个引文块；--all 检查全部非标题段落）
# OUTPUT: 终端报告：引用条数与每千字密度、叙述式（作者名作主语）占比、按作者排队的连续句、点名不报发现、段首以作者起句、缺口句个数与位置与有无原因、"本文"次数与位置、总起句支数与分支标记是否对得上、句首衔接词占比、"综上／此外"次数、空话与禁用词、过长句与分号并句；每段一行小表（字数、引用、首句起头类别、末句是否收束）；--json 机器可读；有问题退出码 1
# POS: zh-econ-scaffold 工具层：文献综述节的机械检查；顶刊参照数来自 1155 篇文献综述节的统计（references/literature-review.md），查不出的交审稿人
import re, sys, json, argparse

CITE_PAREN = re.compile(r'[（(]([^（）()]{1,160}?(?:19|20)\d{2}[a-z]?[^（）()]{0,40}?)[）)]')
YEAR = re.compile(r'(?:19|20)\d{2}[a-z]?')
BARE_YEAR = re.compile(r'[（(]((?:19|20)\d{2}[a-z]?(?:[，,、；;]\s*(?:19|20)\d{2}[a-z]?)*)[）)]')
NARR = re.compile(r'(?:^|[，。；：、“\s])((?:[A-Z][A-Za-z\'\-]+(?:\s*(?:et\s*al\.?|等|和|与|&|and)\s*[A-Z]?[A-Za-z\'\-]*)?|[一-鿿]{2,4}(?:等|和[一-鿿]{2,4}|与[一-鿿]{2,4}|、[一-鿿]{2,4})?)\s*[（(](?:19|20)\d{2}[a-z]?(?:[，,、；;]\s*(?:19|20)\d{2}[a-z]?)*[）)])(?=[^。，；]{0,2}(?:发现|认为|指出|证实|证明|强调|提出|表明|显示|揭示|考察|研究|检验|分析|估计|测算|探讨|讨论|关注|比较|构建|发展|拓展|将|把|则|也|进一步|基于|利用|使用|采用|借助|通过|从|以|对|在|的|等|曾|最早|首次|率先|较早|系统|详细|同样|却|亦|均|和|与))')
NAME_START = re.compile(r'^(?:自|早在|正如|如|例如)?\s*(?:[A-Z][A-Za-z\'\-]+|[一-鿿]{2,4})(?:\s*(?:et\s*al\.?|等|和|与|&|and)\s*[A-Z]?[A-Za-z\'\-]*|等|和[一-鿿]{2,4})?\s*[（(](?:19|20)\d{2}')
GAP = ['鲜有', '较少', '甚少', '很少', '尚未', '尚无', '尚缺', '缺乏', '忽视', '忽略', '未能', '未见', '有待', '空白', '寥寥', '仍不清楚', '并不清楚', '尚不清楚', '尚不明确', '仍未', '亟待', '亟需', '匮乏', '不足', '未得到', '未有', '几乎没有', '少有', '相对较少', '尚待']
ZONGQI = re.compile(r'(?:(?:与|和)本(?:文|研究)[^。]{0,25}?(?:相关|有关|密切|联系|关联)[^。]{0,20}?(?:文献|研究)[^。]{0,16}?|(?:现有|已有|既有|相关|以往|过往|这些|关于[^。]{1,20}的?)(?:文献|研究)[^。]{0,16}?|本(?:文|研究)[^。]{0,15}?(?:文献|研究)[^。]{0,12}?)(?:主要)?(?:可以?)?(?:大致)?(?:分为|归为|可分为|划分为|分成|集中于|集中在|围绕|涉及|包括|有|来自|源于|归纳为|概括为|沿着|基于|从)[^。]{0,8}?(两|三|四|五|六|几|以下|如下|若干|[2-6])\s*(?:个)?(支|类|方面|条|股|个|种|脉络|线索|分支|视角|角度|方向|层面|维度|主线|部分|流派)')
CNNUM = {'两': 2, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6}
BRANCH = re.compile(r'^(?:第([一二三四五六])(?:支|类|个方面|方面|条|股|个|种|脉络|线索)|第([一二三四五六])[，,、]|其([一二三四五六])|([一二三四五六])是|另一(?:支|类|条|种|股)|[（(]\s*([1-6一二三四五六])\s*[）)])')
CONN = ['因此', '此外', '然而', '但是', '同时', '一方面', '另一方面', '其次', '首先', '最后', '再次', '尽管', '虽然', '综上所述', '综上', '基于此', '进一步', '具体而言', '事实上', '与此同时', '可见', '据此', '不过', '由此可见', '总体而言', '总体来看', '此后', '随后', '实际上', '所以', '相比之下', '值得注意的是', '遗憾的是', '需要指出的是', '近年来', '总之', '鉴于此', '为此', '由此', '例如', '换言之']
EMPTY = ['进入视野', '进入研究视野', '面临新的变化', '恰在', '恰逢', '学界普遍认为', '学术界普遍认为', '众所周知', '不言而喻', '毋庸置疑', '填补空白', '填补了空白', '理论和现实意义', '理论与现实意义', '理论意义和现实意义', '日益受到关注', '越来越受到关注', '受到越来越多的关注', '——', '张力', '赋能', '抓手', '至关重要', '在一定程度上', '脉络', '图景', '据我们所知']
SENT_SPLIT = re.compile(r'(?<=[。！？])')


def paragraphs(text, all_paras):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('> '):
            out.append(s[2:].strip())
        elif all_paras and not s.startswith(('|', '-', '*', '```', '<', '[')):
            out.append(s)
    return out


def sentences(p):
    return [s.strip() for s in SENT_SPLIT.split(p) if s.strip()]


def cites(text):
    groups = CITE_PAREN.findall(text)
    refs = sum(max(1, len(YEAR.findall(g))) for g in groups)
    refs += sum(len(YEAR.findall(g)) for g in BARE_YEAR.findall(text))  # 作者名在括号外的叙述式引用
    return refs, sum(1 for g in groups if len(YEAR.findall(g)) >= 2), len(NARR.findall(text))


def first_cat(s):
    if NAME_START.match(s):
        return '点名'
    if BRANCH.match(s):
        return '分支序数'
    if re.match(r'^(?:与本文|本文|与上述|与已有|与既有|与现有|相比|相较|不同于|区别于)', s):
        return '本文'
    for w in CONN:
        if s.startswith(w):
            return '衔接词'
    if re.match(r'^(?:已有|现有|既有|以往|早期|近期|大量|大多数|多数|部分|一些|不少|许多|众多|相关|后续|也有|另有|有研究|有学者|学术界|学界|国内外|这些|上述|关于|有关|文献|研究)', s):
        return '文献主语'
    return '对象或判断'


def main():
    ap = argparse.ArgumentParser(description='文献综述节机械检查')
    ap.add_argument('file')
    ap.add_argument('--all', action='store_true', help='检查全部非标题段落，而不只是 "> " 引文块')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    text = open(a.file, encoding='utf-8').read()
    paras = paragraphs(text, a.all)
    if not paras:
        print('没有找到正文：把文献综述节每段放在以 "> " 开头的引文块里，或加 --all'); sys.exit(2)
    sents = [s for p in paras for s in sentences(p)]
    full = ''.join(paras)
    n_chars = len(re.findall(r'[一-鿿]', full))
    problems, hints, rows = [], [], []
    refs, multi, narr = cites(full)
    per_k = round(1000 * refs / max(1, len(full)), 1)
    narr_share = narr / refs if refs else 0
    # 1 引用密度与放法
    if refs == 0:
        problems.append('没有一处（作者，年）出处：文献综述节顶刊每篇中位 17 条、每千字 5.8 条')
    elif per_k < 2.5:
        hints.append(f'每千字引用 {per_k} 条，顶刊四分位 3.3／5.8／8.8（近年 7.4）：文献少了，或在讲自己的话')
    if refs and narr_share > 0.5:
        problems.append(f'作者名作主语的叙述式引用占 {narr_share:.0%}（{narr}/{refs}）：2024 年后顶刊只有 26%，出处多数压进句末括号；把"A（年）发现___"改成"___（A，年）"')
    elif refs and narr_share > 0.35:
        hints.append(f'叙述式引用占 {narr_share:.0%}，近年顶刊 26%，老文章 74%；能压进括号的尽量压')
    # 2 排队：连续三句以上作者名起句
    run, best, best_at = 0, 0, None
    for i, s in enumerate(sents, 1):
        if NAME_START.match(s):
            run += 1
            if run > best:
                best, best_at = run, i
        else:
            run = 0
    if best >= 3:
        problems.append(f'第 {best_at - best + 1} 至 {best_at} 句连续 {best} 句以作者名起句：按作者排队，没有统领判断；先写一句这些研究共同说明什么，再把出处放括号')
    name_first_paras = [i for i, p in enumerate(paras, 1) if NAME_START.match(sentences(p)[0]) if sentences(p)]
    if name_first_paras:
        hints.append(f'第 {"、".join(map(str, name_first_paras))} 段以作者名开段：顶刊 4011 段里只有 0.8%，文献先归类再点名')
    # 3 缺口
    gap_idx = [i for i, s in enumerate(sents, 1) if any(w in s for w in GAP)]
    if not gap_idx:
        problems.append('没有缺口句（鲜有／尚未／忽视／较少／有待……）：88.7% 的顶刊文献综述节至少有一句，中位 2 句')
    elif len(sents) >= 8 and gap_idx[0] > 0.8 * len(sents):
        hints.append(f'缺口全在最后两成（第 {gap_idx[0]} 句起）：顶刊第一个缺口句的位置中位在三成处，每支文献收尾处就可以立一个小缺口')
    if len(gap_idx) >= 6:
        hints.append(f'缺口句 {len(gap_idx)} 句，顶刊四分位 1／2／4：缺口多了像在数落，合并成两三条')
    # 3b 点名不报发现、缺口不带原因
    FOUND = re.compile(r'发现|表明|指出|认为|证实|证明|显示|揭示|提出|得出|结论|结果|显著|正向|负向|促进|抑制|提高|降低|增加|减少|有助于|有利于|导致|影响|效应|作用|关系|决定|依赖|取决')
    bare = [i for i, s in enumerate(sents, 1) if NARR.search(s) and not FOUND.search(s)]
    if len(bare) >= 2:
        hints.append(f'第 {"、".join(map(str, bare))} 句点名了作者却没有报出发现（只说"研究了／考察了／讨论了"）：点名句要带结论，否则读者不知道它在证明什么')
    REASON = re.compile(r'原因|因为|由于|源于|在于|受限|限于|缺少|缺失|数据|难以|无法|不等于|不同于|并非|不是|只能|尚无法|没有.{0,6}数据')
    if gap_idx and not any(REASON.search(sents[i - 1]) or (i < len(sents) and REASON.search(sents[i])) for i in gap_idx):
        hints.append('缺口句后面没有一句"为什么少"或"相近文献为什么不算"：顶刊好的缺口都跟一句原因或排除（数据缺失、口径不同、A 不等于 B）')
    # 4 本文
    bw = [i for i, s in enumerate(sents, 1) if '本文' in s or '本研究' in s]
    if not bw:
        hints.append('没有"本文"：93% 的顶刊文献综述节有（中位 3 次），至少在末段说清本文与上述文献的关系')
    else:
        early = [i for i in bw if i <= len(sents) / 3 and not re.search(r'与本(?:文|研究)[^。]{0,8}(?:相关|有关|密切)|本(?:文|研究)(?:的研究)?(?:与|和)[^。]{0,12}(?:文献|研究)', sents[i - 1])]
        if len(early) >= 2:
            hints.append(f'前三分之一里有 {len(early)} 句"本文"（第 {"、".join(map(str, early))} 句）而不是"与本文相关的文献"一类总起：顶刊"本文"句 56% 在后三分之一，前面先让文献说话')
        if len(bw) > 8:
            hints.append(f'"本文"{len(bw)} 次，顶刊四分位 1／3／5：定位压到末段两三句，贡献条目留给引言')
    last_para_s = sentences(paras[-1])
    if last_para_s and '本文' not in paras[-1] and not any(w in paras[-1] for w in GAP):
        hints.append('最后一段既没有"本文"也没有缺口句：顶刊 79% 的末段含"本文"、47% 含缺口，这一节要收到本文与文献的关系上')
    # 5 总起与分支
    zq = next((s for s in sents if ZONGQI.search(s) and len(s) < 220), None)
    if zq:
        m = ZONGQI.search(zq)
        n = CNNUM.get(m.group(1))
        marks = []
        for s in sents:
            mm = BRANCH.match(s)
            if mm:
                marks.append(s[:8])
        if n and len(marks) and len(marks) < n:
            problems.append(f'总起句说有 {n} 支，分支标记只找到 {len(marks)} 处（{"、".join(marks)}）：每支要有"第 N 支／一是／另一类"一类起头，与总起对得上')
        if n and n >= 4:
            hints.append(f'总起句分 {n} 支：顶刊两支 108 篇、三支 57 篇、四支 7 篇，四支以上少见，合并到三支以内')
    # 6 衔接词
    conn_n = sum(1 for s in sents if any(s.startswith(w) for w in CONN))
    share = conn_n / max(1, len(sents))
    if share > 0.3:
        problems.append(f'句首衔接词 {conn_n}/{len(sents)} 句（{share:.0%}）：顶刊文献综述节 17%；用名词回指或直接推进代替"此外／同时／然而"')
    elif share > 0.22:
        hints.append(f'句首衔接词 {share:.0%}，顶刊 17%')
    zs = sum(1 for s in sents if s.startswith(('综上所述', '综上')))
    if zs > 1:
        problems.append(f'"综上（所述）"起句 {zs} 次：一节至多一次，放末段')
    cw = sum(1 for s in sents if s.startswith('此外'))
    if cw >= 3:
        hints.append(f'"此外"起句 {cw} 次：顶刊 1155 篇共 864 句，平均每篇不到 1 句；"此外"是换话题的标记，多了就是在排材料')
    # 7 空话与禁用词
    for w in EMPTY:
        c = full.count(w)
        if c:
            problems.append(f'"{w}" {c} 次：顶刊文献综述节不用或几乎不用')
    # 8 长句与分号
    for i, s in enumerate(sents, 1):
        if len(s) > 150:
            hints.append(f'第 {i} 句 {len(s)} 字：顶刊文献节均句长约 55 字，群引长句拆成判断句加括号')
        if '；' in s and not CITE_PAREN.search(s):
            hints.append(f'第 {i} 句含分号而不是在括号里分隔出处：两个功能并在一句，拆开')
    # 9 每段一行
    k = 0
    for i, p in enumerate(paras, 1):
        ss = sentences(p)
        if not ss:
            continue
        r_, m_, n_ = cites(p)
        last = ss[-1]
        end = '缺口' if any(w in last for w in GAP) else '本文' if '本文' in last else '归纳' if last.startswith(('综上', '总体', '可见', '由此可见', '上述', '这些研究', '这些文献')) else '—'
        rows.append(dict(段=i, 字数=len(re.findall(r'[一-鿿]', p)), 句数=len(ss), 引用=r_, 叙述式=n_, 首句起头=first_cat(ss[0]), 末句=end, 首句=ss[0][:40]))
        k += len(ss)
    report = dict(文件=a.file, 字数=n_chars, 句数=len(sents), 段数=len(paras), 引用条数=refs, 每千字引用=per_k, 叙述式条数=narr, 叙述式占比=round(narr_share, 2), 群引括号=multi,
                  缺口句=gap_idx, 本文句=bw, 总起句=zq[:80] if zq else '', 句首衔接词占比=round(share, 2), 问题=problems, 提示=hints, 段表=rows)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f'字数 {n_chars}，{len(sents)} 句 {len(paras)} 段；引用 {refs} 条（每千字 {per_k}，叙述式 {narr} 条占 {narr_share:.0%}，群引括号 {multi}）；缺口句 {len(gap_idx)}，"本文"句 {len(bw)}，句首衔接词 {share:.0%}')
        print(f'顶刊参照（1155 篇）：字数中位 2166，39 句 4 段；引用 17 条、每千字 5.8；叙述式近年 26%；缺口 2 句、首个在三成处；"本文"3 次、56% 在后三分之一；句首衔接词 17%')
        print('\n| 段 | 字数 | 句数 | 引用 | 叙述式 | 首句起头 | 末句收法 | 首句 |\n|---|---|---|---|---|---|---|---|')
        for r in rows:
            print(f"| {r['段']} | {r['字数']} | {r['句数']} | {r['引用']} | {r['叙述式']} | {r['首句起头']} | {r['末句']} | {r['首句']} |")
        print(f'\n问题 {len(problems)}：')
        for x in problems:
            print('  - ' + x)
        print(f'提示 {len(hints)}（不计入问题）：')
        for x in hints:
            print('  - ' + x)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
