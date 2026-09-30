$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$destinationRoot = 'D:\Janus'
$running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match '(main\.py|janus|watchdog\.py)'
}
if ($running) { throw 'Feche o Janus e o watchdog antes da migração.' }
if (-not (Test-Path -LiteralPath 'D:\')) { throw 'USB D: indisponível.' }
if (Test-Path -LiteralPath $destinationRoot) { throw 'D:\Janus já existe; não será sobrescrito.' }
$folders = @('memoria_jarvis_v2', 'logs_sistema', 'SKILLS')
New-Item -ItemType Directory -Path $destinationRoot | Out-Null
$verified = 0
foreach ($folder in $folders) {
    $source = Join-Path $sourceRoot $folder
    Copy-Item -LiteralPath $source -Destination $destinationRoot -Recurse
    foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
        $relative = $file.FullName.Substring($sourceRoot.Length + 1)
        $target = Join-Path $destinationRoot $relative
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
            throw "Falha de verificação: $relative. Configuração não alterada."
        }
        $verified++
    }
}
$envFile = Join-Path $sourceRoot '.env'
$content = [IO.File]::ReadAllText($envFile)
foreach ($entry in @(@('JANUS_DATA_DIR', 'D:/Janus'), @('JANUS_DB_PATH', 'D:/Janus/memoria_jarvis_v2'))) {
    $pattern = '(?m)^\s*' + $entry[0] + '\s*=.*$'
    $line = $entry[0] + '=' + $entry[1]
    if ([regex]::IsMatch($content, $pattern)) { $content = [regex]::Replace($content, $pattern, $line) }
    else { $content = $content.TrimEnd() + "`r`n" + $line + "`r`n" }
}
[IO.File]::WriteAllText($envFile, $content, [Text.UTF8Encoding]::new($false))
Write-Output "Migração concluída: $verified arquivos verificados por SHA-256. Originais preservados. Destino: $destinationRoot"
