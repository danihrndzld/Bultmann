#!/bin/sh
# pages_md/ (Unlimited-OCR output) -> book.md -> EPUB. Usage: ./build_epub.sh [pages_dir] [out.epub]
set -e
cd "$(dirname "$0")"
PAGES=${1:-pages_md}
OUT=$(cd "$(dirname "${2:-../x}")" && pwd)/$(basename "${2:-This World and the Beyond - Rudolf Bultmann.epub}")

# p000-p003 are title/copyright/dedication/RSV note: hand-kept in epub/frontmatter.md
TMP=$(mktemp -d)
for f in "$PAGES"/p*.md; do case $(basename "$f") in p00[0-3].md) ;; *) cp "$f" "$TMP"/ ;; esac; done
python3 det2md.py "$TMP" > book.md
rm -r "$TMP"

cd epub
pandoc metadata.yaml frontmatter.md ../book.md -o "$OUT" \
  --toc --toc-depth=1 --split-level=1 --css=epub.css --epub-title-page=true
cd ..
echo "built: $OUT"
