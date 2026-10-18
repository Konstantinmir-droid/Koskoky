from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field

FIELDS = ('document_type', 'organization', 'document_number', 'document_date',
          'subject', 'inn', 'amount', 'currency', 'counterparty')
REQUIRED = ('document_type', 'organization', 'document_number', 'document_date')
TYPES = ('Договор', 'Дополнительное соглашение', 'Счет', 'Счет-фактура', 'Акт',
         'Накладная', 'УПД', 'Платежный документ', 'Письмо', 'Прочее')
SUPPORTED = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.jpg', '.jpeg', '.png', '.txt', '.csv'}
SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object', 'additionalProperties': False, 'required': list(FIELDS) + ['evidence'],
    'properties': {k: {'type': ['string', 'null']} for k in FIELDS},
}
SCHEMA['properties']['document_type'] = {'enum': [*TYPES, None]}
SCHEMA['properties']['document_date'] = {'anyOf': [{'type': 'string', 'format': 'date'}, {'type': 'null'}]}
SCHEMA['properties']['inn'] = {'anyOf': [{'type': 'string', 'pattern': r'^([0-9]{10}|[0-9]{12})$'}, {'type': 'null'}]}
# A character class avoids the converter emitting an invalid GBNF literal "\\.".
SCHEMA['properties']['amount'] = {'anyOf': [{'type': 'string', 'pattern': r'^[0-9]+([.][0-9]{1,2})?$'}, {'type': 'null'}]}
SCHEMA['properties']['currency'] = {'enum': ['RUB', 'USD', 'EUR', 'CNY', 'GBP', None]}
SCHEMA['properties']['evidence'] = {'type': 'object', 'additionalProperties': False,
    'required': list(FIELDS), 'properties': {k: {'type': ['string', 'null']} for k in FIELDS}}

class DocumentError(Exception):
    pass


def local_path(value: str | Path) -> Path:
    raw = str(value)
    if raw.startswith(('\\\\', '//')) or '://' in raw:
        raise DocumentError('Сетевые пути запрещены')
    path = Path(value).absolute()
    if path.is_symlink():
        raise DocumentError('Символические ссылки запрещены')
    if os.name == 'nt':
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs != -1 and attrs & 0x400:
            raise DocumentError('Точки повторной обработки Windows запрещены')
    path = path.resolve()
    if os.name == 'nt':
        import ctypes
        if str(path).startswith('\\\\') or ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
            raise DocumentError('Сетевые диски запрещены')
    if sys.platform == 'darwin':
        from .macos_volume import is_local
        try:
            if not is_local(path):
                raise DocumentError('Сетевые тома macOS запрещены')
        except OSError as exc:
            raise DocumentError('Не удалось подтвердить локальный том macOS') from exc
    return path


def walk_local(folder: Path):
    stack = [local_path(folder)]
    seen = set()
    while stack:
        directory = stack.pop()
        key = os.path.normcase(str(directory))
        if key in seen:
            continue
        seen.add(key)
        for child in directory.iterdir():
            try:
                child = local_path(child)
            except DocumentError:
                continue
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                yield child


def fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def normalized(value: str) -> str:
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip().casefold()


def validate_structure(value: dict) -> None:
    # jsonschema is deliberately imported lazily: safety tests can exercise stdlib-only code.
    from jsonschema import Draft202012Validator, FormatChecker
    errors = list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise DocumentError('JSON не соответствует схеме: ' + '; '.join('/'.join(map(str, e.path)) for e in errors))
    date = value.get('document_date')
    if date is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            raise DocumentError('Неверный формат даты')
        dt.date.fromisoformat(date)
    for key in FIELDS:
        if value[key] is not None and (not value[key].strip() or len(value[key]) > 600):
            raise DocumentError('Пустое или слишком длинное поле: ' + key)


def inn_valid(value: str) -> bool:
    digits = list(map(int, value))
    def check(weights, number):
        return sum(a*b for a, b in zip(digits, weights)) % 11 % 10 == number
    if len(digits) == 10:
        return check([2,4,10,3,5,9,4,6,8], digits[9])
    return len(digits) == 12 and check([7,2,4,10,3,5,9,4,6,8], digits[10]) and check([3,7,2,4,10,3,5,9,4,6,8], digits[11])


def date_literals(value: str, text: str):
    expected = dt.date.fromisoformat(value)
    for match in re.finditer(r'(?<![0-9])(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[./][0-9]{1,2}[./][0-9]{4})(?![0-9])', text):
        literal = match.group()
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
            try:
                if dt.datetime.strptime(literal, fmt).date() == expected:
                    yield literal
                    break
            except ValueError:
                pass


