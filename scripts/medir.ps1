# Protocolo de medicion: 3 corridas de la suite por configuracion (nativo y Docker).
# Uso (desde la raiz del proyecto, con Ollama y Docker corriendo):
#   .\scripts\medir.ps1
param(
  [string]$Model = "ministral-3:3b",
  [int]$Runs = 3,
  [double]$Temperature = 0.2,
  [int]$MaxTokens = 512
)

$cores = [Environment]::ProcessorCount
$monitor = Join-Path "results" "monitor.csv"
New-Item -ItemType Directory -Force -Path "results" | Out-Null
if (-not (Test-Path $monitor)) {
  "config,run,peak_ram_gb,avg_cpu_pct,duration_s" | Set-Content -Path $monitor -Encoding ascii
}

if (Test-Path ".\.venv\Scripts\python.exe") {
  $py = (Resolve-Path ".\.venv\Scripts\python.exe").Path
} else {
  $py = "python"
}

function Get-OllamaProcs {
  # El modelo corre en el proceso "llama-server" (lo lanza Ollama); se suman todos
  Get-Process | Where-Object { $_.ProcessName -like "ollama*" -or $_.ProcessName -like "llama*" }
}

function Invoke-Monitored {
  param([string]$Config, [int]$Run, [string]$Exe, [string[]]$ArgList)
  $cpu0 = (Get-OllamaProcs | Measure-Object -Property CPU -Sum).Sum
  if (-not $cpu0) { $cpu0 = 0 }
  $peak = 0
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $p = Start-Process -FilePath $Exe -ArgumentList $ArgList -NoNewWindow -PassThru
  while (-not $p.HasExited) {
    $mem = (Get-OllamaProcs | Measure-Object -Property WorkingSet64 -Sum).Sum
    if ($mem -gt $peak) { $peak = $mem }
    Start-Sleep -Milliseconds 500
  }
  $sw.Stop()
  $cpu1 = (Get-OllamaProcs | Measure-Object -Property CPU -Sum).Sum
  if (-not $cpu1) { $cpu1 = 0 }
  $cpuPct = [math]::Max(0, [math]::Round((($cpu1 - $cpu0) / $sw.Elapsed.TotalSeconds / $cores) * 100, 1))
  $ram = [math]::Round($peak / 1GB, 2)
  $dur = [math]::Round($sw.Elapsed.TotalSeconds, 1)
  "$Config,$Run,$ram,$cpuPct,$dur" | Add-Content -Path $monitor -Encoding ascii
  Write-Host "[$Config corrida $Run] RAM pico=$ram GB  CPU=$cpuPct %  duracion=$dur s"
}

Write-Host "Calentando el modelo (evita contar la carga en frio)..."
& $py src/inference.py --model $Model --prompt "Hola" --max-tokens 8 --output-dir $env:TEMP | Out-Null

$resultsPath = (Get-Location).Path + "/results"
for ($r = 1; $r -le $Runs; $r++) {
  $nativo = @("src/inference.py", "--model", $Model, "--prompts-file", "prompts/suite.json",
              "--temperature", "$Temperature", "--max-tokens", "$MaxTokens", "--tag", "native_run$r")
  Invoke-Monitored -Config "native" -Run $r -Exe $py -ArgList $nativo

  $docker = @("run", "--rm", "-v", "`"${resultsPath}:/app/results`"", "mistral-inference:cpu",
              "--model", $Model, "--prompts-file", "prompts/suite.json",
              "--temperature", "$Temperature", "--max-tokens", "$MaxTokens", "--tag", "docker_run$r")
  Invoke-Monitored -Config "docker" -Run $r -Exe "docker" -ArgList $docker
}
Write-Host "Listo. Ahora ejecute: python src/analizar.py"
