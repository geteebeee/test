# MSG Attachment Inspector

Cross-platform desktop GUI (Windows/Linux) for bulk inspection and extraction of attachments from Outlook `.msg` files.

## Features
- Drag & drop multiple `.msg` files into the app.
- See parsed attachments in a table (email source, name, extension, size).
- Tick/untick which attachments should be extracted.
- Filter the list by file type (for example `pdf` or `.pdf`) and optionally apply that filter to extraction scope.
- Extract selected attachments into an output folder.
- Merge extracted PDFs into one file (optional).
- One-click controls to select/deselect all visible rows and select by active type filter.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

On Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run
```bash
python msg_attachment_extractor.py
```


## Makefile shortcuts (Linux/macOS)
```bash
make test
make lint
make run
```

## Build a Windows executable (`.exe`)
If you want to test on a Windows machine that does **not** have Python installed, build on Windows with:

```bat
build_windows_exe.bat
```

This produces:
- `dist\MsgAttachmentInspector.exe`

You can copy that `.exe` to another Windows PC and run it directly.

## Extraction behavior
- The **Apply type filter during extraction** toggle controls whether hidden/non-matching file types are excluded from extraction.
- This means filter changes can now affect both what is displayed and what is extracted (when enabled).

## Notes
- Supports Windows and Linux as requested.
- `.msg` parsing is powered by `extract-msg`.
- GUI is built with Qt via `PySide6`.
