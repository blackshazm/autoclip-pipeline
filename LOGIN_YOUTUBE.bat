@echo off
chcp 65001 > nul
title Login YouTube Studio - AutoClip
color 0c
cd /d "%~dp0"

:menu
cls
echo ========================================================
echo     CONEXÃO YOUTUBE STUDIO - AUTOCLIP PIPELINE
echo ========================================================
echo.
echo Selecione qual canal deseja conectar:
echo.
echo [1] Conectar Canal FITNESS (weslleykebra)
echo [2] Conectar Canal FINANÇAS (Raiz do Éden)
echo [3] Conectar Canal PADRÃO / GERAL
echo [0] Sair
echo.
set /p opcao="Digite a opção desejada [1, 2, 3, 0]: "

if "%opcao%"=="1" goto fit
if "%opcao%"=="2" goto fin
if "%opcao%"=="3" goto def
if "%opcao%"=="0" exit
goto menu

:fit
cls
echo Conectando YouTube Studio (Canal FITNESS)...
python scripts\youtube_login.py --niche fitness
echo.
pause
goto menu

:fin
cls
echo Conectando YouTube Studio (Canal FINANÇAS)...
python scripts\youtube_login.py --niche financas
echo.
pause
goto menu

:def
cls
echo Conectando YouTube Studio (Geral)...
python scripts\youtube_login.py
echo.
pause
goto menu
