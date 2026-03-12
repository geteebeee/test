@echo off
setlocal

REM Build a standalone Windows executable (no Python install required on target machine).

if not exist .venv (
  py -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-build.txt

pyinstaller --noconfirm --clean --windowed --onefile --name MsgAttachmentInspector msg_attachment_extractor.py

echo.
echo Build complete. Executable is in dist\MsgAttachmentInspector.exe
endlocal
