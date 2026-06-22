@echo off
REM ─────────────────────────────────────────────────────────
REM  run_evening.bat — 장 마감 후 실행 (Task Scheduler 등록용)
REM  실행 시각: 매일 오후 4:30 권장
REM ─────────────────────────────────────────────────────────

cd /d "%~dp0"
python run_agent.py --mode evening >> run_log.txt 2>&1
