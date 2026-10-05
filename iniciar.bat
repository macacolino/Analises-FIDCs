@echo off
rem Sobe o Analisador de FIDCs localmente (Windows). Requer Python 3.11+ e Node 20+.
cd /d "%~dp0"
py -m pip install -q -r backend\requirements.txt || goto erro
if not exist frontend\dist\index.html (
  pushd frontend
  call npm install || goto erro
  call npm run build || goto erro
  popd
)
cd backend
if not exist ..\data\fidc.duckdb (
  echo Primeira execucao: baixando dados da CVM, leva uns 3 minutos...
  py -m fidc.etl || goto erro
)
start "" http://localhost:8000
py -m uvicorn fidc.api.main:app --port 8000
goto :eof
:erro
echo Deu erro. Copie a mensagem acima e mande pro Claude.
pause
