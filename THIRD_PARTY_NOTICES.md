# Third-party release checklist

This source archive contains no third-party model, OCR binary or antiword binary.
A distributor must identify exact versions and include their required license notices,
attribution, and corresponding sources/offers where applicable. This list is not
legal clearance for an assembled commercial package.

- Qwen3: use the license shipped with the exact GGUF repository/revision.
- llama.cpp and llama-cpp-python: include exact bundled revisions and MIT notices.
- PySide6 / Qt: LGPL/GPL/commercial licensing; assess the chosen distribution route
  and preserve the required replacement/debugging rights and notices.
- PyMuPDF / MuPDF: AGPL/commercial licensing. Do not distribute a closed-source
  product using this stack without selecting an appropriate license arrangement.
- antiword: check GPL obligations of the exact Windows distribution and accompanying DLLs.
- Tesseract, Leptonica and language data: preserve licenses of each shipped component.
- Python, Pillow, openpyxl, xlrd, jsonschema, PyInstaller and all transitive libraries:
  preserve their own license texts and notices.

Before release, populate vendor/licenses/CONTENTS.txt and include actual license files.
The preflight checks existence only. They do not perform a legal audit.
