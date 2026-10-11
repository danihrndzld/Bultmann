#!/usr/bin/env python3
"""Reconstruct structured Markdown from Vision OCR page JSON (for EPUB via pandoc).

Handles: sermon chapters, section dividers (I/II/III), verse/poetry blocks
(blockquote with line breaks), footnotes (pandoc-linked), paragraph reflow with
indent + gap detection, dehyphenation, and cross-page paragraph joins.
"""
import json, glob, os, re, sys, statistics

JSON_DIR = sys.argv[1] if len(sys.argv) > 1 else "ocr_json"
OUT_MD   = sys.argv[2] if len(sys.argv) > 2 else "bultmann_ocr.md"
files = sorted(glob.glob(os.path.join(JSON_DIR, "page-*.json")))

TERMINALS = ('.', '!', '?', ':', ';', '"', "'", '—')
INDENT = 0.018            # x-jump marking a first-line paragraph indent
VERSE_DX = 0.06           # indent (over body left) that marks a verse line
VERSE_DR = 0.05           # right-edge shortfall (under body right) for verse

# ---- sermon chapter map: {0-based page index: canonical title} ----
CHAPTERS = {
    5:  "Acts 17:22–32",              19:  "St. Matthew 6:25–33",
    32: "Genesis 8:22",               47:  "Philippians 3:7–14",
    54: "St. John 16:5–15",           67:  "Romans 8:18–27",
    79: "St. Matthew 11:28–30",       88:  "Another Season of the Year",
    96: "St. Matthew 11:2–6",         108: "St. John 8:12; 9:39; 12:35–36",
    117:"St. Luke 18:9–14",           130: "Revelation 3:14–20",
    139:"St. Luke 14:16–24",          151: "St. Luke 5:1–10",
    163:"St. Luke 17:7–10",           174: "St. Matthew 20:1–15",
    185:"St. John 16:22–33",          197: "St. Matthew 5:3–10",
    207:"2 Corinthians 4:6–11",       219: "Lamentations 3:22–41",
    234:"St. Mark 13:31–33",
}
SKIP_PAGES = {4}         # OCR'd Contents page — pandoc builds its own TOC

MONTH = re.compile(r'^(January|February|March|April|May|June|July|August|September|'
                   r'October|November|December)\b', re.I)
REFLIKE  = re.compile(r'[A-Za-z].*[\dIlO]\s*[:.]', re.ASCII)
ROMAN    = re.compile(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X)$')   # sermon sections 1–10
FN_START = re.compile(r'^(\d{1,2})[ .:]\s*')
FIRST_CH = 5             # first sermon page index; earlier pages are front matter

def is_verse_line(t):
    """A real verse line: indented running text, not a stray page number/header/footnote."""
    letters = sum(c.isalpha() for c in t)
    digits  = sum(c.isdigit() for c in t)
    if letters < 3 or digits > letters or len(t) < 4:
        return False
    if FN_START.match(t):                       # footnote def, not verse
        return False
    if ' ' not in t and not any(c.islower() for c in t):   # e.g. CIV, LII, IOI
        return False
    return True

PREFIXES = {'self','non','anti','pre','re','co','ex','well','half','over',
            'under','sub','super','semi','un','god'}

def is_margin_noise(text, y):
    t = text.strip().strip('.•·-—* ')
    if not t:
        return True
    if (y > 0.93 or y < 0.085) and re.fullmatch(r'[0-9ivxlcdmIVXLCDM]{1,6}', t):
        return True
    return False

def dehyphenate_join(acc, line):
    if not acc:
        return line
    if acc.endswith('-') and not acc.endswith('--'):
        prev = acc[:-1]
        if prev and prev[-1].isalpha() and line[:1].islower():
            frag = re.split(r'[^A-Za-z]', prev)[-1].lower()
            return acc + line if frag in PREFIXES else prev + line
    return acc + ' ' + line

