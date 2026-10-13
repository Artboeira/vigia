@echo off
rem Gera dist\Vigia.exe (Windows 10/11). Rode no Windows, na pasta do projeto:
rem   packaging\build_windows.bat
rem Precisa de Python 3.10+ de python.org. O WebView2 ja vem no Windows 10/11 atualizado.
setlocal
python -m venv build\venv || exit /b 1
call build\venv\Scripts\activate.bat
pip install --quiet --upgrade pip
pip install --quiet pyinstaller pillow pywebview || exit /b 1
python -m unittest discover -s tests -t . || exit /b 1
python packaging\make_icon.py build\icon.png || exit /b 1
pyinstaller --noconfirm --onefile --windowed --name Vigia --icon "%CD%\build\icon.png" --paths "%CD%" ^
  --add-data "%CD%\vigia\infra\web\static;vigia\infra\web\static" ^
  --distpath "%CD%\dist" --workpath "%CD%\build\work" --specpath "%CD%\build" ^
  "%CD%\packaging\run_vigia.py" || exit /b 1
echo ok: dist\Vigia.exe
