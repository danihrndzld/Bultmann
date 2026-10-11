"""Unlimited-OCR `document parsing.` pages (one .md per page, sorted) -> one clean Markdown file for pandoc."""
import re, sys, glob

BLOCK = re.compile(r"<\|det\|>(\w+) \[(\d+), [^\]]*\]<\|/det\|>(.*?)(?=<\|det\|>|\Z)", re.S)
REF = re.compile(r"^(\d )?[A-Z][a-zA-Z.\s]+\d+\s*:\s*[\d\-; :]+$")   # "Acts 17: 22-32"
DATE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$")                   # "June 7, 1936"
CELL = re.compile(r"<tr><td>(.*?)</td><td>(\d+)</td></tr>")
PAGE = re.compile(r"<\|det\|>page_number [^\n]*?<\|/det\|>(\d+)")
VERSE_X = 180  # body text starts at x 40-120 (of 1000); poems/epigraphs are indented past this
SUP = re.compile(r"\\\(\s*\^\{(\w+)\}\s*\\\)")  # LaTeX "\( ^{1} \)" -> pandoc "^1^"
NOTE = re.compile(r"\^(\d+)\^\s*(.*?)(?=\^\d+\^|$)")  # "^1^ Novalis. ^2^ Hebbel."
SMALL = {"of", "the", "a", "an", "and", "to", "in"}


def nice(title):  # "“ANOTHER SEASON OF THE YEAR . . .”" -> "“Another Season of the Year . . .”"
    words = title.lower().split()
    return " ".join(w if i and w in SMALL else re.sub(r"[a-z]", lambda m: m[0].upper(), w, count=1) for i, w in enumerate(words))


def convert(pages):
    out, contents, pending, defs = [], {}, [], []

    def add(block):  # footnotes left unlinked wait here so a paragraph can still continue onto the next page
        out.extend(pending), pending.clear(), out.append(block)

    for pi, page in enumerate(pages):
        num = (PAGE.findall(page) or [None])[-1]
        blocks = [(label, int(x), SUP.sub(r"^\1^", text)) for label, x, text in BLOCK.findall(page)]
        is_note = lambda label, text: label == "page_footnote" or re.match(r"\s*\^\d+\^", text)
        notes = {n: body.strip() for label, _, text in blocks if is_note(label, text)
                 for n, body in NOTE.findall(" ".join(text.split()))}

        def link(text):  # 'life."1' / 'life.^1^' -> pandoc footnote ref, when that note is on this page
            for n in list(notes):
                text, hit = re.subn(rf"\s*\^{n}\^|(?<=[A-Za-z.,;:!?”\"’')]){n}(?![\d^])", f"[^p{pi}n{n}]", text, count=1)
                if hit:
                    defs.append(f"[^p{pi}n{n}]: {notes.pop(n)}")
            return text

        for label, x, text in blocks:
            flat = " ".join(text.split())
            if label == "table":
                contents |= {p: t for t, p in CELL.findall(text)}
            elif label == "page_number" or flat in ("CONTENTS", "Page") or is_note(label, text):
                continue  # pandoc --toc rebuilds the contents; notes handled above
            elif DATE.match(flat):  # each sermon starts with its date (title or centred text)
                if out and out[-1].startswith("#") and num in contents:
                    out.pop()  # page heading may be OCR-garbled ("20: I-I5"); the contents entry is canonical
                if num in contents:
                    add(f"# {nice(contents[num])}")
                add(f"*{flat}*")
            elif label == "text" and x > VERSE_X:
                verse = "\n".join("| " + link(l.strip()) for l in text.strip().splitlines())
                if out and out[-1][:1] == "|" and not pending and not re.match(r"[\"“‘']", text.strip()):
                    out[-1] += "\n" + verse  # same stanza; a new opening quote starts a new one
                else:
                    add(verse)
            elif label == "title":
                add(f"# {flat}" if REF.match(flat) else f"## {flat}")
            else:
                flat = link(flat)
                prose = out and out[-1][:1] not in "#*>|"
                if prose and re.search(r"[a-z]-$", out[-1]):
                    out[-1] = out[-1][:-1] + flat  # word hyphenated across a page break
                elif prose and (flat[:1].islower() or not re.search(r"[.?!:;”\"’')]$", out[-1])):
                    out[-1] += " " + flat  # paragraph continues across a page break
                else:
                    if out and out[-1].startswith("## "):  # section opens with a small-caps word: "PAUL's" / OCR'd "Ir"
                        flat = re.sub(r"^Ir\b", "It", flat)
                        flat = re.sub(r"^([A-Z])([A-Za-z]*)\b", lambda m: f"[{m[1]}{m[2].lower()}]{{.smallcaps}}", flat)
                    add(flat)
        pending.extend(f"> ^{n}^ {body}" for n, body in notes.items())  # marker not found: keep note visible
    return "\n\n".join(out + pending + defs) + "\n"


def check():
    t = lambda label, s, x=100: f"<|det|>{label} [{x}, 0, 900, 50]<|/det|>{s}\n"
    md = convert([
        t("table", "<table><tr><td>“ANOTHER SEASON OF THE YEAR . . .”</td><td>92</td></tr></table>"),
        t("title", "July 27, 1938") + t("text", "Another season\nAnother day", 300) + t("text", "Gone^{x}", 300) + t("text", r"\( ^{1} \) Günther", 300) + t("text", "the recog-") + t("page_footnote", r"\( ^{2} \) Unused.") + t("page_number", "92"),
        t("table", "<table><tr><td>ST. MATTHEW 20: 1-15</td><td>178</td></tr></table>") + t("title", "St. Matthew 20: I-I5") + t("text", "June 17, 1945", 400) + t("page_number", "178"),
        t("text", "nition of time") + t("title", "II") + t("text", "PAUL's speech, said Hebbel.1 And the poet \\( ^{2} \\) wrote") + t("page_footnote", r"\( ^{1} \) Hebbel. \( ^{2} \) Geibel.") + t("page_number", "93"),
        t("text", "more “not yet”") + t("text", "later on."),
    ])
    assert md == ("# “Another Season of the Year . . .”\n\n*July 27, 1938*\n\n| Another season\n| Another day\n| Gone^{x}\n\n"
                  "the recog-\n\n> ^1^ Günther\n\n> ^2^ Unused.\n\n# St. Matthew 20: 1-15\n\n*June 17, 1945*\n\nnition of time\n\n## II\n\n"
                  "[Paul]{.smallcaps}'s speech, said Hebbel.[^p3n1] And the poet[^p3n2] wrote more “not yet” later on.\n\n[^p3n1]: Hebbel.\n\n[^p3n2]: Geibel.\n"), md


if __name__ == "__main__":
    check()
    sys.stdout.write(convert(open(f).read() for f in sorted(glob.glob(f"{sys.argv[1]}/*.md"))))
