$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$keyFile = Join-Path (Split-Path $PSScriptRoot -Parent) 'brightdata_demo\.secrets\brightdata-key.dpapi'
$previousKey = $env:BRIGHTDATA_API_KEY
try {
    if (Test-Path -LiteralPath $keyFile) {
        $secureKey = ConvertTo-SecureString -String ((Get-Content -LiteralPath $keyFile -Raw).Trim())
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        try { $env:BRIGHTDATA_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secureKey.Dispose() }
    }
    & $pythonPath -m wushiland.app
} finally { $env:BRIGHTDATA_API_KEY = $previousKey }
