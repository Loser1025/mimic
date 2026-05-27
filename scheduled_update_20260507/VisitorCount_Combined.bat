@echo off
set LOG=C:\Users\Loser\Desktop\-\tamalabo\automation-visitor-shindan\run_log.txt

echo === 実行開始: %date% %time% === >> %LOG%

echo [1/3] 訪問者数集計... >> %LOG%
cd /d "C:\Users\Loser\Desktop\-\tamalabo\automation-visitor-shindan"
python count_visitors_final.py >> %LOG% 2>&1

echo [2/3] 提案日シート更新... >> %LOG%
cd /d "C:\Users\Loser\Desktop\-\tamalabo\proposal-to-sheet"
python run.py >> %LOG% 2>&1

echo [3/4] 面談日シート更新... >> %LOG%
cd /d "C:\Users\Loser\Desktop\-\tamalabo\proposal-to-sheet"
python run_mendan.py >> %LOG% 2>&1

echo [4/4] 面談予約日（未転化）シート更新... >> %LOG%
python run_mendan.py --mitenca >> %LOG% 2>&1

echo === 実行終了: %date% %time% === >> %LOG%