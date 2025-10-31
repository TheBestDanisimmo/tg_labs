param(
  [int]$Port = 8080
)

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
  Write-Host "ngrok is not installed or not in PATH. Download from https://ngrok.com/download" -ForegroundColor Yellow
  exit 1
}

Write-Host "Starting ngrok http $Port ..."
ngrok http $Port

