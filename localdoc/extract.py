from __future__ import annotations
import io
import os
from pathlib import Path
import subprocess
from .core import DocumentError, local_path
from .runtime import native_tool

MAX_BYTES = 150 * 1024 * 1024
MAX_CHARS = 300_000
MAX_PAGES = 200


def child_run(args, *, data=None, timeout=120):
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout,
                            creationflags=flags, shell=False)
    if result.returncode:
        # Native stderr may contain document text: never copy it into logs/errors.
        raise DocumentError('Ошибка локального обработчика: ' + Path(args[0]).name)
    return result.stdout


class Extractor:
    def __init__(self, root: Path):
        self.root = root
        self.tesseract = native_tool(root, 'tesseract')
        self.antiword = native_tool(root, 'antiword')

    def ocr(self, image) -> str:
        from PIL import ImageOps
        if not self.tesseract.is_file():
            raise DocumentError('В комплекте отсутствует Tesseract OCR')
        if image.width * image.height > 60_000_000:
            raise DocumentError('Слишком большое изображение')
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((5000, 5000))
        output = io.BytesIO()
        image.save(output, format='PNG')
        text = child_run([str(self.tesseract), 'stdin', 'stdout', '--tessdata-dir',
                          str(self.root / 'vendor/tesseract/tessdata'), '-l', 'rus+eng', '--psm', '3'],
                         data=output.getvalue()).decode('utf-8', errors='strict')
        if len(text.strip()) < 3:
            raise DocumentError('OCR не обнаружил читаемый текст')
        return text

    def read(self, value: Path) -> str:
        path = local_path(value)
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise DocumentError('Файл отсутствует или превышает 150 МБ')
        ext = path.suffix.lower()
        if ext in ('.txt', '.csv'):
            raw = path.read_bytes()
            encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp1251')
            for encoding in encodings:
                try:
                    text = raw.decode(encoding)
                    if '\x00' in text:
                        continue
                    return self.checked(text)
                except UnicodeError:
                    pass
            raise DocumentError('Не удалось определить кодировку')
        if ext in ('.png', '.jpg', '.jpeg'):
            from PIL import Image
            with Image.open(path) as image:
                return self.checked(self.ocr(image))
        if ext == '.pdf':
            import fitz
            from PIL import Image
            parts = []
            with fitz.open(path) as doc:
                if doc.needs_pass:
                    raise DocumentError('PDF защищен паролем')
                if len(doc) > MAX_PAGES:
                    raise DocumentError('PDF превышает 200 страниц; частичный анализ запрещен')
                for i, page in enumerate(doc):
                    text = page.get_text('text')
                    # OCR pages with substantial embedded images too: mixed text + scanned pages.
                    image_area = sum(abs(fitz.Rect(info['bbox']).get_area()) for info in page.get_image_info())
                    needs_ocr = len(text.strip()) < 40 or image_area > page.rect.get_area() * .10
                    if needs_ocr:
                        scale = min(3, 5000 / max(page.rect.width, page.rect.height))
                        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                        image = Image.open(io.BytesIO(pix.tobytes('png')))
                        try:
                            ocr_text = self.ocr(image)
                        finally:
                            image.close()
                        text = text + '\n' + ocr_text
                    if len(text.strip()) < 3:
                        raise DocumentError(f'Нет читаемого текста на странице {i+1}')
                    parts.append(f'\n[Страница {i+1}]\n{text}')
                    self.checked('\n'.join(parts))
            return self.checked('\n'.join(parts))
        if ext == '.docx':
            # Never open Office automation, execute macros or resolve external relationships.
            import zipfile
            import xml.etree.ElementTree as ET
            from PIL import Image
            pieces = []
            with zipfile.ZipFile(path) as archive:
                if sum(info.file_size for info in archive.infolist()) > 300 * 1024 * 1024:
                    raise DocumentError('Слишком большой распакованный DOCX')
                names = archive.namelist()
                texts = [n for n in names if n == 'word/document.xml' or
                         (n.startswith(('word/header', 'word/footer', 'word/footnotes', 'word/endnotes')) and n.endswith('.xml'))]
                for name in texts:
                    root = ET.fromstring(archive.read(name))
                    pieces.append('\n'.join(''.join(n.itertext()) for n in root.iter()
                                            if n.tag.endswith('}t')))
                for name in names:
                    if name.startswith('word/media/') and Path(name).suffix.lower() in ('.png','.jpg','.jpeg'):
                        with Image.open(io.BytesIO(archive.read(name))) as image:
                            if image.width > 500 and image.height > 500:
                                pieces.append(self.ocr(image))
            return self.checked('\n'.join(pieces))
        if ext == '.doc':
            if not self.antiword.is_file():
                raise DocumentError('В комплекте отсутствует antiword для DOC')
            # The bundled UTF-8 mapping file must accompany antiword.
            text = child_run([str(self.antiword), '-m', str(self.root / 'vendor/antiword/UTF-8.txt'), str(path)])
            return self.checked(text.decode('utf-8', errors='strict'))
        if ext in ('.xlsx', '.xls'):
            return self.checked(self.spreadsheet(path))
        raise DocumentError('Формат не поддерживается')

    @staticmethod
    def checked(text):
        if not text.strip():
            raise DocumentError('Документ не содержит читаемого текста')
        if len(text) > MAX_CHARS:
            raise DocumentError('Документ превышает 300 000 символов; обрезка запрещена')
        return text

    def spreadsheet(self, path):
        import datetime
        parts = []
        count = 0
        def append_row(row):
            nonlocal count
            count += 1
            if count > 50_000:
                raise DocumentError('Превышен лимит 50 000 строк')
            parts.append('\t'.join(str(v) if v is not None else '' for v in row))
            if count % 500 == 0:
                self.checked('\n'.join(parts))
        if path.suffix.lower() == '.xlsx':
            import openpyxl
            import zipfile
            with zipfile.ZipFile(path) as archive:
                if sum(x.file_size for x in archive.infolist()) > 300*1024*1024:
                    raise DocumentError('Слишком большая распакованная книга')
                if any(n.startswith('xl/media/') for n in archive.namelist()):
                    raise DocumentError('Книга содержит изображения. Требуется отдельная проверка изображений')
            book = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)
            try:
                for sheet in book:
                    parts.append('[Лист ' + sheet.title + ']')
                    for row in sheet.iter_rows(values_only=True):
                        if any(isinstance(v, str) and v.startswith('=') for v in row):
                            raise DocumentError('Есть формулы: сохраните проверенную копию книги как значения')
                        append_row(row)
            finally:
                book.close()
        else:
            import xlrd
            book = xlrd.open_workbook(str(path), on_demand=True)
            try:
                for sheet in book.sheets():
                    parts.append('[Лист ' + sheet.name + ']')
                    for index in range(sheet.nrows):
                        row = []
                        for cell in sheet.row(index):
                            if cell.ctype == xlrd.XL_CELL_DATE:
                                row.append(xlrd.xldate_as_datetime(cell.value, book.datemode).isoformat())
                            elif cell.ctype == xlrd.XL_CELL_ERROR:
                                raise DocumentError('Ошибка в ячейке XLS')
                            else:
                                row.append(cell.value)
                        append_row(row)
            finally:
                book.release_resources()
        return '\n'.join(parts)
