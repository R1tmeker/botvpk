param(
  [Parameter(Mandatory = $true)]
  [string]$DumpPath,
  [switch]$ConfirmRestore,
  [string]$ComposeFile = "docker-compose.yml",
  [string]$Service = "postgres",
  [string]$DbName = "vpk_zvezda",
  [string]$DbUser = "vpk"
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRestore) {
  throw "Restore is destructive. Re-run with -ConfirmRestore after making a fresh backup."
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dumpFullPath = (Resolve-Path $DumpPath).Path
$containerFile = "/tmp/vpk-zvezda-restore.dump"

Push-Location $root
try {
  docker compose -f $ComposeFile cp $dumpFullPath "${Service}:$containerFile"
  docker compose -f $ComposeFile exec -T $Service sh -c "dropdb -U $DbUser --if-exists $DbName && createdb -U $DbUser $DbName && pg_restore -U $DbUser -d $DbName --clean --if-exists --no-owner --no-acl $containerFile"
  docker compose -f $ComposeFile exec -T $Service rm -f $containerFile
  Write-Host "Database restored from: $dumpFullPath"
}
finally {
  Pop-Location
}
