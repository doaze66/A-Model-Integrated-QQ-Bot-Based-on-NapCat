# Render NapCat launcher files from templates (pure ASCII to avoid encoding issues)
param([Parameter(Mandatory = $true)][string]$NapcatDir)

$ErrorActionPreference = 'Stop'
$dirFs = $NapcatDir.TrimEnd('\')
$dirUrl = $dirFs -replace '\\', '/'

# loadNapCat.js -> UTF-8 without BOM (loaded by QQ/Node)
$t1 = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'loadNapCat.js.template') -Raw -Encoding UTF8
$t1 = $t1.Replace('__NAPCAT_DIR__', $dirUrl)
[System.IO.File]::WriteAllText((Join-Path $dirFs 'loadNapCat.js'), $t1, (New-Object System.Text.UTF8Encoding($false)))

# start_napcat.bat -> ASCII (content is pure ASCII)
$t2 = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'start_napcat.bat.template') -Raw -Encoding UTF8
$t2 = $t2.Replace('__NAPCAT_DIR__', $dirFs)
[System.IO.File]::WriteAllText((Join-Path $dirFs 'start_napcat.bat'), $t2, (New-Object System.Text.ASCIIEncoding))

"RENDER_OK -> $dirFs"
