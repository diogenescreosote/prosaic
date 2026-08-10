# processed_files/ — canonical raw bytes for triaged inbox material

New material lands in `../inbox/`, is triaged into `../assets/`
(literate snake_case rename, OCR-supplement, `.txt` sidecar, INDEX.md
row), and the original file, byte-for-byte and under its assets name,
moves here. Where the assets copy is an unedited byte-copy, prefer a
relative symlink into this directory; derived artifacts (`_ocr` PDFs,
sidecars, redactions) stay real files in `assets/`.

## Contents

(empty)
