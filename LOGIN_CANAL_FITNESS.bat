@echo off
chcp 65001 > nul
title Conexão de Contas - Canal Fitness
color 0a
cd /d "%~dp0"

:menu
cls
echo ========================================================
echo       CONEXÃO AUTOMÁTICA - CANAL FITNESS / SHAPE
echo ========================================================
echo.
echo Selecione qual plataforma deseja conectar para FITNESS:
echo.
echo [1] Conectar YouTube Studio (Shorts - Fitness)
echo [2] Conectar TikTok Studio (TikTok - Fitness)
echo [3] Conectar AMBOS em sequência (YouTube + TikTok)
echo [4] Testar Diagnóstico de Saúde e Sessão das Contas
echo [0] Sair
echo.
set /p opcao="Digite a opção desejada [1-4, 0]: "

if "%opcao%"=="1" goto yt
if "%opcao%"=="2" goto tk
if "%opcao%"=="3" goto ambos
if "%opcao%"=="4" goto diag
if "%opcao%"=="0" exit
goto menu

:yt
cls
echo ========================================================
echo  Conectando YouTube Studio (Fitness)...
echo ========================================================
echo.
python scripts\youtube_login.py --niche fitness
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:tk
cls
echo ========================================================
echo  Conectando TikTok Studio (Fitness)...
echo ========================================================
echo.
python scripts\tiktok_login.py --niche fitness
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:ambos
cls
echo [1/2] Conectando YouTube Studio (Fitness)...
python scripts\youtube_login.py --niche fitness
echo.
echo [2/2] Conectando TikTok Studio (Fitness)...
python scripts\tiktok_login.py --niche fitness
echo.
echo ========================================================
echo  Conexão do Canal Fitness concluída com sucesso!
echo ========================================================
pause
goto menu

:diag
cls
echo Executando diagnóstico rápido das contas...
echo.
python scripts\verify_accounts_health.py
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu
