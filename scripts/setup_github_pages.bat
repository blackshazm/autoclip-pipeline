@echo off
chcp 65001 > nul
title AutoClip Engine - Publicação no GitHub
color 0b
cd /d "%~dp0\.."

echo ======================================================================
echo    AutoClip Engine - Publicação no GitHub e Ativação do Pages
echo ======================================================================
echo.

git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Git não encontrado no PATH do sistema!
    echo Instale o Git em https://git-scm.com e tente novamente.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [1/4] Inicializando repositório Git local...
    git init
    git branch -M main
) else (
    echo [1/4] Repositório Git já inicializado.
)

echo [2/4] Adicionando arquivos do projeto...
git add docs/ .github/ .gitignore README.md requirements.txt src/ config/ deploy/ scripts/

echo [3/4] Criando commit...
git commit -m "feat: atualizar estrutura do AutoClip Engine"

echo.
echo ======================================================================
echo  PRÓXIMOS PASSOS PARA ATIVAR O GITHUB PAGES:
echo ======================================================================
echo 1. Crie um repositório no GitHub (ex: autoclip-dashboard)
echo 2. Vincule seu repositório remoto:
echo    git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
echo    git push -u origin main
echo 3. No GitHub: Settings -> Pages:
echo    Selecione 'Deploy from a branch' -> Branch 'main' -> pasta '/docs'
echo ======================================================================
echo.
pause
