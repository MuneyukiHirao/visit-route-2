# Run backend pytest and frontend jest
Set-Location -Path (Split-Path $MyInvocation.MyCommand.Path -Parent)
Set-Location ..

Write-Host "== Backend: pytest =="
python -m pytest tests

Write-Host "`n== Frontend: npm test =="
Set-Location frontend
npm test
