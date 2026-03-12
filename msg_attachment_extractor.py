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
    def extract_selected(records: Iterable[AttachmentRecord], output_dir: Path) -> list[Path]:
        extract_msg = _import_extract_msg()
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted_files: list[Path] = []

        records_by_msg: dict[Path, list[AttachmentRecord]] = {}
        for record in records:
            if not record.selected:
                continue
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


def start_gui() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QFileDialog,
            QHBoxLayout,
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
            self.setDragDropMode(QTableWidget.DropOnly)
            self.horizontalHeader().setStretchLastSection(True)

        def dragEnterEvent(self, event):  # type: ignore[override]
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event):  # type: ignore[override]
            paths = []
            for url in event.mimeData().urls():
                local_path = Path(url.toLocalFile())
                if local_path.suffix.lower() == ".msg":
                    paths.append(local_path)
            self.main_window.load_msg_files(paths)
            event.acceptProposedAction()

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("MSG Attachment Inspector")
            self.resize(1100, 600)

            self.records: list[AttachmentRecord] = []
            self.filtered_records: list[AttachmentRecord] = []

            self.table = DropTable(self)
            self.filter_input = QLineEdit()
            self.filter_input.setPlaceholderText("Filter by extension (e.g. .pdf or pdf)")
            self.filter_input.textChanged.connect(self.apply_filter)

            open_button = QPushButton("Add .msg files")
            open_button.clicked.connect(self.open_file_picker)

            extract_button = QPushButton("Extract selected...")
            extract_button.clicked.connect(self.extract_selected)

            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(self.clear_records)

            top_row = QHBoxLayout()
            top_row.addWidget(QLabel("Drop .msg files into the table or click Add .msg files"))
            top_row.addStretch()
            top_row.addWidget(open_button)
            top_row.addWidget(clear_button)

            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("Attachment type filter:"))
            filter_row.addWidget(self.filter_input)
            filter_row.addWidget(extract_button)

            layout = QVBoxLayout()
            layout.addLayout(top_row)
            layout.addLayout(filter_row)
            layout.addWidget(self.table)

            container = QWidget()
            container.setLayout(layout)
            self.setCentralWidget(container)

        def open_file_picker(self) -> None:
            files, _ = QFileDialog.getOpenFileNames(self, "Select .msg files", "", "Outlook Email (*.msg)")
            self.load_msg_files([Path(f) for f in files])

        def load_msg_files(self, files: Iterable[Path]) -> None:
            for file_path in files:
                try:
                    self.records.extend(MsgAttachmentExtractor.parse_msg_file(file_path))
                except Exception as exc:
                    QMessageBox.warning(self, "Unable to parse file", f"Failed to parse {file_path}: {exc}")
            self.apply_filter()

        def clear_records(self) -> None:
            self.records.clear()
            self.filtered_records.clear()
            self.table.setRowCount(0)

        def apply_filter(self) -> None:
            self.filtered_records = MsgAttachmentExtractor.filter_records(self.records, self.filter_input.text())
            self.refresh_table()

        def refresh_table(self) -> None:
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

        def extract_selected(self) -> None:
            for row, record in enumerate(self.filtered_records):
                check_item = self.table.item(row, 0)
                record.selected = bool(check_item and check_item.checkState() == Qt.Checked)

            output_dir = QFileDialog.getExistingDirectory(self, "Choose extraction folder")
            if not output_dir:
                return

            try:
                extracted = MsgAttachmentExtractor.extract_selected(self.records, Path(output_dir))
            except Exception as exc:
                QMessageBox.critical(self, "Extraction failed", str(exc))
                return

            QMessageBox.information(self, "Done", f"Extracted {len(extracted)} attachments to:\n{output_dir}")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


def main() -> int:
    return start_gui()


if __name__ == "__main__":
    raise SystemExit(main())
