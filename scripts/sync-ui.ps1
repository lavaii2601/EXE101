#!/usr/bin/env pwsh
param()

$ErrorActionPreference = 'Stop'

Write-Host "Syncing ui/ → frontend/ ..."
$repoRoot = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repoRoot 'ui'
$dst = Join-Path $repoRoot 'frontend'

if (-not (Test-Path $src)) {
    Write-Error "Source folder not found: $src"
    exit 1
}

if (-not (Test-Path $dst)) {
    Write-Host "Destination folder not found. Creating: $dst"
    New-Item -ItemType Directory -Path $dst -Force | Out-Null
}

# Copy files, overwrite existing
Get-ChildItem -Path $src -Recurse | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length).TrimStart('\\','/')
    $target = Join-Path $dst $rel
    if ($_.PSIsContainer) {
        if (-not (Test-Path $target)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }
    } else {
        Copy-Item -Path $_.FullName -Destination $target -Force
    }
}

Write-Host "Sync complete: ui/ → frontend/"
