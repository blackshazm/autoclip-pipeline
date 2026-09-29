@echo off
chcp 65001 > nul
echo ======================================================================
echo    AutoClip Engine - Publicação no GitHub e Ativação do GitHub Pages
echo ======================================================================
echo.

:: Verificar se o git está instalado
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] O Git não está instalado ou não está no PATH do sistema.
    echo Instale o Git em https://git-scm.com/
    pause
    exit /b 1
)

:: Inicializar git se necessário
if not exist ".git" (
    echo [1/4] Inicializando repositório Git local...
    git init
    git branch -M main
) else (
    echo [1/4] Repositório Git já inicializado.
)

echo [2/4] Adicionando arquivos (respeitando .gitignore)...
git add docs/ .github/ .gitignore README.md requirements.txt src/ config/ deploy/

echo [3/4] Criando commit inicial com a página web...
git commit -m "feat: adicionar dashboard interativo e suporte ao GitHub Pages"

echo.
echo ======================================================================
echo    PRÓXIMOS PASSOS:
echo ======================================================================
echo 1. Crie um repositório vazio no seu GitHub (ex: 'autoclip-pipeline')
echo 2. Execute o comando para vincular seu repositório:
echo.
echo    git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
echo    git push -u origin main
echo.
echo 3. Para ativar a página web pública:
echo    No GitHub, vá em: Settings -> Pages
echo    - Build and deployment:
echo      Opção A: Selecione 'Deploy from a branch' -> Branch 'main' -> pasta '/docs'
echo      Opção B: Selecione 'GitHub Actions' (o workflow deploy-pages.yml fará tudo sozinho)
echo.
echo Sua página ficará acessível em:
echo    https://SEU_USUARIO.github.io/SEU_REPOSITORIO/
echo ======================================================================
echo.
pause
