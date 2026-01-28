#!/usr/bin/env python3
"""
pdf2clip-gui: draw rectangles on a PDF to extract text into TSV.
"""
from __future__ import annotations

import importlib.util
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

import re
import statistics


if importlib.util.find_spec("fitz") is None:
    print("Error: PyMuPDF (fitz) is required. Install with 'pip install pymupdf'.", file=sys.stderr)
    sys.exit(1)

import fitz  # PyMuPDF


NUMBER_RE = re.compile(r"^[+-]?\d{1,3}([\s\u00A0]\d{3})*(,\d+)?$|^[+-]?\d+(,\d+)?$")


@dataclass
class Selection:
    page_index: int
    rect: "fitz.Rect"


@dataclass
class Cell:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    page: int
    source: Path

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2.0


@dataclass
class Row:
    cells: List[Cell]
    y_center: float


@dataclass
class AnchorSet:
    anchors: List[float]
    source: str


@dataclass
class AssignResult:
    rows: List[List[str]]
    headers: List[str]
    unassigned_count: int
    too_few_rows: int
    too_many_rows: int
    target_cols: int


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00A0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_number(text: str) -> str:
    if not NUMBER_RE.match(text):
        return text
    normalized = text.replace("\u00A0", " ").replace(" ", "")
    normalized = normalized.replace(",", ".")
    return normalized


def text_from_rect(page: "fitz.Page", rect: "fitz.Rect") -> str:
    text = page.get_text("text", clip=rect) or ""
    text = normalize_whitespace(text)
    if text:
        return text
    words = page.get_text("words") or []
    matched = []
    for w in words:
        x0, y0, x1, y1, word, *_ = w
        wrect = fitz.Rect(x0, y0, x1, y1)
        if rect.intersects(wrect):
            matched.append((y0, x0, word))
    matched.sort()
    return normalize_whitespace(" ".join(word for _, _, word in matched))


def cluster_rows(cells: Sequence[Cell], row_tol: float) -> List[Row]:
    rows: List[Row] = []
    for cell in sorted(cells, key=lambda c: c.y_center):
        placed = False
        for row in rows:
            if abs(cell.y_center - row.y_center) <= row_tol:
                row.cells.append(cell)
                row.y_center = statistics.mean(c.y_center for c in row.cells)
                placed = True
                break
        if not placed:
            rows.append(Row(cells=[cell], y_center=cell.y_center))
    for row in rows:
        row.cells.sort(key=lambda c: c.x0)
    return rows


def mode_count(counts: Sequence[int], min_cols: int) -> int:
    if not counts:
        return min_cols
    freq: Dict[int, int] = {}
    for count in counts:
        freq[count] = freq.get(count, 0) + 1
    mode_value = max(freq.items(), key=lambda item: item[1])[0]
    return max(mode_value, min_cols)


def build_anchors(rows: Sequence[Row], target_cols: int, col_tol: float) -> AnchorSet:
    candidates = [row for row in rows if len(row.cells) == target_cols]
    x_centers: List[float] = []
    for row in candidates:
        x_centers.extend(cell.x_center for cell in row.cells)
    x_centers.sort()
    anchors: List[float] = []
    for x in x_centers:
        if not anchors or abs(x - anchors[-1]) > col_tol:
            anchors.append(x)
        else:
            anchors[-1] = statistics.mean([anchors[-1], x])
    if len(anchors) != target_cols:
        if len(anchors) > target_cols:
            anchors = anchors[:target_cols]
        else:
            while len(anchors) < target_cols and anchors:
                anchors.append(anchors[-1] + col_tol)
    return AnchorSet(anchors=anchors, source="auto")


def assign_cells(rows: Sequence[Row], anchors: AnchorSet, col_tol: float) -> AssignResult:
    headers = [f"Col{i + 1}" for i in range(len(anchors.anchors))]
    result_rows: List[List[str]] = []
    unassigned = 0
    too_few = 0
    too_many = 0
    for row in rows:
        output = ["" for _ in anchors.anchors]
        if len(row.cells) < len(anchors.anchors):
            too_few += 1
        if len(row.cells) > len(anchors.anchors):
            too_many += 1
        for cell in row.cells:
            distances = [abs(cell.x_center - anchor) for anchor in anchors.anchors]
            if not distances:
                continue
            col_index = distances.index(min(distances))
            if distances[col_index] > col_tol:
                unassigned += 1
                continue
            if output[col_index]:
                output[col_index] = f"{output[col_index]} | {cell.text}"
            else:
                output[col_index] = cell.text
        result_rows.append(output)
    return AssignResult(
        rows=result_rows,
        headers=headers,
        unassigned_count=unassigned,
        too_few_rows=too_few,
        too_many_rows=too_many,
        target_cols=len(anchors.anchors),
    )


