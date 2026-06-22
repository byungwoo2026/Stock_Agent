@echo off
REM ─────────────────────────────────────────────────────────
REM  run_morning.bat — 장 시작 전 실행 (Task Scheduler 등록용)
REM  실행 시각: 매일 오전 8:50 권장
REM ─────────────────────────────────────────────────────────

cd /d "C:\민병우\공부\3. 코디세이\Stock_클로드\Stock_Agent"

REM 1. 복기 시스템 실행
python run_agent.py --mode morning >> run_log.txt 2>&1

REM 2. 복기 결과 GitHub 자동 업로드 (Streamlit Cloud 자동 반영)
git add predictions_log.json >> run_log.txt 2>&1
git commit -m "복기 업데이트: %date% %time%" >> run_log.txt 2>&1
git push >> run_log.txt 2>&1

echo 완료: %date% %time% >> run_log.txt
