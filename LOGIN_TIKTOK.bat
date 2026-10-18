@echo off
chcp 65001 > nul
title Login TikTok Studio - AutoClip
color 0b
cd /d "%~dp0"

:menu
cls
echo ========================================================
echo        CONEXÃO TIKTOK STUDIO - AUTOCLIP PIPELINE
echo ========================================================
echo.
echo Selecione qual canal deseja conectar no TikTok:
echo.
echo [1] Conectar TikTok FITNESS
echo [2] Conectar TikTok FINANÇAS
echo [3] Conectar TikTok PADRÃO / GERAL
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
echo Conectando TikTok Studio (Canal FITNESS)...
python scripts\tiktok_login.py --niche fitness
echo.
pause
goto menu

:fin
cls
echo Conectando TikTok Studio (Canal FINANÇAS)...
python scripts\tiktok_login.py --niche financas
echo.
pause
goto menu

:def
cls
echo Conectando TikTok Studio (Geral)...
python scripts\tiktok_login.py
echo.
pause
goto menu
