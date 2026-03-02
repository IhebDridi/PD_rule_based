@echo off
REM Run 100 bots and export data to CSV so you can check if data is correct.
REM No need to reset DB: "otree test" uses a fresh run each time (not the server's db).
echo Running 100 bots and exporting data...
otree test prisoners_dilemma_100 100 --export
echo.
echo Data exported to bot_data folder. Check the CSV to verify your data.
pause
