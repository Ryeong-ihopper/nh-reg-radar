param(
    [string]$Config = "temp/operational-config.local.json",
    [string]$InputRoot = "temp/chunking-search-audit-20260921/input",
    [string]$OutputRoot = "temp/chunking-search-audit-20260922-v3v6"
)

$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $project
$cfg = Get-Content -Raw -Encoding utf8 -LiteralPath $Config | ConvertFrom-Json
if ($cfg.parser_runner -ne "nh_parser_fin") {
    throw "Current audit requires parser_runner=nh_parser_fin"
}
$target = [IO.Path]::GetFullPath((Join-Path $project $OutputRoot))
if (Test-Path -LiteralPath $target) {
    throw "Output directory already exists: $target"
}
$python311 = Join-Path $project ".venv311/Scripts/python.exe"
$python313 = [string]$cfg.parser_python
$parserRoot = [string]$cfg.parser_root
$ragPythonPath = "$project/rag-pipeline;$project/rag-pipeline/tools"
$env:NH_OUTPUT_ROOT = Join-Path $target "parser"
$env:NH_MEDIA_DIR = Join-Path $target "media"
foreach ($entry in $cfg.parser_env.psobject.Properties) {
    [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, "Process")
}
foreach ($entry in $cfg.model_env.psobject.Properties) {
    [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, "Process")
}

& $python313 (Join-Path $parserRoot "run.py") --input (Join-Path $InputRoot "deposit") --run-name deposit --with-vlm
if ($LASTEXITCODE -ne 0) { throw "Deposit parsing failed" }
& $python313 (Join-Path $parserRoot "run.py") --input (Join-Path $InputRoot "retirement") --run-name retirement --with-vlm
if ($LASTEXITCODE -ne 0) { throw "Retirement parsing failed" }

$env:PYTHONPATH = $ragPythonPath
$depositFinal = Join-Path $target "parser/deposit/final"
$retirementFinal = Join-Path $target "parser/retirement/final"
& $python311 "rag-pipeline/tools/build_search_inputs_from_parser.py" `
    --p1-dir $depositFinal --p3-dir $depositFinal `
    --output-dir (Join-Path $target "search-inputs/deposit") `
    --product-group "예금성" --product-subtype "예금성상품-입출식"
if ($LASTEXITCODE -ne 0) { throw "Deposit search-input build failed" }
& $python311 "rag-pipeline/tools/build_search_inputs_from_parser.py" `
    --p1-dir $retirementFinal --p3-dir $retirementFinal `
    --output-dir (Join-Path $target "search-inputs/retirement") `
    --product-group "투자성" --product-subtype "투자성상품-퇴직연금 일반"
if ($LASTEXITCODE -ne 0) { throw "Retirement search-input build failed" }

$fine = Join-Path $target "search-inputs/all-evidence-fine.jsonl"
$lines = @(
    [IO.File]::ReadAllLines((Join-Path $target "search-inputs/deposit/evidence_fine.jsonl")),
    [IO.File]::ReadAllLines((Join-Path $target "search-inputs/retirement/evidence_fine.jsonl"))
) | ForEach-Object { $_ }
[IO.File]::WriteAllLines($fine, [string[]]$lines, [Text.UTF8Encoding]::new($false))

& $python311 "rag-pipeline/tools/audit_search_channels.py" `
    --config $Config --fine $fine --output-dir (Join-Path $target "search-audit") `
    --prepare-current-index
if ($LASTEXITCODE -ne 0) { throw "Search audit failed" }

[ordered]@{
    schema = "nh-ad-parse-evidence-v3 + nh-ad-region-review-input-v6"
    output = $target
    fine = $fine
    metrics = (Join-Path $target "search-audit/metrics.json")
} | ConvertTo-Json
