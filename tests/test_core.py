import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from localdoc.core import (FIELDS, SCHEMA, Record, RenameJournal, DocumentError, clean_component,
                           fingerprint, suggested_name, validate_filename, validate_structure, verify_evidence, local_path)
from localdoc.extract import Extractor


def sample():
    data = {k: None for k in FIELDS}
    data.update(document_type='Договор', organization='ООО Альфа', document_number='125', document_date='2026-10-15')
    data['evidence'] = {k: data[k] for k in FIELDS}
    data['evidence']['document_date'] = '15.10.2026'
    return data


class SchemaTests(unittest.TestCase):
    def test_valid(self):
        validate_structure(sample())
    def test_bad_date(self):
        for value in ['2026-02-30', '15.10.2026', '2026-1-1']:
            with self.subTest(value=value), self.assertRaises((DocumentError, ValueError)):
                data = sample(); data['document_date'] = value; validate_structure(data)
    def test_extra_or_missing_or_bad_type(self):
        for edit in [lambda d: d.update(extra='x'), lambda d: d.pop('organization'), lambda d: d.update(amount=1.25),
                     lambda d: d.update(currency='XYZ'), lambda d: d['evidence'].pop('inn')]:
            data = sample(); edit(data)
            with self.assertRaises(DocumentError): validate_structure(data)
    def test_hallucination_is_null(self):
        data = sample()
        data['inn'], data['evidence']['inn'] = '7707083893', 'ИНН 7707083893'
        result, issues = verify_evidence(data, 'Договор 125 от 15.10.2026 ООО Альфа')
        self.assertIsNone(result['inn']); self.assertTrue(issues)
        self.assertEqual(result['organization'], 'ООО Альфа')
        self.assertEqual(result['document_date'], '2026-10-15')
    def test_existing_quote_cannot_justify_wrong_value(self):
        data = sample(); data['organization'] = 'ООО Бета'; data['evidence']['organization'] = 'ООО Альфа'
        result, _ = verify_evidence(data, 'Договор 125 от 15.10.2026 ООО Альфа')
        self.assertIsNone(result['organization'])
    def test_amount_and_currency(self):
        data = sample(); data.update(amount='1250.50', currency='RUB')
        data['evidence'].update(amount='1 250,50 руб.', currency='1 250,50 руб.')
        result, _ = verify_evidence(data, 'Договор 125 от 15.10.2026 ООО Альфа. Итого 1 250,50 руб.')
        self.assertEqual(result['amount'], '1250.50'); self.assertEqual(result['currency'], 'RUB')
    def test_bad_inn_rejected(self):
        data = sample(); data['inn'] = '1234567890'; data['evidence']['inn'] = '1234567890'
        result, _ = verify_evidence(data, '1234567890')
        self.assertIsNone(result['inn'])
    def test_canonical_values_get_literal_source_evidence(self):
        data = sample(); data.update(amount='1250.50', currency='RUB')
        data['evidence'].update(document_date='2026-10-15', amount='1250.50', currency='RUB')
        text = 'Договор 125 от 15.10.2026 ООО Альфа. Стоимость: 1250,50 руб.'
        result, _ = verify_evidence(data, text)
        self.assertEqual(result['document_date'], '2026-10-15')
        self.assertEqual(result['amount'], '1250.50')
        self.assertEqual(result['currency'], 'RUB')
        for key in ('document_date','amount','currency'):
            self.assertIn(result['evidence'][key], text)
    def test_canonical_evidence_cannot_create_absent_values(self):
        data = sample(); data.update(document_date='2027-10-15', amount='9999.00', currency='USD')
        data['evidence'].update(document_date='2027-10-15', amount='9999.00', currency='USD')
        result, _ = verify_evidence(data, 'Договор 125 от 15.10.2026 ООО Альфа. Стоимость: 1250,50 руб.')
        for key in ('document_date','amount','currency'):
            self.assertIsNone(result[key]); self.assertIsNone(result['evidence'][key])
    def test_mixed_zero_padding_in_complete_date(self):
        data = sample(); data['document_date']='2026-01-05'; data['evidence']['document_date']='2026-01-05'
        result, _ = verify_evidence(data, 'Договор 125 ООО Альфа от 5.01.2026')
        self.assertEqual(result['evidence']['document_date'], '5.01.2026')
    def test_amount_recovery_cannot_use_a_year(self):
        data = sample(); data['amount']='2026.00'; data['evidence']['amount']='2026.00'
        result, _ = verify_evidence(data, 'Договор 125 ООО Альфа от 15.10.2026')
        self.assertIsNone(result['amount'])


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.src = self.root/'scan.PDF'
        self.src.write_bytes(b'original bytes')
        self.journal = RenameJournal(self.root/'journal.db')
        self.record = Record(str(self.src), fingerprint(self.src), sample(), approved=True)
        self.record.suggested_filename = suggested_name(self.record.data, self.src)
    def tearDown(self):
        self.journal.db.close(); self.temp.cleanup()
    def test_apply_undo_roundtrip(self):
        target = self.journal.apply(self.record)
        self.assertFalse(self.src.exists()); self.assertTrue(target.exists()); self.assertEqual(target.suffix, '.PDF')
        self.assertEqual(self.journal.undo_all(), (1, []))
        self.assertEqual(self.src.read_bytes(), b'original bytes'); self.assertFalse(target.exists())
        self.assertEqual(self.journal.undo_all(), (0, []))
    def test_conflict_no_overwrite(self):
        target = self.src.with_name(self.record.suggested_filename)
        target.write_bytes(b'existing')
        with self.assertRaises(DocumentError): self.journal.apply(self.record)
        self.assertEqual(target.read_bytes(), b'existing'); self.assertTrue(self.src.exists())
    def test_changed_file_blocked(self):
        self.src.write_bytes(b'changed')
        with self.assertRaises(DocumentError): self.journal.apply(self.record)
        self.assertTrue(self.src.exists())
    def test_approval_and_errors_block(self):
        self.record.approved = False
        with self.assertRaises(DocumentError): self.journal.apply(self.record)
        self.record.approved = True; self.record.error = 'OCR failed'
        with self.assertRaises(DocumentError): self.journal.apply(self.record)
    def test_missing_required_field_blocks(self):
        self.record.data['document_date'] = None
        with self.assertRaises(DocumentError): self.journal.apply(self.record)
    def test_undo_original_collision(self):
        target = self.journal.apply(self.record); self.src.write_bytes(b'another')
        count, errors = self.journal.undo_all()
        self.assertEqual(count, 0); self.assertTrue(errors)
        self.assertEqual(self.src.read_bytes(), b'another'); self.assertTrue(target.exists())
    def test_undo_modified_target(self):
        target = self.journal.apply(self.record); target.write_bytes(b'changed')
        count, errors = self.journal.undo_all()
        self.assertEqual(count, 0); self.assertTrue(errors); self.assertFalse(self.src.exists())
    def test_crash_between_link_and_unlink(self):
        target = self.src.with_name(self.record.suggested_filename)
        with patch('localdoc.core.Path.unlink', side_effect=OSError('simulated crash')):
            with self.assertRaises(OSError): self.journal.apply(self.record)
        self.assertTrue(self.src.exists()); self.assertTrue(target.exists())
        self.assertEqual(self.journal.undo_all(), (1, []))
        self.assertTrue(self.src.exists()); self.assertFalse(target.exists())
    def test_crash_before_link(self):
        with patch('localdoc.core.os.link', side_effect=OSError('unsupported filesystem')):
            with self.assertRaises(OSError): self.journal.apply(self.record)
        self.assertEqual(self.journal.undo_all(), (1, []))
        self.assertTrue(self.src.exists())
    def test_case_insensitive_conflict(self):
        self.src.with_name(self.record.suggested_filename.swapcase()).write_bytes(b'existing')
        with self.assertRaises(DocumentError): self.journal.apply(self.record)
    def test_illegal_names(self):
        for value in ['../bad.PDF','CON.PDF','aux.PDF','x?.PDF','x.pdf','a.PDF ', 'a:b.PDF']:
            with self.subTest(value=value), self.assertRaises(DocumentError): validate_filename(value, self.src)
    def test_cannot_clear_live_journal(self):
        self.journal.apply(self.record)
        with self.assertRaises(DocumentError): self.journal.clear_completed()
        self.journal.undo_all(); self.journal.clear_completed()
        self.assertEqual(self.journal.entries(), [])


