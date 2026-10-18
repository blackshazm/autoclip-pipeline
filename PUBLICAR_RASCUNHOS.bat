@echo off
chcp 65001 > nul
title Publicador em Massa de Rascunhos do YouTube Studio
color 0e
cd /d "%~dp0"

:menu
cls
echo ========================================================
echo   PUBLICADOR EM MASSA DE RASCUNHOS - YOUTUBE STUDIO
echo ========================================================
echo.
echo Selecione qual canal deseja publicar os rascunhos:
echo.
echo [1] Publicar Rascunhos do Canal FITNESS (weslleykebra)
echo [2] Publicar Rascunhos do Canal FINANÇAS (Raiz do Éden)
echo [3] Publicar Rascunhos de AMBOS os Canais (Recomendado)
echo [0] Sair
echo.
set /p opcao="Digite a opção desejada [1, 2, 3, 0]: "

if "%opcao%"=="1" goto fit
if "%opcao%"=="2" goto fin
if "%opcao%"=="3" goto all
if "%opcao%"=="0" exit
goto menu

:fit
cls
echo ========================================================
echo  Publicando rascunhos do canal FITNESS...
echo ========================================================
echo.
python scripts\publicar_todos_rascunhos.py --niche fitness --limit 50
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:fin
cls
echo ========================================================
echo  Publicando rascunhos do canal FINANÇAS...
echo ========================================================
echo.
python scripts\publicar_todos_rascunhos.py --niche financas --limit 50
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu

:all
cls
echo ========================================================
echo  Publicando rascunhos de AMBOS os canais...
echo ========================================================
echo.
python scripts\publicar_todos_rascunhos.py --niche all --limit 50
echo.
echo Pressione qualquer tecla para voltar ao menu...
pause >nul
goto menu
