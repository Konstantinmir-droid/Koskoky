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
            source = folder/'synthetic.txt'
            source.write_text('Договор № 125 от 15.10.2026\n'
                              'Исполнитель: ООО Альфа. Заказчик: ООО Бета.\n'
                              'Предмет договора: Аренда оборудования.\n'
                              'Стоимость: 1250,50 руб.\n',encoding='utf-8')
            engine = Engine(root, models[0])
            record = engine.analyze(source, raise_errors=True)
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
