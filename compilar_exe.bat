@echo off
chcp 65001 >nul
title MILLER - compilar ejecutable
cd /d "%~dp0"

echo [1/3] Instalando dependencias de MILLER y PyInstaller...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo [2/3] Compilando MILLER.exe (puede tardar varios minutos)...
python -m PyInstaller --noconfirm --clean miller.spec
if errorlevel 1 goto error

echo [3/3] Listo: dist\MILLER\MILLER.exe
echo El ejecutable usa las carpetas modelos, audios y datos de esta misma carpeta.
echo No mueva dist\MILLER sin llevarse tambien modelos, audios y datos.
pause
exit /b 0

:error
echo.
echo ERROR: la compilacion no termino. Revise los mensajes de arriba.
pause
exit /b 1
