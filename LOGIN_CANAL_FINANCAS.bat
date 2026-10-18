@echo off
chcp 65001 > nul
title Conexão de Contas - Canal Finanças (Raiz do Éden)
color 0b
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] O Python não foi encontrado no PATH do sistema.
    echo Instale o Python ou adicione-o às variáveis de ambiente para continuar.
    if "%1"=="" pause
    exit /b 1
)

if /i "%1"=="--yt" goto yt
if /i "%1"=="--tk" goto tk
if /i "%1"=="--ambos" goto ambos
if /i "%1"=="--diag" goto diag
if /i "%1"=="--status" goto diag

:menu
cls
echo ========================================================
echo   CONEXAO AUTOMATICA - CANAL FINANCAS (RAIZ DO EDEN)
echo ========================================================
echo.
echo Selecione qual plataforma deseja conectar para FINANCAS:
echo.
echo [1] Conectar YouTube Studio (Shorts - Raiz do Eden)
echo [2] Conectar TikTok Studio (TikTok - Financas)
echo [3] Conectar AMBOS em sequencia (YouTube + TikTok)
echo [4] Testar Diagnostico de Saude e Sessao das Contas
echo [0] Sair
echo.
set "opcao="
set /p opcao="Digite a opcao desejada [1-4, 0]: "

if defined opcao set "opcao=%opcao: =%"
if "%opcao%"=="1" goto yt
if "%opcao%"=="2" goto tk
if "%opcao%"=="3" goto ambos
if "%opcao%"=="4" goto diag
if "%opcao%"=="0" exit /b 0

echo.
echo [!] Opcao invalida. Digite 1, 2, 3, 4 ou 0.
timeout /t 2 >nul
goto menu

:yt
cls
echo ========================================================
echo  Conectando YouTube Studio (Canal: Raiz do Eden)...
echo ========================================================
echo.
python scripts\youtube_login.py --niche financas
set "yt_res=%errorlevel%"
if "%yt_res%"=="0" (
    echo.
    echo [OK] YouTube Studio (Financas) conectado com sucesso!
) else (
    echo.
    echo [AVISO] O login do YouTube Financas nao foi confirmado.
)
if not "%1"=="" exit /b %yt_res%
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:tk
cls
echo ========================================================
echo  Conectando TikTok Studio (Financas)...
echo ========================================================
echo.
python scripts\tiktok_login.py --niche financas
set "tk_res=%errorlevel%"
if "%tk_res%"=="0" (
    echo.
    echo [OK] TikTok Studio (Financas) conectado com sucesso!
) else (
    echo.
    echo [AVISO] O login do TikTok Financas nao foi confirmado.
)
if not "%1"=="" exit /b %tk_res%
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:ambos
cls
echo ========================================================
echo  [1/2] Conectando YouTube Studio (Financas - Raiz do Eden)...
echo ========================================================
echo.
python scripts\youtube_login.py --niche financas
set "yt_err=%errorlevel%"

echo.
echo ========================================================
echo  [2/2] Conectando TikTok Studio (Financas)...
echo ========================================================
echo.
python scripts\tiktok_login.py --niche financas
set "tk_err=%errorlevel%"

cls
echo ========================================================
echo  RESUMO DA CONEXAO - CANAL FINANCAS
echo ========================================================
echo.
if "%yt_err%"=="0" (
    echo   [OK] YouTube Studio (Raiz do Eden): Conectado com sucesso.
) else (
    echo   [FALHA] YouTube Studio (Raiz do Eden): Login nao confirmado.
)

if "%tk_err%"=="0" (
    echo   [OK] TikTok Studio (Financas): Conectado com sucesso.
) else (
    echo   [FALHA] TikTok Studio (Financas): Login nao confirmado.
)
echo.
echo ========================================================
if not "%1"=="" exit /b 0
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:diag
cls
echo ========================================================
echo  Executando diagnostico de saude das contas...
echo ========================================================
echo.
python scripts\verify_accounts_health.py
set "diag_res=%errorlevel%"
if not "%1"=="" exit /b %diag_res%
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu