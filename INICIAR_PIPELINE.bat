@echo off
chcp 65001 > nul
title Esteira Autônoma de Cortes - Pipeline
color 0a
cd /d "%~dp0"

if "%1"=="--status" goto status
if "%1"=="--stop" goto stop

:menu
cls
echo =================================================================
echo   ESTEIRA AUTÔNOMA DE CORTES - AUTOCLIP PIPELINE
echo =================================================================
echo.
echo Selecione a operação desejada:
echo.
echo [1] Iniciar Esteira Contínua (Robô 1 + SupoClipe + Robô 2)
echo [2] Verificar Status dos Robôs e Filas
echo [3] Parar Execução da Esteira
echo [0] Sair
echo.
set /p opcao="Digite a opção desejada [1, 2, 3, 0]: "

if "%opcao%"=="1" goto run
if "%opcao%"=="2" goto status
if "%opcao%"=="3" goto stop
if "%opcao%"=="0" exit
goto menu

:run
cls
echo =================================================================
echo   INICIANDO ESTEIRA AUTÔNOMA DE CORTES...
echo =================================================================
echo.
python run_pipeline.py
echo.
pause
goto menu

:status
cls
python run_pipeline.py --status
echo.
pause
goto menu

:stop
cls
python run_pipeline.py --stop
echo.
pause
goto menu
