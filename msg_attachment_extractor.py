#!/usr/bin/env python3
"""GUI tool for inspecting and extracting attachments from .msg email files."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTableWidget


@dataclass
class AttachmentRecord:
    """An attachment found in a .msg file."""

    source_msg: Path
    attachment_name: str
    extension: str
    size_bytes: int
    selected: bool = True


class MsgAttachmentExtractor:
    """Utility functions for parsing and extracting .msg attachments."""

    @staticmethod
    def parse_msg_file(msg_path: Path) -> list[AttachmentRecord]:
        extract_msg = _import_extract_msg()
        records: list[AttachmentRecord] = []
        message = extract_msg.Message(str(msg_path))
        try:
            for attachment in message.attachments:
                name = attachment.longFilename or attachment.shortFilename or "unnamed_attachment"
                ext = Path(name).suffix.lower()
                size = len(attachment.data) if attachment.data else 0
                records.append(
                    AttachmentRecord(
                        source_msg=msg_path,
                        attachment_name=name,
                        extension=ext,
                        size_bytes=size,
                    )
                )
        finally:
            message.close()
        return records

    @staticmethod
    def filter_records(records: Iterable[AttachmentRecord], extension_filter: str) -> list[AttachmentRecord]:
        cleaned = extension_filter.strip().lower()
        if not cleaned:
            return list(records)
        if not cleaned.startswith("."):
            cleaned = f".{cleaned}"
        return [record for record in records if record.extension == cleaned]

    @staticmethod
    def records_for_extraction(
        records: Iterable[AttachmentRecord],
        extension_filter: str,
        apply_filter_to_extraction: bool,
    ) -> list[AttachmentRecord]:
        selected = [record for record in records if record.selected]
        if apply_filter_to_extraction:
            return MsgAttachmentExtractor.filter_records(selected, extension_filter)
        return selected

    @staticmethod
    def extract_selected(records: Iterable[AttachmentRecord], output_dir: Path) -> list[Path]:
        extract_msg = _import_extract_msg()
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted_files: list[Path] = []

        records_by_msg: dict[Path, list[AttachmentRecord]] = {}
        for record in records:
            records_by_msg.setdefault(record.source_msg, []).append(record)

        for msg_path, selected_records in records_by_msg.items():
            message = extract_msg.Message(str(msg_path))
            try:
                by_name = {r.attachment_name for r in selected_records}
                for attachment in message.attachments:
                    name = attachment.longFilename or attachment.shortFilename or "unnamed_attachment"
                    if name not in by_name:
                        continue
                    destination = MsgAttachmentExtractor._safe_destination(output_dir, name)
                    with destination.open("wb") as fh:
                        fh.write(attachment.data or b"")
                    extracted_files.append(destination)
            finally:
                message.close()

        return extracted_files

    @staticmethod
    def merge_pdfs(pdf_files: Iterable[Path], output_path: Path) -> Path:
        pypdf = _import_pypdf()
        merger = pypdf.PdfMerger()
        try:
            added = False
            for pdf_path in pdf_files:
                if pdf_path.suffix.lower() != ".pdf":
                    continue
                merger.append(str(pdf_path))
                added = True
            if not added:
                raise RuntimeError("No PDF files were selected/extracted to merge.")
            with output_path.open("wb") as fh:
                merger.write(fh)
        finally:
            merger.close()
        return output_path

    @staticmethod
    def _safe_destination(output_dir: Path, filename: str) -> Path:
        candidate = output_dir / filename
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while True:
            revised = output_dir / f"{stem}_{counter}{suffix}"
            if not revised.exists():
                return revised
            counter += 1


def _import_extract_msg():
    try:
        import extract_msg
    except ImportError as exc:
        raise RuntimeError(
            "The dependency 'extract-msg' is required. Install with: pip install -r requirements.txt"
        ) from exc
    return extract_msg


def _import_pypdf():
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError("The dependency 'pypdf' is required. Install with: pip install -r requirements.txt") from exc
    return pypdf


def start_gui() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QAbstractItemView,
            QCheckBox,
            QFileDialog,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise RuntimeError(
            "The dependency 'PySide6' is required. Install with: pip install -r requirements.txt"
        ) from exc

    class DropTable(QTableWidget):
        """Table widget supporting drag-and-drop of .msg files."""

        def __init__(self, parent: "MainWindow") -> None:
            super().__init__(0, 5, parent)
            self.main_window = parent
            self.setHorizontalHeaderLabels(["Extract", "Email File", "Attachment", "Type", "Size (KB)"])
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QAbstractItemView.DropOnly)
            header = self.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Interactive)
            header.resizeSection(0, 80)
            header.resizeSection(1, 380)
            header.resizeSection(2, 260)
            header.resizeSection(3, 100)
            header.resizeSection(4, 110)

        def dragEnterEvent(self, event):  # type: ignore[override]
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()

        def dragMoveEvent(self, event):  # type: ignore[override]
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event):  # type: ignore[override]
            paths: list[Path] = []
            for url in event.mimeData().urls():
                local = Path(url.toLocalFile())
                if local.is_file() and local.suffix.lower() == ".msg":
                    paths.append(local)
                if local.is_dir():
                    paths.extend(local.glob("*.msg"))
            self.main_window.load_msg_files(paths)
            event.acceptProposedAction()

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("MSG Attachment Inspector")
            self.resize(1150, 640)

            self.records: list[AttachmentRecord] = []
            self.filtered_records: list[AttachmentRecord] = []

            self.table = DropTable(self)
            self.table.itemChanged.connect(self.on_item_changed)

            self.filter_input = QLineEdit()
            self.filter_input.setPlaceholderText("Type filter (e.g. .pdf or pdf)")
            self.filter_input.textChanged.connect(self.apply_filter)

            self.all_visible_checkbox = QCheckBox("Select all visible")
            self.all_visible_checkbox.stateChanged.connect(self.toggle_all_visible)

            self.apply_filter_extract_checkbox = QCheckBox("Apply type filter during extraction")
            self.apply_filter_extract_checkbox.setChecked(True)

            self.merge_pdf_checkbox = QCheckBox("Merge extracted PDFs into one file")
            self.merge_pdf_filename = QLineEdit("merged.pdf")

            open_button = QPushButton("Add .msg files")
            open_button.clicked.connect(self.open_file_picker)

            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(self.clear_records)

            select_filtered_button = QPushButton("Select filtered")
            select_filtered_button.clicked.connect(lambda: self.set_selection_for_filtered(True))

            deselect_filtered_button = QPushButton("Deselect filtered")
            deselect_filtered_button.clicked.connect(lambda: self.set_selection_for_filtered(False))

            extract_button = QPushButton("Extract selected...")
            extract_button.clicked.connect(self.extract_selected)

            top_row = QHBoxLayout()
            top_row.addWidget(QLabel("Drop .msg files into the table or click Add .msg files"))
            top_row.addStretch()
            top_row.addWidget(open_button)
            top_row.addWidget(clear_button)

            controls_row = QHBoxLayout()
            controls_row.addWidget(QLabel("Attachment type filter:"))
            controls_row.addWidget(self.filter_input)
            controls_row.addWidget(self.all_visible_checkbox)
            controls_row.addWidget(select_filtered_button)
            controls_row.addWidget(deselect_filtered_button)

            options_row = QHBoxLayout()
            options_row.addWidget(self.apply_filter_extract_checkbox)
            options_row.addWidget(self.merge_pdf_checkbox)
            options_row.addWidget(QLabel("Merged filename:"))
            options_row.addWidget(self.merge_pdf_filename)
            options_row.addStretch()
            options_row.addWidget(extract_button)

            layout = QVBoxLayout()
            layout.addLayout(top_row)
            layout.addLayout(controls_row)
            layout.addLayout(options_row)
            layout.addWidget(self.table)

            container = QWidget()
            container.setLayout(layout)
            self.setCentralWidget(container)

        def open_file_picker(self) -> None:
            files, _ = QFileDialog.getOpenFileNames(self, "Select .msg files", "", "Outlook Email (*.msg)")
            self.load_msg_files([Path(f) for f in files])

        def load_msg_files(self, files: Iterable[Path]) -> None:
            added = 0
            for file_path in files:
                try:
                    self.records.extend(MsgAttachmentExtractor.parse_msg_file(file_path))
                    added += 1
                except Exception as exc:
                    QMessageBox.warning(self, "Unable to parse file", f"Failed to parse {file_path}: {exc}")
            if added == 0:
                return
            self.apply_filter()

        def clear_records(self) -> None:
            self.records.clear()
            self.filtered_records.clear()
            self.table.setRowCount(0)

        def apply_filter(self) -> None:
            self.filtered_records = MsgAttachmentExtractor.filter_records(self.records, self.filter_input.text())
            self.refresh_table()

        def refresh_table(self) -> None:
            self.table.blockSignals(True)
            self.table.setRowCount(len(self.filtered_records))
            for row, record in enumerate(self.filtered_records):
                checkbox = QTableWidgetItem()
                checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                checkbox.setCheckState(Qt.Checked if record.selected else Qt.Unchecked)
                self.table.setItem(row, 0, checkbox)

                self.table.setItem(row, 1, QTableWidgetItem(str(record.source_msg)))
                self.table.setItem(row, 2, QTableWidgetItem(record.attachment_name))
                self.table.setItem(row, 3, QTableWidgetItem(record.extension or "(no extension)"))
                self.table.setItem(row, 4, QTableWidgetItem(f"{record.size_bytes / 1024:.2f}"))
            self.table.blockSignals(False)
            self.sync_select_all_checkbox()

        def on_item_changed(self, item: QTableWidgetItem) -> None:
            if item.column() != 0:
                return
            row = item.row()
            if 0 <= row < len(self.filtered_records):
                self.filtered_records[row].selected = item.checkState() == Qt.Checked
            self.sync_select_all_checkbox()

        def sync_select_all_checkbox(self) -> None:
            if not self.filtered_records:
                self.all_visible_checkbox.blockSignals(True)
                self.all_visible_checkbox.setChecked(False)
                self.all_visible_checkbox.blockSignals(False)
                return
            all_selected = all(record.selected for record in self.filtered_records)
            self.all_visible_checkbox.blockSignals(True)
            self.all_visible_checkbox.setChecked(all_selected)
            self.all_visible_checkbox.blockSignals(False)

        def toggle_all_visible(self) -> None:
            should_select = self.all_visible_checkbox.isChecked()
            self.set_selection_for_filtered(should_select)

        def set_selection_for_filtered(self, selected: bool) -> None:
            for record in self.filtered_records:
                record.selected = selected
            self.refresh_table()

        def extract_selected(self) -> None:
            chosen_records = MsgAttachmentExtractor.records_for_extraction(
                self.records,
                self.filter_input.text(),
                self.apply_filter_extract_checkbox.isChecked(),
            )
            if not chosen_records:
                QMessageBox.information(self, "Nothing to extract", "No attachments match current selection/filter.")
                return

            output_dir = QFileDialog.getExistingDirectory(self, "Choose extraction folder")
            if not output_dir:
                return

            output_path = Path(output_dir)
            try:
                extracted = MsgAttachmentExtractor.extract_selected(chosen_records, output_path)
                merged_path = None
                if self.merge_pdf_checkbox.isChecked():
                    merged_name = self.merge_pdf_filename.text().strip() or "merged.pdf"
                    if not merged_name.lower().endswith(".pdf"):
                        merged_name += ".pdf"
                    safe_merged = MsgAttachmentExtractor._safe_destination(output_path, merged_name)
                    merged_path = MsgAttachmentExtractor.merge_pdfs(extracted, safe_merged)
            except Exception as exc:
                QMessageBox.critical(self, "Extraction failed", str(exc))
                return

            message = f"Extracted {len(extracted)} attachments to:\n{output_dir}"
            if merged_path:
                message += f"\n\nMerged PDF:\n{merged_path}"
            QMessageBox.information(self, "Done", message)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


def main() -> int:
    return start_gui()


if __name__ == "__main__":
    raise SystemExit(main())