def cells_to_tsv(
    cells: Sequence[Cell],
    row_tol: float,
    col_tol: float,
    min_cols: int,
    include_source: bool,
    normalize_numbers: bool,
) -> Tuple[str, AssignResult]:
    rows = cluster_rows(cells, row_tol=row_tol)
    target_cols = mode_count([len(row.cells) for row in rows], min_cols=min_cols)
    anchors = build_anchors(rows, target_cols=target_cols, col_tol=col_tol)
    assigned = assign_cells(rows, anchors=anchors, col_tol=col_tol)
    output_lines: List[str] = []
    headers = assigned.headers
    if include_source:
        headers = ["SourceFile", "SourcePage"] + headers
    output_lines.append("\t".join(headers))
    for row, row_obj in zip(assigned.rows, rows):
        values = row
        if normalize_numbers:
            values = [normalize_number(value) for value in values]
        if include_source:
            source_file = row_obj.cells[0].source.name if row_obj.cells else ""
            source_page = str(row_obj.cells[0].page + 1) if row_obj.cells else ""
            values = [source_file, source_page] + values
        output_lines.append("\t".join(values))
    return "\n".join(output_lines), assigned


class Pdf2ClipApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("pdf2clip-gui")
        self.doc: Optional[fitz.Document] = None
        self.pdf_path: Optional[Path] = None
        self.page_index = 0
        self.zoom = 2.0
        self.selections: List[Selection] = []
        self.canvas = tk.Canvas(root, bg="#1e1e1e")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.image_id: Optional[int] = None
        self.image_obj = None
        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_rect_id: Optional[int] = None

        controls = ttk.Frame(root)
        controls.grid(row=0, column=1, sticky="ns")

        ttk.Button(controls, text="Open PDF", command=self.open_pdf).grid(row=0, column=0, pady=4, sticky="ew")
        ttk.Button(controls, text="Prev", command=self.prev_page).grid(row=1, column=0, pady=4, sticky="ew")
        ttk.Button(controls, text="Next", command=self.next_page).grid(row=2, column=0, pady=4, sticky="ew")
        ttk.Button(controls, text="Clear Page", command=self.clear_page).grid(row=3, column=0, pady=4, sticky="ew")
        ttk.Button(controls, text="Clear All", command=self.clear_all).grid(row=4, column=0, pady=4, sticky="ew")

        ttk.Label(controls, text="Row tol").grid(row=5, column=0, sticky="w")
        self.row_tol_var = tk.DoubleVar(value=6.0)
        ttk.Entry(controls, textvariable=self.row_tol_var, width=8).grid(row=6, column=0, sticky="ew")

        ttk.Label(controls, text="Col tol").grid(row=7, column=0, sticky="w")
        self.col_tol_var = tk.DoubleVar(value=12.0)
        ttk.Entry(controls, textvariable=self.col_tol_var, width=8).grid(row=8, column=0, sticky="ew")

        ttk.Label(controls, text="Min cols").grid(row=9, column=0, sticky="w")
        self.min_cols_var = tk.IntVar(value=2)
        ttk.Entry(controls, textvariable=self.min_cols_var, width=8).grid(row=10, column=0, sticky="ew")

        self.include_source_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Include source", variable=self.include_source_var).grid(
            row=11, column=0, sticky="w", pady=2
        )
        self.normalize_numbers_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Normalize numbers", variable=self.normalize_numbers_var).grid(
            row=12, column=0, sticky="w", pady=2
        )

        ttk.Button(controls, text="Copy TSV", command=self.copy_tsv).grid(row=13, column=0, pady=6, sticky="ew")
        ttk.Button(controls, text="Save TSV", command=self.save_tsv).grid(row=14, column=0, pady=6, sticky="ew")

        self.status_var = tk.StringVar(value="Load a PDF to begin.")
        ttk.Label(controls, textvariable=self.status_var, wraplength=180).grid(row=15, column=0, pady=8)

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)

    def open_pdf(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            doc = fitz.open(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open PDF: {exc}")
            return
        if doc.is_encrypted:
            messagebox.showerror("Error", "Encrypted PDF is not supported.")
            return
        self.doc = doc
        self.pdf_path = Path(path)
        self.page_index = 0
        self.selections.clear()
        self.render_page()

    def render_page(self) -> None:
        if not self.doc:
            return
        page = self.doc.load_page(self.page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        self.image_obj = tk.PhotoImage(data=pix.tobytes("ppm"))
        self.canvas.delete("all")
        self.image_id = self.canvas.create_image(0, 0, anchor="nw", image=self.image_obj)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.draw_selection_overlays()
        self.update_status()

    def draw_selection_overlays(self) -> None:
        if not self.doc:
            return
        for selection in self.selections:
            if selection.page_index != self.page_index:
                continue
            rect = selection.rect
            x0 = rect.x0 * self.zoom
            y0 = rect.y0 * self.zoom
            x1 = rect.x1 * self.zoom
            y1 = rect.y1 * self.zoom
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#00ff99", width=2)

    def on_drag_start(self, event: tk.Event) -> None:
        if not self.doc:
            return
        self.drag_start = (event.x, event.y)
        if self.drag_rect_id:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

    def on_drag_move(self, event: tk.Event) -> None:
        if not self.doc or not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        if self.drag_rect_id:
            self.canvas.coords(self.drag_rect_id, x0, y0, x1, y1)
        else:
            self.drag_rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ffaa00", width=2)

    def on_drag_end(self, event: tk.Event) -> None:
        if not self.doc or not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        self.drag_start = None
        if self.drag_rect_id:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None
        if abs(x1 - x0) < 4 or abs(y1 - y0) < 4:
            return
        pdf_rect = fitz.Rect(
            min(x0, x1) / self.zoom,
            min(y0, y1) / self.zoom,
            max(x0, x1) / self.zoom,
            max(y0, y1) / self.zoom,
        )
        self.selections.append(Selection(page_index=self.page_index, rect=pdf_rect))
        self.render_page()

    def prev_page(self) -> None:
        if not self.doc:
            return
        if self.page_index > 0:
            self.page_index -= 1
            self.render_page()

    def next_page(self) -> None:
        if not self.doc:
            return
        if self.page_index < self.doc.page_count - 1:
            self.page_index += 1
            self.render_page()

    def clear_page(self) -> None:
        if not self.doc:
            return
        self.selections = [sel for sel in self.selections if sel.page_index != self.page_index]
        self.render_page()

    def clear_all(self) -> None:
        if not self.doc:
            return
        self.selections.clear()
        self.render_page()

    def update_status(self) -> None:
        total = len(self.selections)
        if not self.doc:
            self.status_var.set("Load a PDF to begin.")
            return
        self.status_var.set(
            f"{self.pdf_path.name} - Page {self.page_index + 1}/{self.doc.page_count} | "
            f"Selections: {total}"
        )

    def build_cells(self) -> List[Cell]:
        if not self.doc or not self.pdf_path:
            return []
        cells: List[Cell] = []
        for selection in self.selections:
            page = self.doc.load_page(selection.page_index)
            text = text_from_rect(page, selection.rect)
            text = normalize_whitespace(text)
            cells.append(
                Cell(
                    text=text,
                    x0=selection.rect.x0,
                    x1=selection.rect.x1,
                    y0=selection.rect.y0,
                    y1=selection.rect.y1,
                    page=selection.page_index,
                    source=self.pdf_path,
                )
            )
        return cells

    def generate_tsv(self) -> Optional[str]:
        cells = self.build_cells()
        if not cells:
            messagebox.showinfo("No selections", "Draw rectangles on the PDF before exporting.")
            return None
        tsv, assigned = cells_to_tsv(
            cells,
            row_tol=self.row_tol_var.get(),
            col_tol=self.col_tol_var.get(),
            min_cols=self.min_cols_var.get(),
            include_source=self.include_source_var.get(),
            normalize_numbers=self.normalize_numbers_var.get(),
        )
        self.status_var.set(
            f"Rows: {len(assigned.rows)} | Cols: {assigned.target_cols} | "
            f"Unassigned: {assigned.unassigned_count}"
        )
        return tsv

    def copy_tsv(self) -> None:
        tsv = self.generate_tsv()
        if tsv is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(tsv)
        messagebox.showinfo("Copied", "TSV copied to clipboard.")

    def save_tsv(self) -> None:
        tsv = self.generate_tsv()
        if tsv is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".tsv", filetypes=[("TSV", "*.tsv")])
        if not path:
            return
        Path(path).write_text(tsv, encoding="utf-8")
        messagebox.showinfo("Saved", f"Saved TSV to {path}")


def main() -> None:
    root = tk.Tk()
    app = Pdf2ClipApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
