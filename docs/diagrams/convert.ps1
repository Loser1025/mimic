$outputDir = "C:\Users\Loser\Desktop\-\tamalabo\mimic3\docs\diagrams"

$names = @("mimic3_architecture", "dual_mode_sequence", "workflow_graph_state", "react_loop", "class_diagram")
$titles = @(
    "Mimic3 System Architecture (Component Diagram)",
    "DualModelOrchestrator - Thinker/Actor Sequence",
    "WorkflowGraph - PlanStep State Transition",
    "InteractiveOrchestrator - ReAct Loop",
    "Mimic3 Class Diagram"
)

$htmlRows = @()

for ($i = 0; $i -lt $names.Count; $i++) {
    $pngPath = Join-Path $outputDir "$($names[$i]).png"
    $pngBytes = [System.IO.File]::ReadAllBytes($pngPath)
    $base64 = [Convert]::ToBase64String($pngBytes)
    $dataUri = "data:image/png;base64,$base64"
    
    $row = "    <div class=`"diagram`">`n        <h2>$($titles[$i])</h2>`n        <img src=`"$dataUri`" alt=`"$($names[$i])`" />`n        <p class=`"download`"><a href=`"$dataUri`" download=`"$($names[$i]).png`">Download PNG</a></p>`n    </div>"
    $htmlRows += $row
    Write-Output "Encoded: $($names[$i]) ($($base64.Length) chars)"
}

$diagramsHtml = $htmlRows -join "`n"
$dateStr = Get-Date -Format "yyyy-MM-dd HH:mm"

$html = @"
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mimic3 Architecture Diagrams</title>
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: "Segoe UI", "Hiragino Sans", sans-serif;
        background: #1a1a2e;
        color: #e0e0e0;
        padding: 20px;
    }
    h1 {
        text-align: center;
        color: #00d4ff;
        font-size: 2em;
        margin-bottom: 10px;
    }
    .subtitle {
        text-align: center;
        color: #888;
        margin-bottom: 40px;
        font-size: 0.9em;
    }
    .diagram {
        background: #16213e;
        border-radius: 12px;
        padding: 30px;
        margin-bottom: 40px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        border: 1px solid #0f3460;
    }
    .diagram h2 {
        color: #00d4ff;
        margin-bottom: 20px;
        font-size: 1.3em;
        border-bottom: 1px solid #0f3460;
        padding-bottom: 10px;
    }
    .diagram img {
        width: 100%;
        max-width: 1200px;
        height: auto;
        display: block;
        margin: 0 auto;
        border-radius: 8px;
        background: #fafafa;
    }
    .download {
        text-align: right;
        margin-top: 15px;
    }
    .download a {
        color: #00d4ff;
        text-decoration: none;
        font-size: 0.85em;
    }
    .download a:hover { text-decoration: underline; }
    .footer {
        text-align: center;
        color: #555;
        margin-top: 40px;
        font-size: 0.8em;
    }
</style>
</head>
<body>
<h1>Mimic3 Architecture Diagrams</h1>
<p class="subtitle">PlantUML to PNG | Generated: $dateStr</p>

$diagramsHtml

<div class="footer">
    Generated from ARCHITECTURE.puml | Powered by plantuml.com
</div>
</body>
</html>
"@

$htmlPath = Join-Path $outputDir "architecture.html"
[System.IO.File]::WriteAllText($htmlPath, $html, [System.Text.Encoding]::UTF8)
Write-Output "`nHTML saved: $htmlPath ($((Get-Item $htmlPath).Length) bytes)"
