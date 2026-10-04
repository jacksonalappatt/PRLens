param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList
)

python "$PSScriptRoot\main.py" @ArgsList
