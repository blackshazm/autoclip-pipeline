@echo off
title Login YouTube Studio - AutoClip
color 0c
echo ========================================================
echo     CONEXAO AUTOMATICA YOUTUBE STUDIO - AUTOCLIP PIPELINE
echo ========================================================
echo.
echo Abrindo o navegador para voce fazer o login na conta Google...
echo.
cd /d "d:\Downloads\haker00\You1"
python scripts\youtube_login.py
echo.
echo Processo concluido!
pause
