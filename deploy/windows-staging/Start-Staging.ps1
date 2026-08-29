$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker не найден. Установите и запустите Docker Desktop."
}

if (-not (Test-Path ".env")) {
    throw "Создайте .env из .env.example и замените POSTGRES_PASSWORD."
}

$compose = @("compose", "--env-file", ".env", "--file", "compose.yml")

& docker @compose up --detach database
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось запустить PostgreSQL."
}

& docker @compose run --rm app python -m ke_box_calc.db.migrator up
if ($LASTEXITCODE -ne 0) {
    throw "Миграции не выполнены; приложение не запущено."
}

& docker @compose up --detach app
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось запустить приложение."
}

Write-Host "KE | BOX CALC v2 staging запущен: http://127.0.0.1:8080"
Write-Host "Проверка: http://127.0.0.1:8080/api/v2/health/ready"
