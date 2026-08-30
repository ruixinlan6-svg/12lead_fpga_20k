param (
    [Parameter(Mandatory=$true)]
    [string]$Candidate,   # candidate_a_morph, candidate_b_morph_rr, candidate_c_morph_rr_aug

    [Parameter(Mandatory=$false)]
    [int]$GpuId = 2,

    [Parameter(Mandatory=$false)]
    [int]$Seed = 17,

    [Parameter(Mandatory=$false)]
    [string]$RunId = ""
)

if ($RunId -eq "") {
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmm"
    $RunId = "$Timestamp-m2-$Candidate-seed$Seed"
}

$RemoteBase = "C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3"
$PythonExe = "C:\ProgramData\anaconda3\envs\lrx_train\python.exe"
$OutputDir = "$RemoteBase\runs\$RunId"
$ConfigPath = "$RemoteBase\train\ec57\configs\$Candidate.json"

Write-Host "=========================================================="
Write-Host "Launching M2 EC57 Candidate Training on GPU $GpuId"
Write-Host "Candidate: $Candidate"
Write-Host "Seed:      $Seed"
Write-Host "RunId:     $RunId"
Write-Host "Output:    $OutputDir"
Write-Host "=========================================================="

$env:CUDA_VISIBLE_DEVICES = "$GpuId"
$env:PYTHONPATH = "$RemoteBase"

& $PythonExe "$RemoteBase\train\ec57\train_nv_remote.py" --config "$ConfigPath" --output-dir "$OutputDir" --seed $Seed --device "cuda:0"

Write-Host "M2 Candidate Training complete for RunId: $RunId"
