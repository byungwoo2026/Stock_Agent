@echo off
cd /d "C:\민병우\공부\3. 코디세이\Stock_클로드\Stock_Agent"
python run_agent.py --mode evening >> run_log.txt 2>&1
git add predictions_log.json >> run_log.txt 2>&1
git commit -m "auto update" >> run_log.txt 2>&1
git push >> run_log.txt 2>&1