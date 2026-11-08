#!/usr/bin/env python3
# INPUT: 本地顶刊全文库目录（markdown）；关键词若干（建议 X 与 Y 各一两个）；--top N；--since 年份；--all 要求所有关键词都出现
# OUTPUT: 按命中分排序的论文清单（分、年、路径、标题里命中的词），供挑三到五篇范文
# POS: zh-econ-scaffold 工具层：从本地语料库里找同 X 同 Y 的范文；没有语料库时跳过本脚本，向用户要范文
import os, re, sys, argparse

YEAR_RE = re.compile(r'(20[0-3]\d)')


def score_file(path, kws, all_required):
    name = os.path.basename(path)
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except OSError:
        return None
    head = text[:4000]
    total = 0.0
    hits_name = []
    present = 0
    for k in kws:
        cn = name.count(k)
        ch = head.count(k)
        cb = text.count(k)
        if cb:
            present += 1
        if cn:
            hits_name.append(k)
        total += cn * 5 + ch * 1.0 + min(cb, 50) * 0.1
    if all_required and present < len(kws):
        return None
    if present == len(kws):
        total += 10
    ms = YEAR_RE.findall(path)          # 取路径里最后一个年份，避开"2016至今"这类目录名
    year = int(ms[-1]) if ms else 0
    return total, year, path, hits_name


def main():
    ap = argparse.ArgumentParser(description='在本地顶刊全文库里找同题范文')
    ap.add_argument('corpus')
    ap.add_argument('keywords', nargs='+')
    ap.add_argument('--top', type=int, default=15)
    ap.add_argument('--since', type=int, default=0)
    ap.add_argument('--all', action='store_true', help='要求所有关键词都出现')
    a = ap.parse_args()
    rows = []
    for root, _, files in os.walk(a.corpus):
        for fn in files:
            if not fn.endswith('.md'):
                continue
            r = score_file(os.path.join(root, fn), a.keywords, a.all)
            if r and r[0] > 0 and r[1] >= a.since:
                rows.append(r)
    rows.sort(key=lambda r: (-r[0], -r[1]))
    if not rows:
        print('没有命中；换关键词，或直接向用户要范文'); sys.exit(1)
    for total, year, path, hn in rows[:a.top]:
        tag = '标题含：' + '、'.join(hn) if hn else ''
        print(f'{total:6.1f}  {year}  {os.path.relpath(path, a.corpus)}  {tag}')
    print(f'共 {len(rows)} 篇命中，显示前 {min(a.top, len(rows))} 篇；范文包取三到五篇，同 X 同 Y 优先，其次同 Y')


if __name__ == '__main__':
    main()
