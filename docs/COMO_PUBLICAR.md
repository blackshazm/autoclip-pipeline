# 🌐 Como Publicar sua Página Web no GitHub Pages

Este guia explica passo a passo como colocar no ar a página web interativa do projeto com um link público gratuito do GitHub Pages.

---

## 🚀 Passo a Passo Rápido

### 1. Criar um Repositório no GitHub
1. Acesse [github.com/new](https://github.com/new).
2. Dê um nome ao seu repositório (ex: `autoclip-pipeline`).
3. Mantenha-o como **Público** (para o GitHub Pages gratuito funcionar sem restrições) e **não** marque "Initialize with README".
4. Clique em **Create repository**.

---

### 2. Enviar o Código Local para o GitHub
No terminal do seu computador (na pasta do projeto `d:\Downloads\haker00\You1`), execute:

```powershell
# Inicializar o repositório local
git init
git branch -M main

# Adicionar os arquivos (o .gitignore já protege suas senhas e credenciais)
git add .
git commit -m "feat: adicionar dashboard e configuracao do GitHub Pages"

# Vincular ao seu repositório remoto (substitua com o seu usuário e nome do repo)
git remote add origin https://github.com/SEU_USUARIO/NOME_DO_REPO.git

# Enviar para o GitHub
git push -u origin main
```

---

### 3. Ativar o GitHub Pages

Você tem duas formas fáceis de ativar:

#### Opção A: Direto pela pasta `/docs` (Mais rápido - 3 cliques)
1. No seu repositório no GitHub, clique na aba **Settings** (Configurações).
2. Na barra lateral esquerda, clique em **Pages**.
3. Em **Build and deployment**:
   - **Source:** selecione `Deploy from a branch`.
   - **Branch:** selecione `main` e a pasta `/docs`.
   - Clique em **Save**.

#### Opção B: Via GitHub Actions (Automático)
O repositório já inclui o arquivo `.github/workflows/deploy-pages.yml`.
1. Em **Settings** -> **Pages**:
   - **Source:** selecione `GitHub Actions`.
2. O workflow fará o deploy automático a cada commit na branch `main`.

---

## 🔗 Seu Link Público

Após cerca de 1 a 2 minutos, o GitHub disponibilizará o link no topo da aba **Settings -> Pages**:

```text
https://<SEU_USUARIO>.github.io/<NOME_DO_REPO>/
```

Você poderá acessar e compartilhar esse link com qualquer pessoa para visualizar o Dashboard interativo, a arquitetura do pipeline e a documentação do projeto.
