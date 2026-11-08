@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Instalar Graphify (graphifyy) para MILLER
echo ============================================
set "PY=python"
where py >/dev/null 2>/dev/null && set "PY=py -3.13"
%PY% --version >/dev/null 2>/dev/null || set "PY=python"
%PY% --version || (echo Instale Python 3.13 & pause & exit /b 1)
echo.
echo [1/4] Instalando pipx...
%PY% -m pip install --user --upgrade pipx
%PY% -m pipx ensurepath
echo.
echo [2/4] Instalando graphify (paquete oficial: graphifyy, con doble y)...
%PY% -m pipx install graphifyy || %PY% -m pipx upgrade graphifyy
if errorlevel 1 (echo Error instalando graphify & pause & exit /b 1)
echo.
echo [3/4] Registrando graphify en su asistente de IA...
%PY% -m pipx run --spec graphifyy graphify install
echo.
echo [4/4] Creando el mapa de MILLER (local, sin enviar codigo a internet)...
%PY% -m pipx run --spec graphifyy graphify update .
echo.
echo Listo. Abra graphify-out\graph.html para ver el mapa de MILLER.
echo Si "graphify" no se reconoce en una consola nueva, cierre y abra la consola.
pause
