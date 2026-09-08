$ErrorActionPreference = 'Stop'
$probeBody = @{
    model = 'knowledge-qwen35:4b'
    messages = @(
        @{ role = 'system'; content = '只依据资料回答，用 [1] 引用，不输出思考过程。 /no_think' },
        @{ role = 'user'; content = '[1] 北京住宿标准为每人每晚600元。问题：北京住宿标准是多少？ /no_think' }
    )
    temperature = 0.1
    reasoning_effort = 'none'
    max_tokens = 768
    stream = $false
} | ConvertTo-Json -Depth 5
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/v1/chat/completions' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($probeBody)) -TimeoutSec 600
$result.choices | Select-Object finish_reason,@{Name='answer';Expression={$_.message.content}} | ConvertTo-Json -Depth 3