def group_paragraphs(lines):
    """Body lines sorted top->bottom -> list of {'text','indented'}."""
    if not lines:
        return []
    ys = [l['y'] for l in lines]
    gaps = sorted(g for g in (ys[i]-ys[i+1] for i in range(len(ys)-1)) if g > 0)
    thresh = (gaps[len(gaps)//2] if gaps else 0.02) * 1.7
    out, cur, cur_ind = [], "", False
    prev_y = prev_x = None
    for l in lines:
        t = l['text'].strip()
        if not t:
            continue
        indent = prev_x is not None and (l['x'] - prev_x > INDENT)
        biggap = prev_y is not None and (prev_y - l['y'] > thresh)
        if cur and (indent or biggap):
            out.append({'text': cur, 'indented': cur_ind})
            cur, cur_ind = t, bool(indent)
        elif not cur:
            cur, cur_ind = t, False
        else:
            cur = dehyphenate_join(cur, t)
        prev_y, prev_x = l['y'], l['x']
    if cur:
        out.append({'text': cur, 'indented': cur_ind})
    return out

def clean(p):
    p = re.sub(r'\s+', ' ', p).strip()
    for a, b in [('“','"'),('”','"'),('’',"'"),('‘',"'")]:
        p = p.replace(a, b)
    return p

def strip_heading_lines(lines, has_ref):
    i, date_txt = 0, None
    while i < len(lines):
        l = lines[i]; t = l['text'].strip()
        if l['x'] > 0.20 and MONTH.match(t):
            date_txt = t; i += 1; continue
        if has_ref and l['x'] > 0.20 and i < 3 and REFLIKE.search(t) and len(t) < 45:
            i += 1; continue
        break
    return lines[i:], date_txt

# ---- assembly ----
structure = []            # ('h2',title,date) | ('section',num) | ('p',txt) | ('verse',[lines])
footnotes = []            # (id, html_text) emitted at document end
last_para_idx = None
fn_counter = 0

for f in files:
    d = json.load(open(f))
    pg = d['page']
    if pg in SKIP_PAGES:
        continue
    lines = [l for l in d['lines'] if not is_margin_noise(l['text'], l['y'])]
    lines.sort(key=lambda l: -l['y'])
    if not lines:
        continue

    # page geometry from long (body) lines
    longs = [l for l in lines if l['w'] > 0.5]
    body_left  = min((l['x'] for l in longs), default=min(l['x'] for l in lines))
    body_right = max((l['x']+l['w'] for l in longs), default=max(l['x']+l['w'] for l in lines))
    body_h     = statistics.median([l['h'] for l in longs]) if longs else \
                 statistics.median([l['h'] for l in lines])

    # chapter heading
    chapter = CHAPTERS.get(pg)
    date_txt = None
    if chapter:
        lines, date_txt = strip_heading_lines(lines, chapter != "Another Season of the Year")

    # locate footnote region (contiguous small-print tail beginning with a number)
    fn_start_idx = None
    for i, l in enumerate(lines):
        if l['y'] < 0.62 and l['h'] < body_h*0.9 and FN_START.match(l['text'].strip()):
            fn_start_idx = i
            break
    body_lines = lines[:fn_start_idx] if fn_start_idx is not None else lines
    fn_lines   = lines[fn_start_idx:] if fn_start_idx is not None else []

    if chapter:
        structure.append(('h2', chapter, date_txt))
        last_para_idx = None

    # walk body lines, splitting into paragraph-runs / verse / section
    page_items = []        # (kind, struct_index)
    run = []
    def flush_run():
        global last_para_idx, run, page_items
        if not run:
            return
        paras = group_paragraphs(run)
        for j, p in enumerate(paras):
            if last_para_idx is not None and j == 0 and not p['indented']:
                prev = structure[last_para_idx][1]
                if prev.endswith('-') or (not prev.rstrip().endswith(TERMINALS)
                                          and p['text'][:1].islower()):
                    structure[last_para_idx] = ('p', dehyphenate_join(prev, p['text']))
                    page_items.append(('p', last_para_idx))
                    continue
            structure.append(('p', p['text']))
            last_para_idx = len(structure) - 1
            page_items.append(('p', last_para_idx))
        run = []

    in_book = pg >= FIRST_CH
    for l in body_lines:
        t = l['text'].strip()
        x, r = l['x'], l['x'] + l['w']
        if in_book and x > 0.30 and l['w'] < 0.16 and ROMAN.fullmatch(t):
            flush_run()
            structure.append(('section', t))
            page_items.append(('section', len(structure)-1))
            last_para_idx = None
            continue
        is_verse = (in_book and x > body_left + VERSE_DX
                    and r < body_right - VERSE_DR and is_verse_line(t))
        if is_verse:
            flush_run()
            if structure and structure[-1][0] == 'verse':
                structure[-1][1].append(t)      # extend current stanza
            else:
                structure.append(('verse', [t]))
                page_items.append(('verse', len(structure)-1))
            last_para_idx = None
        else:
            run.append(l)
    flush_run()

    # footnotes: split region into individual notes; emit each in place (no data loss)
    if fn_lines:
        notes = []          # list of [number, [text lines]]
        for l in fn_lines:
            t = l['text'].strip()
            m = FN_START.match(t)
            if m:
                notes.append([m.group(1), [t[m.end():]]])
            elif notes:
                notes[-1][1].append(t)
        for num, txt_lines in notes:
            txt_lines = [clean(x) for x in txt_lines if x.strip()]
            if txt_lines:
                structure.append(('note', num, txt_lines))
        last_para_idx = None

# ---- render ----
n_h2 = n_sec = n_p = n_v = n_note = 0
with open(OUT_MD, 'w') as out:
    out.write("# This World and the Beyond — Marburg Sermons\n\n")
    out.write("*Rudolf Bultmann. OCR local (Apple Vision, en-US + de-DE).*\n\n")
    for item in structure:
        k = item[0]
        if k == 'h2':
            out.write(f"## {item[1]}\n\n")
            if item[2]:
                out.write(f"*{clean(item[2])}*\n\n")
            n_h2 += 1
        elif k == 'section':
            out.write(f"### {item[1]}\n\n")
            n_sec += 1
        elif k == 'verse':
            vlines = [clean(x) for x in item[1] if x.strip()]
            if vlines:
                out.write('\n'.join('> ' + ln + '  ' for ln in vlines).rstrip() + "\n\n")
                n_v += 1
        elif k == 'note':
            _, num, tlines = item
            first = f"**[{num}]** {tlines[0]}"
            body = [first] + tlines[1:]
            out.write('\n'.join('> ' + ln + '  ' for ln in body).rstrip() + "\n\n")
            n_note += 1
        else:
            p = clean(item[1])
            if p:
                out.write(p + "\n\n")
                n_p += 1

print(f"pages:{len(files)} chapters:{n_h2} sections:{n_sec} paragraphs:{n_p} "
      f"verse-blocks:{n_v} notes:{n_note} -> {OUT_MD}")
