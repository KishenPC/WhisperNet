param(
    [ValidateSet('setup','doctor','test','build','demo','experiment','report','inspect')]
    [string]$Command = 'doctor',
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)
$ErrorActionPreference = 'Stop'
$linuxPath = (& wsl.exe -d Ubuntu-24.04 -- wslpath -a $PSScriptRoot).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Ubuntu-24.04 could not access this project' }
if ($Command -eq 'setup') {
    & wsl.exe -d Ubuntu-24.04 --cd $linuxPath -- bash scripts/setup.sh
} else {
    $environment = (& wsl.exe -d Ubuntu-24.04 -- sh -c 'printf "%s/.local/share/whispernet/venv" "$HOME"').Trim()
    $wslArguments = @('-d','Ubuntu-24.04')
    if ($Command -in @('demo','experiment')) { $wslArguments += @('--user','root') }
    $wslArguments += @('--cd',$linuxPath,'--','env',"WHISPERNET_VENV=$environment",'bash','scripts/run.sh',$Command)
    $wslArguments += $Arguments
    & wsl.exe @wslArguments
}
if ($LASTEXITCODE -ne 0) { throw "WhisperNet $Command failed (exit $LASTEXITCODE)." }
