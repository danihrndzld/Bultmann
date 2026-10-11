# This World and the Beyond (Bultmann) → EPUB

Escaneo de *This World and the Beyond: Marburg Sermons* (Rudolf Bultmann, Scribner's, 1960; 245 páginas) convertido a EPUB 3 con OCR local en una MacBook Pro M2 Pro de 16 GB.

Resultado: `This World and the Beyond - Rudolf Bultmann.epub`. Pasa EPUBCheck con 0 errores y 0 advertencias. Trae los 21 sermones como capítulos, cada uno con su fecha; 35 de 38 notas al pie enlazadas; metadatos para Calibre (autor ordenado como "Bultmann, Rudolf", editorial, año, LCCN 60-14019, traductor Harold Knight) y portada.

## Pipeline actual: `unlimited_ocr/`

| Paso | Archivo | Qué hace |
|---|---|---|
| 1 | `bench.py` | Corre [Unlimited-OCR](https://github.com/baidu/Unlimited-OCR) (port MLX de 8 bits `sahilchachra/unlimited-ocr-8bit-mlx`) con el prompt `document parsing.`; escribe un `.md` por página en `pages_md/` con bloques etiquetados (`title`, `text`, `page_footnote`, `page_number`, `table`) |
| 2 | `det2md.py` | Convierte los bloques en `book.md`: capítulos por fecha y título del índice, versos por sangría (x > 180), une párrafos entre páginas, enlaza notas `[^pNnM]`, versalita en la primera palabra de cada sección |
| 3 | `build_epub.sh` | `book.md` + `epub/metadata.yaml` + `epub/frontmatter.md` + `epub/epub.css` + `epub/cover.jpg` → EPUB con pandoc |

Medido en la M2 Pro: 4,2 s por página, 17,5 min el libro completo, 5,44 GB de memoria pico, 0 páginas en bucle.

Para reconstruir el EPUB desde el OCR ya hecho: `unlimited_ocr/build_epub.sh` (requiere `pandoc`). `python3 unlimited_ocr/det2md.py` corre su autoprueba `check()` antes de convertir.

### Correcciones al port MLX (sin ellas el OCR repite texto en bucle)

1. `model/tokenizer.json`: el port trae un pre-tokenizer Metaspace; aquí va el original de `baidu/Unlimited-OCR` (ByteLevel).
2. `model/tokenizer_config.json`: `tokenizer_class` cambiado a `PreTrainedTokenizerFast`, porque `LlamaTokenizer` en transformers 5 reconstruye el Metaspace.
3. Prompt con espacio final (`"<image>document parsing. "`): mlx-vlm borra el último token del prompt.

Para volver a correr el OCR, enlaza los demás archivos del modelo desde la caché de Hugging Face:

```sh
cd unlimited_ocr
uvx --from huggingface_hub hf download sahilchachra/unlimited-ocr-8bit-mlx
M=$(ls -d ~/.cache/huggingface/hub/models--sahilchachra--unlimited-ocr-8bit-mlx/snapshots/*)
for f in chat_template.jinja config.json model.safetensors model.safetensors.index.json processor_config.json special_tokens_map.json; do ln -sf "$(realpath "$M/$f")" model/$f; done
uv run --python 3.12 --with mlx-vlm --with torch --with torchvision python bench.py ./model <carpeta_png> pages_md "<image>document parsing. "
```

Las páginas PNG salen del PDF con PyMuPDF a escala 0,75 (1266×2072 px). El PDF no está en el repo: pesa 129 MB.

## Pipeline anterior (Apple Vision)

`ocr_vision.swift` → `ocr_json/` → `build_markdown.py` → `bultmann_ocr.md` → `This World and the Beyond - Bultmann.epub`. Contra Unlimited-OCR tuvo de 0 a 5 diferencias de palabras por página de unas 400 palabras. Unlimited-OCR acertó en todas las que revisé: "poly theistic" → "polytheistic", "IO" → "10", "4M" → "4ff".