class ExtractionTests(unittest.TestCase):
    def test_utf8_cp1251_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); reader = Extractor(root)
            for encoding in ['utf-8-sig','utf-16','cp1251']:
                source = root/'test.csv'; source.write_text('Договор,125\nАльфа,2026', encoding=encoding)
                self.assertIn('Договор', reader.read(source))
    def test_empty_and_oversized_text_blocked(self):
        for text in ['', ' ', 'a'*300001]:
            with self.assertRaises(DocumentError): Extractor.checked(text)
    def test_network_paths_blocked(self):
        for path in ['//server/document.pdf', '\\\\server\\document.pdf','https://host/document.pdf']:
            with self.assertRaises(DocumentError): local_path(path)
    def test_xlsx_values(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); book = Workbook(); book.active.append(['Договор', 125]); book.save(root/'test.xlsx'); book.close()
            self.assertIn('Договор\t125', Extractor(root).read(root/'test.xlsx'))
    def test_xlsx_formulas_blocked(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); book = Workbook(); book.active.append(['=1+1']); book.save(root/'test.xlsx'); book.close()
            with self.assertRaises(DocumentError): Extractor(root).read(root/'test.xlsx')
    def test_docx_no_external_fetch(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'test.docx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', '<w:document xmlns:w="urn:test"><w:p><w:t>Договор 125</w:t></w:p></w:document>')
            self.assertEqual(Extractor(root).read(path), 'Договор 125')
    def test_pdf_native_text(self):
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'test.pdf'
            with fitz.open() as book:
                page = book.new_page(); page.insert_text((50,50), 'Contract 125. Alpha LLC. Date 2026-10-15. Payment details.')
                book.save(path)
            self.assertIn('Contract 125', Extractor(root).read(path))
    def test_ocr_missing_blocks(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DocumentError): Extractor(Path(tmp)).ocr(Image.new('RGB',(100,100)))

if __name__ == '__main__': unittest.main()
