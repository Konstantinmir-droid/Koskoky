"""Packaged-runtime smoke test using synthetic data only. No user documents."""
from pathlib import Path
import json
import tempfile
import traceback
from .core import validate_structure, RenameJournal, fingerprint
from .engine import Engine, disable_network
from .extract import Extractor
from .runtime import resource_root


def run(report: str) -> int:
    disable_network()
    root = resource_root()
    results = {'status':'failed', 'checks':[], 'limitations':[
        'Synthetic smoke test only; does not prove field accuracy on real documents.',
        'Python sockets denied; native traffic capture still required.',
        'Does not test old OS versions or installer interaction.'
    ]}
    engine = None
    try:
        from .privacy import enforce_offline
        enforce_offline()
        results['checks'].append('os_network_denial')
        reader = Extractor(root)
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB',(1200,500),'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=48)
        draw.text((80,80),'INVOICE 125\n2026-10-15',fill='black',font=font,spacing=30)
        text = reader.ocr(image)
        if '125' not in text:
            raise RuntimeError('Bundled OCR failed synthetic invoice')
        results['checks'].append('bundled_ocr')
        models = sorted((root/'models').glob('*.gguf'))
        if not models:
            raise RuntimeError('Bundled model missing')
        with tempfile.TemporaryDirectory(prefix='localdoc-selftest-') as tmp:
            folder = Path(tmp)
            # Exercise dynamically imported readers inside the frozen executable.
            import fitz
            import zipfile
            from openpyxl import Workbook
            pdf = folder/'synthetic.pdf'
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((50,50), 'Contract 125. Alpha LLC. Date 2026-10-15. Synthetic test document.')
                document.save(pdf)
            if 'Contract 125' not in reader.read(pdf):
                raise RuntimeError('Bundled PDF reader failed')
            office = folder/'synthetic.docx'
            with zipfile.ZipFile(office,'w') as archive:
                archive.writestr('word/document.xml',
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:body><w:p><w:r><w:t>Contract 125</w:t></w:r></w:p></w:body></w:document>')
            if 'Contract 125' not in reader.read(office):
                raise RuntimeError('Bundled DOCX reader failed')
            spreadsheet = folder/'synthetic.xlsx'
            book = Workbook()
            book.active.append(['Contract',125])
            book.save(spreadsheet)
            book.close()
            if 'Contract\t125' not in reader.read(spreadsheet):
                raise RuntimeError('Bundled XLSX reader failed')
            picture = folder/'synthetic.jpg'
            image.save(picture)
            if '125' not in reader.read(picture):
                raise RuntimeError('Bundled image reader failed')
            scan = folder/'synthetic-scan.pdf'
            import io
            image_bytes = io.BytesIO()
            image.save(image_bytes,format='PNG')
            with fitz.open() as document:
                page = document.new_page(width=600,height=250)
                page.insert_image(page.rect,stream=image_bytes.getvalue())
                document.save(scan)
            if '125' not in reader.read(scan):
                raise RuntimeError('Bundled scanned PDF OCR failed')
            results['checks'].append('bundled_pdf_docx_xlsx_image_scanned_pdf')
            source = folder/'synthetic.txt'
            source.write_text('Договор № 125 от 15.10.2026\n'
                              'Исполнитель: ООО Альфа. Заказчик: ООО Бета.\n'
                              'Предмет договора: Аренда оборудования.\n'
                              'Стоимость: 1250,50 руб.\n',encoding='utf-8')
            engine = Engine(root, models[0])
            results['synthetic_model'] = {}
            record = engine.analyze(source, raise_errors=True, diagnostics=results['synthetic_model'])
            results['synthetic_model']['verified'] = record.data
            results['synthetic_model']['issues'] = record.issues
            if record.error:
                raise RuntimeError(record.error)
            validate_structure(record.data)
            if record.data['document_number'] != '125' or record.data['document_date'] != '2026-10-15':
                raise RuntimeError('Qwen failed synthetic number/date check')
            if not record.suggested_filename:
                raise RuntimeError('Qwen failed mandatory fields check')
            results['checks'].append('bundled_qwen_schema_and_fields')
            record.approved = True
            journal = RenameJournal(folder/'journal.sqlite3')
            digest = fingerprint(source)
            try:
                target = journal.apply(record)
                if fingerprint(target) != digest:
                    raise RuntimeError('Rename changed bytes')
                count, errors = journal.undo_all()
                if count != 1 or errors or fingerprint(source) != digest:
                    raise RuntimeError('Undo failed')
            finally:
                journal.db.close()
            results['checks'].append('rename_and_undo')
        results['status'] = 'passed'
    except Exception as exc:
        results['error'] = type(exc).__name__ + ': ' + str(exc)
        results['synthetic_test_traceback'] = traceback.format_exc()
    finally:
        if engine is not None:
            engine.close()
        Path(report).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if results['status'] == 'passed' else 1
