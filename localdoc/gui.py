from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
from .qt_compat import (Qt, QThread, Signal, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QPlainTextEdit, QLabel, QComboBox, QCheckBox, QProgressBar)
from .core import (FIELDS, SUPPORTED, TYPES, REQUIRED, Record, RenameJournal, DocumentError,
                   local_path, suggested_name, validate_filename, validate_structure, walk_local)
from .engine import Engine, disable_network
from .runtime import resource_root, state_directory

LABELS = {'document_type':'Тип', 'organization':'Организация / ФИО', 'document_number':'Номер',
    'document_date':'Дата YYYY-MM-DD', 'subject':'Тема', 'inn':'ИНН', 'amount':'Сумма, например 1250.50',
    'currency':'Валюта RUB / USD / EUR / CNY / GBP', 'counterparty':'Контрагент'}


def app_root():
    return resource_root()


def state_root(root):
    base = state_directory(root)
    base = local_path(base)
    base.mkdir(parents=True, exist_ok=True)
    return base


class Worker(QThread):
    result = Signal(object)
    status = Signal(str)
    failed = Signal(str)
    def __init__(self, root, model, paths):
        super().__init__()
        self.root, self.model, self.paths = root, model, paths
    def run(self):
        engine = None
        try:
            self.status.emit('Загрузка локальной модели…')
            engine = Engine(self.root, self.model)
            for i, path in enumerate(self.paths):
                if self.isInterruptionRequested():
                    break
                self.status.emit(f'Обработка {i+1} из {len(self.paths)}')
                self.result.emit(engine.analyze(path, self.isInterruptionRequested))
        except Exception as exc:
            self.failed.emit(str(exc) if isinstance(exc, DocumentError) else 'Не удалось запустить модель: ' + type(exc).__name__)
        finally:
            if engine is not None:
                engine.close()


