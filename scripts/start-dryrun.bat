@echo off
:: JamTrade — paper trading launcher for Windows Task Scheduler
:: Starts freqtrade in dry-run mode. No real money is ever used.
:: Logs go to user_data\logs\dryrun.log

cd /d "C:\Users\gadia\Downloads\jamtrade-bot\jamtrade-bot"

:: Load secrets from .env (TG_TOKEN, TG_CHAT_ID, etc.)
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)

".venv\Scripts\freqtrade.exe" trade ^
  --config user_data/config-dryrun.json ^
  --strategy MultiConfirmationStrategy ^
  --logfile user_data/logs/dryrun.log
