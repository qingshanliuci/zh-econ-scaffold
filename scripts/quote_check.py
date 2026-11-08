#!/usr/bin/env python3
# INPUT: 稿件文件（默认只查以 "> " 开头的引文块，--all 查全部行）；一个或多个来源（--source 本地文本文件或 http(s) 链接，可重复）；--min 引文最短字数（默认 6）
# OUTPUT: 稿件里每条引号内文字是否在某个来源里逐字出现；未命中的给出最接近的来源片段；有未命中退出码 1
# POS: zh-econ-scaffold 工具层的引文核对：政策法规、党代会报告的原话只能逐字抄，论文里的转述不作出处
import re, sys, argparse, difflib, html, urllib.request

# 弯引号与直角引号开闭不同，可直接配对；不跨行、不含表格竖线
CURLY_RE = re.compile(r'“([^“”\n|]+)”|「([^「」\n|]+)」')
# 全角半角统一，去空白
TRANS = str.maketrans({'，': ',', '。': '.', '：': ':', '；': ';', '（': '(', '）': ')', '％': '%',
                       '、': ',', '“': '"', '”': '"', '‘': "'", '’': "'", '—': '-', '－': '-',
                       '０': '0', '１': '1', '２': '2', '３': '3', '４': '4', '５': '5', '６': '6', '７': '7', '８': '8', '９': '9'})


def norm(s):
    s = s.translate(TRANS)
    return re.sub(r'\s+', '', s)


def body_lines(text, all_lines):
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('> '):
            yield s[2:]
        elif all_lines:
            yield s


def extract_quotes(line, min_len):
    """弯引号按正则取；直引号 " 开闭同形，按出现顺序两两配对，
    这样 "十四五"规划纲要要求"完善……" 里取到的是 完善……，不是 规划纲要要求。"""
    out = []
    for m in CURLY_RE.finditer(line):
        q = next(g for g in m.groups() if g)
        out.append(q)
    pos = [i for i, ch in enumerate(line) if ch == '"']
    for a, b in zip(pos[0::2], pos[1::2]):
        out.append(line[a + 1:b])
    return [q.strip() for q in out if len(q.strip()) >= min_len and '|' not in q]


def load_source(src):
    if src.startswith(('http://', 'https://')):
        req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0 quote-check'})
        raw = urllib.request.urlopen(req, timeout=30).read()
        txt = None
        for enc in ('utf-8', 'gb18030'):
            try:
                txt = raw.decode(enc); break
            except UnicodeDecodeError:
                pass
        if txt is None:
            txt = raw.decode('utf-8', 'ignore')
        txt = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', txt, flags=re.S | re.I)
        txt = re.sub(r'<[^>]+>', ' ', txt)
        return html.unescape(txt)
    return open(src, encoding='utf-8', errors='ignore').read()


def nearest(q, src_text):
    pieces = [p for p in re.split(r'[。；\n]', src_text) if len(p.strip()) >= 6]
    best = difflib.get_close_matches(q, pieces, n=1, cutoff=0.3)
    return best[0].strip()[:80] if best else ''


def main():
    ap = argparse.ArgumentParser(description='引文逐字核对')
    ap.add_argument('draft')
    ap.add_argument('--source', action='append', required=True, help='来源文件或链接，可重复')
    ap.add_argument('--min', type=int, default=6)
    ap.add_argument('--all', action='store_true', help='查全部行，而不只是 "> " 引文块')
    a = ap.parse_args()
    draft = open(a.draft, encoding='utf-8').read()
    quotes = []
    for line in body_lines(draft, a.all):
        for q in extract_quotes(line, a.min):
            if q not in quotes:
                quotes.append(q)
    if not quotes:
        print('稿件里没有引号内文字（最短 %d 字；默认只查 "> " 引文块，可加 --all）' % a.min); return
    sources = {}
    for s in a.source:
        try:
            sources[s] = load_source(s)
        except Exception as e:
            print(f'来源读不到：{s}（{e}）')
    nsrc = {k: norm(v) for k, v in sources.items()}
    miss = 0
    for q in quotes:
        nq = norm(q)
        hit = [k for k, v in nsrc.items() if nq in v]
        if hit:
            print(f'命中  「{q}」 ← {hit[0]}')
        else:
            miss += 1
            cand = ''
            for k, v in sources.items():
                c = nearest(q, v)
                if c:
                    cand = f'{c}（{k}）'; break
            print(f'未命中「{q}」' + (f'\n       最接近：{cand}' if cand else ''))
    print(f'共 {len(quotes)} 条引文，{miss} 条未命中')
    sys.exit(1 if miss else 0)


if __name__ == '__main__':
    main()
