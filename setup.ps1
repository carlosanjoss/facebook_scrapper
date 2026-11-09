[CmdletBinding()]
param(
    [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Set-Location $ProjectRoot

function Assert-CommandSucceeded {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step falhou com código de saída $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($UvCommand) {
        Write-Host "Criando ambiente Python 3.11 em .venv..."
        & $UvCommand.Source venv --python 3.11 $VenvDir
        Assert-CommandSucceeded "Criação do ambiente virtual"
    } else {
        $PyCommand = Get-Command py -ErrorAction SilentlyContinue
        if (-not $PyCommand) {
            throw "Python 3.11 não foi encontrado. Instale o Python 3.11 ou o uv e execute novamente."
        }
        Write-Host "Criando ambiente Python 3.11 em .venv..."
        & $PyCommand.Source -3.11 -m venv $VenvDir
        Assert-CommandSucceeded "Criação do ambiente virtual"
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Não foi possível criar o ambiente virtual .venv."
}

$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($UvCommand) {
    Write-Host "Instalando dependências Python..."
    & $UvCommand.Source pip install --python $VenvPython -r requirements.txt
    Assert-CommandSucceeded "Instalação das dependências"
} else {
    Write-Host "Instalando dependências Python..."
    & $VenvPython -m pip install --upgrade pip
    Assert-CommandSucceeded "Atualização do pip"
    & $VenvPython -m pip install -r requirements.txt
    Assert-CommandSucceeded "Instalação das dependências"
}

if (-not $SkipBrowser) {
    Write-Host "Instalando o Chromium do Playwright..."
    & $VenvPython -m playwright install chromium
    Assert-CommandSucceeded "Instalação do Chromium"
}

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ".env.example") -Destination (Join-Path $ProjectRoot ".env")
    Write-Host "Arquivo .env criado a partir de .env.example."
}

Write-Host "Executando testes rápidos..."
& $VenvPython -m unittest discover -s tests -v
Assert-CommandSucceeded "Testes rápidos"

Write-Host ""
Write-Host "Projeto preparado. Próximos comandos:"
Write-Host "  .\run.ps1 -Login"
Write-Host "  .\run.ps1 -Once -LimitPages 1 -LimitPosts 1 -NoComments"
