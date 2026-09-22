param(
    [string]$DgxHost = $env:DGX_HOST,
    [string]$SshKey = $env:DGX_SSH_KEY,
    [int]$EsLocalPort = 19201,
    # The DGX Elasticsearch container exposes 9200 through host port 9201.
    [int]$EsRemotePort = 9201,
    [int]$BgeLocalPort = 8103,
    [int]$GemmaLocalPort = 8102,
    [int]$PaddleLocalPort = 28081,
    [int]$PaddleRemotePort = 8081
)

$ErrorActionPreference = 'Stop'

if (-not $DgxHost) {
    throw 'DGX_HOST or -DgxHost is required.'
}
if (-not $SshKey) {
    throw 'DGX_SSH_KEY or -SshKey is required.'
}
if (-not (Test-Path -LiteralPath $SshKey -PathType Leaf)) {
    throw "SSH key does not exist: $SshKey"
}

$arguments = @(
    '-N',
    '-o', 'BatchMode=yes',
    '-o', 'ExitOnForwardFailure=yes',
    '-i', $SshKey,
    '-L', "${EsLocalPort}:127.0.0.1:${EsRemotePort}",
    '-L', "${BgeLocalPort}:127.0.0.1:8103",
    '-L', "${GemmaLocalPort}:127.0.0.1:8102",
    '-L', "${PaddleLocalPort}:127.0.0.1:${PaddleRemotePort}",
    $DgxHost
)

Start-Process -FilePath 'ssh' -ArgumentList $arguments -WindowStyle Hidden
Write-Host "Tunnels requested: ES=$EsLocalPort BGE=$BgeLocalPort Gemma=$GemmaLocalPort Paddle=$PaddleLocalPort"
