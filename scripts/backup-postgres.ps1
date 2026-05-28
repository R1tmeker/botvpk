param(
  [string]$ComposeFile = "docker-compose.yml",
  [string]$Service = "postgres",
  [string]$DbName = "vpk_zvezda",
  [string]$DbUser = "vpk",
  [string]$BackupDir = "backups",
  [int]$KeepLast = 14
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backupPath = Join-Path $root $BackupDir
New-Item -ItemType Directory -Force -Path $backupPath | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$containerFile = "/tmp/vpk-zvezda-$stamp.dump"
$localFile = Join-Path $backupPath "vpk-zvezda-$stamp.dump"

Push-Location $root
try {
  docker compose -f $ComposeFile exec -T $Service pg_dump -U $DbUser -d $DbName --format=custom --no-owner --no-acl --file=$containerFile
  docker compose -f $ComposeFile cp "${Service}:$containerFile" $localFile
  docker compose -f $ComposeFile exec -T $Service rm -f $containerFile

  Get-ChildItem -Path $backupPath -Filter "vpk-zvezda-*.dump" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLast |
    Remove-Item -Force

  Write-Host "Backup saved: $localFile"
}
finally {
  Pop-Location
}
