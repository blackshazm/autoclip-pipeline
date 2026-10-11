@echo off
chcp 65001 > nul
title Conexão de Contas - Canal Finanças (Raiz do Éden)
color 0b
cd /d "%~dp0"

:menu
cls
echo ========================================================
echo   CONEXÃO AUTOMÁTICA - CANAL FINANÇAS (RAIZ DO ÉDEN)
echo ========================================================
echo.
echo Selecione qual plataforma deseja conectar para FINANÇAS:
echo.
echo [1] Conectar YouTube Studio (Shorts - Raiz do Éden)
echo [2] Conectar TikTok Studio (TikTok - Finanças)
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
echo  Conectando YouTube Studio (Canal: Raiz do Éden)...
echo ========================================================
echo.
python scripts\youtube_login.py --niche financas
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:tk
cls
echo ========================================================
echo  Conectando TikTok Studio (Finanças)...
echo ========================================================
echo.
python scripts\tiktok_login.py --niche financas
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:ambos
cls
echo [1/2] Conectando YouTube Studio (Finanças - Raiz do Éden)...
python scripts\youtube_login.py --niche financas
echo.
echo [2/2] Conectando TikTok Studio (Finanças)...
python scripts\tiktok_login.py --niche financas
echo.
echo ========================================================
echo  Conexão do Canal Finanças concluída com sucesso!
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