def canonical_evidence(key: str, value: str, text: str) -> str | None:
    """Recover a literal quote only for exact, reversible format conversions."""
    if key == 'document_date':
        return next(date_literals(value, text), None)
    if key == 'amount':
        from decimal import Decimal, InvalidOperation
        for match in re.finditer(r'(?<!\d)\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?(?!\d)', text):
            try:
                if Decimal(re.sub(r'\s', '', match.group()).replace(',', '.')) == Decimal(value):
                    before, after = text[:match.start()], text[match.end():]
                    if re.search(r'\d[./-]$', before) or re.match(r'[./-]\d', after):
                        continue  # Never recover an amount from a date fragment.
                    labelled = re.search(r'\b(?:итого|стоимость|сумма|всего|цена|к\s+оплате)\s*[:=]?\s*$', before, re.I)
                    money = re.match(r'(?:руб(?:\.|лей\b|ля\b|ль\b|\b)|RUB\b|₽|USD\b|US\$|доллар|EUR\b|€|евро|CNY\b|юан|GBP\b|£)', after.lstrip(), re.I)
                    if labelled or money:
                        return match.group().strip()
            except InvalidOperation:
                pass
    if key == 'currency':
        patterns = {'RUB': r'RUB|руб(?:\.|лей|ля|ль)?|₽', 'USD': r'USD|доллар США|US\$',
                    'EUR': r'EUR|€|евро', 'CNY': r'CNY|юан(?:ь|я|ей)', 'GBP': r'GBP|£'}
        pattern = patterns.get(value)
        if pattern:
            match = re.search(r'(?<![A-Za-zА-Яа-яЁё])(?:' + pattern + r')(?![A-Za-zА-Яа-яЁё])', text, re.I)
            return match.group() if match else None
    return None


def supported_value(key: str, value: str, quote: str) -> bool:
    if key == 'document_date':
        return next(date_literals(value, quote), None) is not None
    if key == 'amount':
        from decimal import Decimal, InvalidOperation
        for match in re.finditer(r'(?<!\d)\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?(?!\d)', quote):
            try:
                if Decimal(re.sub(r'\s', '', match.group()).replace(',', '.')) == Decimal(value):
                    return True
            except InvalidOperation:
                pass
        return False
    if key == 'currency':
        aliases = {'RUB': ['rub','руб','₽'], 'USD': ['usd','доллар сша','us$'],
                   'EUR': ['eur','€','евро'], 'CNY': ['cny','юан'], 'GBP': ['gbp','£']}
        return any(x in quote.casefold() for x in aliases.get(value, []))
    if key == 'document_type':
        aliases = {'Платежный документ': ['платеж','платёж','поручение','квитанция'],
                   'Прочее': [], 'Акт': ['акт'], 'Счет': ['счет','счёт'],
                   'Счет-фактура': ['счет-фактура','счёт-фактура']}
        return any(x in quote.casefold() for x in aliases.get(value, [value.casefold()]))
    return bool(re.search(r'(?<!\w)' + re.escape(normalized(value)) + r'(?!\w)', normalized(quote)))


def verify_evidence(value: dict, text: str) -> tuple[dict, list[str]]:
    validate_structure(value)
    value = json.loads(json.dumps(value))
    issues = []
    for key in FIELDS:
        item, quote = value[key], value['evidence'][key]
        if item is None:
            value['evidence'][key] = None
            continue
        # Some models repeat the canonical value instead of quoting its source form.
        # Recover only exact date/decimal/currency equivalents, never arbitrary text.
        if quote and normalized(quote) == normalized(item) and normalized(quote) not in normalized(text):
            literal = canonical_evidence(key, item, text)
            if literal is not None:
                quote = value['evidence'][key] = literal
                issues.append('Цитата восстановлена по исходному формату: ' + key)
        if (not quote or normalized(quote) not in normalized(text)
                or not supported_value(key, item, quote)
                or (key == 'inn' and not inn_valid(item))):
            value[key] = None
            value['evidence'][key] = None
            issues.append('Нет надежного подтверждения: ' + key)
    return value, issues


def clean_component(value: str) -> str:
    value = unicodedata.normalize('NFKC', value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value)
    value = re.sub(r'\s+', '_', value).strip(' ._')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        value = '_' + value
    return value or 'Без_названия'


def suggested_name(data: dict, source: Path) -> str | None:
    if any(not data.get(k) for k in REQUIRED):
        return None
    parts = [clean_component(str(data[k]))[:70] for k in ('document_date','document_type','document_number','organization')]
    budget = min(220, 245 - len(str(source.parent))) - len(source.suffix)
    if budget < 30:
        raise DocumentError('Слишком длинный путь. Переместите файл ближе к корню диска')
    return '_'.join(parts)[:budget].rstrip(' .') + source.suffix


