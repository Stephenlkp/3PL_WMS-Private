# Build StarLinks.exe for 64-bit Intel/AMD Windows. Run this on that PC:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -3.12 -m venv (Join-Path $Root "backend\.venv")
}
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "backend\requirements.txt") pyinstaller

Push-Location (Join-Path $Root "frontend")
npm ci
npm run build
Pop-Location

$Release = Join-Path $Root "release"
New-Item -ItemType Directory -Force -Path $Release | Out-Null
$Index = Invoke-RestMethod "https://nodejs.org/dist/index.json"
$NodeVersion = ($Index | Where-Object { $_.version -like "v22.*" } | Select-Object -First 1).version
$NodeZip = Join-Path $Release "node.zip"
Invoke-WebRequest -Uri "https://nodejs.org/dist/$NodeVersion/node-$NodeVersion-win-x64.zip" -OutFile $NodeZip
$NodeExtract = Join-Path $Release "node-extract"
if (Test-Path $NodeExtract) { Remove-Item -Recurse -Force $NodeExtract }
Expand-Archive -Path $NodeZip -DestinationPath $NodeExtract -Force
$NodeExe = Get-ChildItem -Path $NodeExtract -Filter node.exe -Recurse | Select-Object -First 1

$PyDist = Join-Path $Release "pyi"
$PyWork = Join-Path $Release "work"
& $Python -m PyInstaller --noconfirm --distpath $PyDist --workpath $PyWork (Join-Path $Root "packaging\windows\StarLinks.spec")

$Out = Join-Path $Release "StarLinks"
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item (Join-Path $PyDist "StarLinks\*") $Out -Recurse -Force

function Copy-Tree($Source, $Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit $LASTEXITCODE" }
}

$Web = Join-Path $Out "web"
Copy-Tree (Join-Path $Root "frontend\.next\standalone") $Web
Copy-Tree (Join-Path $Root "frontend\.next\static") (Join-Path $Web ".next\static")
Copy-Tree (Join-Path $Root "frontend\public") (Join-Path $Web "public")
New-Item -ItemType Directory -Force -Path (Join-Path $Out "node") | Out-Null
Copy-Item $NodeExe.FullName (Join-Path $Out "node\node.exe") -Force

$Zip = Join-Path $Release "StarLinks-windows-x64.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path $Out -DestinationPath $Zip
Write-Host "Built $(Join-Path $Out 'StarLinks.exe')"
Write-Host "Zip: $Zip"
