@echo off
:: JamTrade — paper trading launcher for Windows Task Scheduler
:: Starts freqtrade in dry-run mode. No real money is ever used.
:: Logs go to user_data\logs\dryrun.log
:: NOTE: freqtrade's telegram is disabled in config; the .env secrets are
:: only needed by signal_advisor.py, so nothing is loaded here.

cd /d "C:\Users\gadia\Downloads\jamtrade-bot\jamtrade-bot"

".venv\Scripts\freqtrade.exe" trade ^
  --config user_data/config-dryrun.json ^
  --strategy MultiConfirmationStrategy ^
  --logfile user_data/logs/dryrun.log
