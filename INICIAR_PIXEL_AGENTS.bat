@echo off
chcp 65001 > nul
title Pixel Agents • Servidor Standalone Oficial
color 0b

echo =====================================================================
echo 🏢 INICIANDO SERVIDOR STANDALONE DO PIXEL AGENTS
echo =====================================================================
echo.
echo [*] Inicializando o app Pixel Agents via npx na porta padrão...
echo [*] Este app permite usar o Office Layout Editor oficial e pets.
echo.
echo Pressione Ctrl+C para encerrar quando desejar.
echo.

npx -y pixel-agents
pause
