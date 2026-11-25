# Choosing a Gemini model

List the models your key can use (PowerShell):

```
(Invoke-RestMethod "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200" -Headers @{"x-goog-api-key"=$env:GEMINI_API_KEY}).models | Where-Object { $_.supportedGenerationMethods -contains "generateContent" } | Select-Object -ExpandProperty name
```

Test which respond right now:

```
$body = '{"contents":[{"parts":[{"text":"Say hi"}]}]}'
foreach ($m in "gemini-3.6-flash","gemini-3.5-flash","gemini-3.5-flash-lite") {
  try {
    $t = Measure-Command { Invoke-RestMethod -Method Post -Uri "https://generativelanguage.googleapis.com/v1beta/models/$($m):generateContent" -Headers @{"x-goog-api-key"=$env:GEMINI_API_KEY} -ContentType "application/json" -Body $body | Out-Null }
    "$m  OK  ($([math]::Round($t.TotalSeconds,1)) s)"
  } catch { "$m  FAILED: $($_.Exception.Message)" }
}
```

Use a fixed version (not `-latest` or `preview`) and the same one for every experiment; write its exact
name in the paper. 503 = overloaded right now, 404 = not available to your key, 429 = free-tier limit.