class Editor(QDialog):
    def __init__(self, record: Record, parent):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle('Проверка реквизитов')
        self.resize(1000, 740)
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel(Path(record.source).name))
        columns = QHBoxLayout()
        outer.addLayout(columns)
        form = QFormLayout()
        self.inputs = {}
        for key in FIELDS:
            if key == 'document_type':
                edit = QComboBox()
                edit.addItems(['', *TYPES])
                edit.setCurrentText(record.data.get(key) or '')
            else:
                edit = QLineEdit(record.data.get(key) or '')
                edit.setMaxLength(600)
            self.inputs[key] = edit
            form.addRow(LABELS[key], edit)
        self.name = QLineEdit(record.suggested_filename)
        form.addRow('Имя файла', self.name)
        generate = QPushButton('Сформировать имя из полей')
        generate.clicked.connect(self.make_name)
        form.addRow(generate)
        self.confirm = QCheckBox('Я сверил(а) реквизиты и имя с оригиналом')
        form.addRow(self.confirm)
        columns.addLayout(form)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(record.text)
        text.setPlaceholderText('Текст доступен после анализа')
        columns.addWidget(text, 1)
        notices = QPlainTextEdit()
        notices.setReadOnly(True)
        notices.setMaximumHeight(130)
        evidence = record.data.get('evidence', {})
        notices.setPlainText('\n'.join(([record.error] if record.error else []) + record.issues) +
            '\n\nЦитаты:\n' + '\n'.join(f'{LABELS[k]}: {evidence.get(k) or "нет"}' for k in FIELDS))
        outer.addWidget(notices)
        actions = QHBoxLayout()
        save, cancel = QPushButton('Сохранить проверку'), QPushButton('Закрыть')
        save.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        actions.addWidget(save)
        actions.addWidget(cancel)
        outer.addLayout(actions)
        if record.error or record.renamed:
            save.setEnabled(False)

    def values(self):
        result = {key: ((widget.currentText() if isinstance(widget, QComboBox) else widget.text()).strip() or None)
                  for key, widget in self.inputs.items()}
        result['evidence'] = dict(self.record.data.get('evidence', {k: None for k in FIELDS}))
        for key in FIELDS:
            if result[key] != self.record.data.get(key):
                result['evidence'][key] = None  # Manual corrections are never passed off as model citations.
        return result

    def make_name(self):
        try:
            self.name.setText(suggested_name(self.values(), Path(self.record.source)) or '')
        except Exception as exc:
            QMessageBox.warning(self, 'Имя', str(exc))

    def save(self):
        try:
            data = self.values()
            validate_structure(data)
            if self.confirm.isChecked():
                if any(not data[k] for k in REQUIRED):
                    raise DocumentError('Для переименования нужны дата, тип, номер и организация')
                validate_filename(self.name.text(), Path(self.record.source))
            self.record.data = data
            self.record.suggested_filename = self.name.text()
            self.record.approved = self.confirm.isChecked()
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, 'Проверка', str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = app_root()
        self.state = state_root(self.root)
        self.journal = RenameJournal(self.state / 'renames.sqlite3')
        self.records = []
        self.worker = None
        self.setWindowTitle('Локальные документы · анализ и безопасное переименование')
        self.resize(1250, 780)
        self.setAcceptDrops(True)
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)
        note = QLabel('Обработка на этом компьютере. Перетащите файлы или папку. Перед переименованием откройте строку и подтвердите реквизиты.')
        note.setWordWrap(True)
        layout.addWidget(note)
        modelbar = QHBoxLayout()
        modelbar.addWidget(QLabel('Модель Qwen3 GGUF:'))
        self.model = QLineEdit()
        config = self.state / 'settings.json'
        try:
            self.model.setText(json.loads(config.read_text('utf-8'))['model'])
        except (OSError, ValueError, KeyError):
            models = sorted((self.root / 'models').glob('*.gguf'))
            if models:
                self.model.setText(str(models[0]))
        modelbar.addWidget(self.model)
        choose = QPushButton('Выбрать…')
        choose.clicked.connect(self.select_model)
        modelbar.addWidget(choose)
        layout.addLayout(modelbar)
        buttonrows = [QHBoxLayout(), QHBoxLayout()]
        actions = [('Файлы', self.add_files), ('Папка', self.add_folder), ('Анализировать', self.analyze),
                   ('Проверить', self.edit), ('Переименовать проверенные', self.rename),
                   ('Отменить переименования', self.undo), ('Экспорт JSON', lambda: self.export('json')),
                   ('Экспорт XLSX', lambda: self.export('xlsx')), ('Журнал', self.logs), ('Очистить список', self.clear)]
        self.buttons = []
        for index, (title, callback) in enumerate(actions):
            button = QPushButton(title)
            button.clicked.connect(callback)
            self.buttons.append(button)
            buttonrows[index // 5].addWidget(button)
        for row in buttonrows:
            layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Исходное / текущее имя', 'Предложенное имя', 'Состояние', 'Проверка'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self.edit())
        self.table.setColumnWidth(0, 320)
        self.table.setColumnWidth(1, 430)
        self.table.setColumnWidth(2, 200)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.cancel = QPushButton('Остановить после текущего фрагмента')
        self.cancel.clicked.connect(lambda: self.worker.requestInterruption() if self.worker else None)
        self.cancel.setVisible(False)
        bottom.addWidget(self.progress)
        bottom.addWidget(self.cancel)
        layout.addLayout(bottom)
        self.statusBar().showMessage('Готово. Сначала выберите модель и документы')
        pending = [x for x in self.journal.entries() if x[3] == 'prepared']
        if pending:
            self.statusBar().showMessage('Есть незавершенные операции. Нажмите «Отменить переименования» для восстановления')

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def log(self, event):
        # No document text, fields, model output or exception payloads in the processing log.
        from datetime import datetime
        path = self.state / 'processing.log'
        if path.exists() and path.stat().st_size > 2_000_000:
            path.write_text('', encoding='utf-8')
        with path.open('a', encoding='utf-8') as stream:
            stream.write(datetime.now().isoformat(timespec='seconds') + ' ' + event + '\n')

    def select_model(self):
        if self.busy():
            return
        name, _ = QFileDialog.getOpenFileName(self, 'Локальная модель Qwen3', str(self.root / 'models'), 'GGUF (*.gguf)')
        if name:
            self.model.setText(str(local_path(name)))

    def dragEnterEvent(self, event):
        if not self.busy() and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.busy():
            return
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, 'Документы', '', 'Документы (' + ' '.join('*' + x for x in sorted(SUPPORTED)) + ')')
        self.add_paths(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Папка (включая вложенные папки)')
        if folder:
            self.add_paths([folder])

    def add_paths(self, paths):
        seen = {os.path.normcase(r.source) for r in self.records}
        skipped = 0
        try:
            for value in paths:
                path = local_path(value)
                candidates = walk_local(path) if path.is_dir() else [path]
                for candidate in candidates:
                    if candidate.suffix.lower() not in SUPPORTED:
                        continue
                    candidate = local_path(candidate)
                    key = os.path.normcase(str(candidate))
                    if key not in seen and candidate.is_file():
                        if len(self.records) >= 2000:
                            raise DocumentError('Лимит очереди: 2000 файлов')
                        self.records.append(Record(str(candidate)))
                        seen.add(key)
        except Exception as exc:
            QMessageBox.warning(self, 'Добавление файлов', str(exc))
        self.refresh()

    def refresh(self):
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            status = ('Переименован' if record.renamed else 'Ошибка' if record.error else
                      'Подтвержден' if record.approved else 'Нужна проверка' if record.data else 'В очереди')
            cells = [Path(record.source).name, record.suggested_filename, status,
                     record.error or ', '.join(LABELS[k] for k in FIELDS if record.data and record.data.get(k) is None)]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setToolTip(record.source if col == 0 else value)
                self.table.setItem(row, col, item)

    def analyze(self):
        paths = [Path(r.source) for r in self.records if not r.renamed]
        if not paths or self.busy():
            return
        try:
            model = local_path(self.model.text())
            if not model.is_file():
                raise DocumentError('Выберите установленную модель GGUF')
            (self.state / 'settings.json').write_text(json.dumps({'model': str(model)}, ensure_ascii=False), encoding='utf-8')
        except Exception as exc:
            QMessageBox.warning(self, 'Модель', str(exc))
            return
        # Previous approvals cannot survive a new analysis, even if cancelled midway.
        for r in self.records:
            if not r.renamed:
                r.approved = False
                r.data, r.text, r.digest, r.suggested_filename, r.error, r.issues = {}, '', '', '', None, []
        self.refresh()
        self.worker = Worker(self.root, model, paths)
        self.worker.result.connect(self.received)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.failed.connect(lambda message: QMessageBox.warning(self, 'Анализ', message))
        self.worker.finished.connect(self.finished)
        for button in self.buttons:
            button.setEnabled(False)
        self.model.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel.show()
        self.log('ANALYSIS_START')
        self.worker.start()

    def received(self, record):
        for i, previous in enumerate(self.records):
            if previous.source == record.source:
                self.records[i] = record
                break
        self.log('FILE_ERROR' if record.error else 'FILE_ANALYZED')
        self.refresh()

    def finished(self):
        for button in self.buttons:
            button.setEnabled(True)
        self.model.setEnabled(True)
        self.progress.hide()
        self.cancel.hide()
        self.statusBar().showMessage('Обработка завершена. Откройте строки для проверки')
        self.log('ANALYSIS_STOP')

    def edit(self):
        row = self.table.currentRow()
        if row >= 0 and self.records[row].data:
            Editor(self.records[row], self).exec()
            self.refresh()
        elif row >= 0:
            QMessageBox.information(self, 'Проверка', self.records[row].error or 'Сначала выполните анализ')

    def rename(self):
        records = [r for r in self.records if r.approved and not r.renamed and not r.error]
        if not records:
            QMessageBox.information(self, 'Переименование', 'Нет подтвержденных документов')
            return
        if QMessageBox.question(self, 'Переименование', f'Переименовать проверенных файлов: {len(records)}?') != QMessageBox.Yes:
            return
        errors, count = [], 0
        for record in records:
            try:
                self.journal.apply(record)
                count += 1
                self.log('RENAME_OK')
            except Exception as exc:
                errors.append(Path(record.source).name + ': ' + str(exc))
                self.log('RENAME_ERROR')
        self.refresh()
        QMessageBox.information(self, 'Результат', f'Переименовано: {count}. Ошибок: {len(errors)}\n' + '\n'.join(errors[:20]))

    def undo(self):
        if QMessageBox.question(self, 'Отмена', 'Восстановить исходные имена всех незавершенных операций в журнале?') != QMessageBox.Yes:
            return
        count, errors = self.journal.undo_all()
        if count:
            # Paths are stale after undo. Clear memory to avoid reusing old approvals.
            self.records.clear()
            self.refresh()
        self.log('UNDO')
        QMessageBox.information(self, 'Отмена', f'Восстановлено: {count}\n' + '\n'.join(errors))

    def export(self, ext):
        if not self.records:
            return
        value, _ = QFileDialog.getSaveFileName(self, 'Экспорт', 'Результаты.' + ext, ext.upper() + ' (*.' + ext + ')')
        if not value:
            return
        temporary = None
        try:
            target = local_path(value)
            if target.suffix.lower() != '.' + ext:
                target = target.with_suffix('.' + ext)
            protected = {os.path.normcase(str(local_path(r.source))) for r in self.records}
            protected.update(os.path.normcase(str(local_path(p))) for entry in self.journal.entries() for p in entry[1:3])
            if os.path.normcase(str(target)) in protected:
                raise DocumentError('Экспорт поверх исходного документа запрещен')
            if target.exists() and QMessageBox.question(self, 'Замена экспорта', 'Заменить существующий файл экспорта?') != QMessageBox.Yes:
                return
            handle, name = tempfile.mkstemp(prefix='.localdoc-', suffix='.'+ext, dir=target.parent)
            os.close(handle)
            temporary = Path(name)
            if ext == 'json':
                temporary.write_text(json.dumps([r.export() for r in self.records], ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
            else:
                from openpyxl import Workbook
                book = Workbook()
                sheet = book.active
                sheet.title = 'Результаты'
                keys = ['source', *FIELDS, 'suggested_filename', 'review_required', 'warnings', 'error', 'approved', 'renamed']
                sheet.append(keys)
                for row, record in enumerate(self.records, 2):
                    data = record.export()
                    for col, key in enumerate(keys, 1):
                        value = data.get(key)
                        if isinstance(value, list):
                            value = '; '.join(value)
                        cell = sheet.cell(row, col, value)
                        if isinstance(value, str):
                            cell.data_type = 's'  # Never emit spreadsheet formulas from document text.
                sheet.freeze_panes = 'A2'
                sheet.auto_filter.ref = sheet.dimensions
                for column in sheet.columns:
                    sheet.column_dimensions[column[0].column_letter].width = 25
                book.save(temporary)
                book.close()
            os.replace(temporary, target)
            self.log('EXPORT_' + ext.upper())
            QMessageBox.information(self, 'Экспорт', 'Результаты сохранены')
        except Exception as exc:
            QMessageBox.warning(self, 'Экспорт', str(exc))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def logs(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Локальный журнал')
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        logfile = self.state / 'processing.log'
        view.setPlainText((logfile.read_text('utf-8') if logfile.exists() else '') + '\nПереименования:\n' +
                          '\n'.join(f'{i} | {s} → {t} | {state}' for i,s,t,state in self.journal.entries()))
        layout.addWidget(view)
        clear = QPushButton('Очистить журнал обработки')
        def clean():
            if QMessageBox.question(dialog, 'Очистка', 'Очистить журнал обработки? Журнал отмены сохраняется.') == QMessageBox.Yes:
                logfile.write_text('', encoding='utf-8')
                view.setPlainText('Журнал обработки очищен. История переименований сохранена.')
        clear.clicked.connect(clean)
        layout.addWidget(clear)
        forget = QPushButton('Очистить историю отмененных переименований')
        def forget_history():
            try:
                self.journal.clear_completed()
                view.setPlainText('История отмененных операций очищена')
            except Exception as exc:
                QMessageBox.warning(dialog, 'История', str(exc))
        forget.clicked.connect(forget_history)
        layout.addWidget(forget)
        dialog.exec()

    def clear(self):
        self.records.clear()
        self.refresh()

    def closeEvent(self, event):
        if self.busy():
            self.worker.requestInterruption()
            self.statusBar().showMessage('Завершение текущего фрагмента. После остановки можно закрыть окно')
            event.ignore()
        else:
            self.records.clear()
            self.journal.db.close()
            event.accept()


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['DO_NOT_TRACK'] = '1'
    disable_network()
    app = QApplication(sys.argv)
    try:
        from .privacy import enforce_offline
        enforce_offline()
    except Exception as exc:
        QMessageBox.critical(None, 'Сетевая защита', str(exc))
        return 1
    app.setApplicationName('LocalDocRenamer')
    try:
        window = Window()
    except Exception as exc:
        QMessageBox.critical(None, 'Ошибка запуска', 'Не удалось открыть локальные настройки: ' + type(exc).__name__)
        return 1
    window.show()
    return app.exec()
