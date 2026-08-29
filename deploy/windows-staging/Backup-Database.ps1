$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$backupDirectory = Join-Path $PSScriptRoot "backups"
New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$containerFile = "/tmp/boxcalc-$timestamp.dump"
$targetFile = Join-Path $backupDirectory "boxcalc-$timestamp.dump"

& docker exec ke-box-calc-v2-postgres sh -c `
    'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --file="$1"' `
    sh $containerFile
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось создать дамп PostgreSQL."
}

& docker cp "ke-box-calc-v2-postgres`:$containerFile" $targetFile
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось скопировать дамп на Windows."
}

& docker exec ke-box-calc-v2-postgres rm -f $containerFile
Write-Host "Резервная копия создана: $targetFile"