def validate_filename(name: str, source: Path) -> None:
    if not name or name in ('.', '..') or Path(name).name != name:
        raise DocumentError('Нужно имя файла без пути')
    if re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name) or name.endswith((' ', '.')):
        raise DocumentError('Недопустимое имя Windows')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I):
        raise DocumentError('Зарезервированное имя Windows')
    if Path(name).suffix != source.suffix:
        raise DocumentError('Исходное расширение должно сохраняться без изменений')
    if len(str(source.with_name(name)).encode('utf-16-le')) // 2 > 245:
        raise DocumentError('Слишком длинный путь')


@dataclass
class Record:
    source: str
    digest: str = ''
    data: dict = field(default_factory=dict)
    suggested_filename: str = ''
    issues: list[str] = field(default_factory=list)
    error: str | None = None
    approved: bool = False
    text: str = ''
    renamed: bool = False

    def export(self):
        return {'source': self.source, 'sha256': self.digest, **{k: self.data.get(k) for k in FIELDS},
                'evidence': self.data.get('evidence', {}), 'suggested_filename': self.suggested_filename or None,
                'review_required': [k for k in FIELDS if self.data.get(k) is None],
                'warnings': self.issues, 'error': self.error, 'approved': self.approved, 'renamed': self.renamed}


class RenameJournal:
    """Write-ahead journal. No replace/overwrite. One durable transaction per file."""
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS renames (id INTEGER PRIMARY KEY, source TEXT, target TEXT, digest TEXT, state TEXT)')
        self.db.commit()

    def apply(self, record: Record) -> Path:
        if record.error or not record.approved or record.renamed:
            raise DocumentError('Нужна проверка без критических ошибок')
        validate_structure(record.data)
        if any(not record.data.get(k) for k in REQUIRED):
            raise DocumentError('Заполните дату, тип, номер и организацию')
        src = local_path(record.source)
        if not src.is_file() or fingerprint(src) != record.digest:
            raise DocumentError('Исходный файл изменился после анализа')
        validate_filename(record.suggested_filename, src)
        dst = src.with_name(record.suggested_filename)
        if dst == src:
            raise DocumentError('Имя уже совпадает')
        if any(p.name.casefold() == dst.name.casefold() for p in src.parent.iterdir()):
            raise DocumentError('Имя уже занято. Исправьте предложенное имя')
        row = self.db.execute('INSERT INTO renames(source,target,digest,state) VALUES(?,?,?,?)',
                              (str(src), str(dst), record.digest, 'prepared')).lastrowid
        self.db.commit()
        # link refuses to replace an existing target, including races after the check.
        # Refuse unsupported filesystems rather than falling back to overwrite-prone operations.
        os.link(src, dst)
        try:
            if fingerprint(dst) != record.digest:
                raise DocumentError('Файл изменился во время переименования')
            if not os.path.samefile(src, dst):
                raise DocumentError('Исходный путь изменился во время операции')
            src.unlink()
        except BaseException:
            # Keep the durable prepared entry for safe recovery/undo.
            raise
        self.db.execute('UPDATE renames SET state=? WHERE id=?', ('applied', row))
        self.db.commit()
        record.source, record.renamed = str(dst), True
        return dst

    def undo_all(self) -> tuple[int, list[str]]:
        count, errors = 0, []
        rows = self.db.execute("SELECT id,source,target,digest,state FROM renames WHERE state != 'undone' ORDER BY id DESC").fetchall()
        for row, source, target, digest, state in rows:
            try:
                src, dst = local_path(source), local_path(target)
                if src.exists() and dst.exists():
                    if not os.path.samefile(src, dst) or fingerprint(src) != digest:
                        raise DocumentError('Исходное имя занято или содержимое изменено')
                    dst.unlink()  # interrupted link/unlink; original still intact
                elif dst.exists():
                    if fingerprint(dst) != digest:
                        raise DocumentError('Переименованный файл изменен')
                    os.link(dst, src)
                    dst.unlink()
                elif src.exists() and state == 'prepared' and fingerprint(src) == digest:
                    pass
                else:
                    raise DocumentError('Не найден ожидаемый файл')
                self.db.execute('UPDATE renames SET state=? WHERE id=?', ('undone', row))
                self.db.commit()
                count += 1
            except Exception as exc:
                errors.append(f'Запись {row}: {exc}')
        return count, errors

    def entries(self):
        return self.db.execute('SELECT id,source,target,state FROM renames ORDER BY id DESC').fetchall()

    def clear_completed(self):
        if self.db.execute("SELECT COUNT(*) FROM renames WHERE state != 'undone'").fetchone()[0]:
            raise DocumentError('Сначала отмените переименования: журнал нужен для восстановления')
        self.db.execute('DELETE FROM renames')
        self.db.commit()
        self.db.execute('VACUUM')
