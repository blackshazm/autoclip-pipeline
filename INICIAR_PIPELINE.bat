@echo off
chcp 65001 > nul
title Esteira Autônoma de Cortes - Pipeline
echo =================================================================
echo   INICIANDO ESTEIRA AUTÔNOMA DE CORTES (MODO CONTÍNUO 15 MIN)
echo =================================================================
echo.
cd /d "%~dp0"

python run_pipeline.py

pause
