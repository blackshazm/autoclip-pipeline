@echo off
chcp 65001 > nul
title Diagnóstico de Saúde das Contas - AutoClip
color 0b
cd /d "%~dp0"

cls
echo ========================================================
echo   DIAGNÓSTICO DE SAÚDE E SESSÃO DAS CONTAS
echo ========================================================
echo.
python scripts\verify_accounts_health.py
echo.
echo ========================================================
echo  Teste concluído.
echo ========================================================
echo.
pause
