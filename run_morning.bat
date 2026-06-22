@echo off
REM ─────────────────────────────────────────────────────────
REM  run_morning.bat — 장 시작 전 실행 (Task Scheduler 등록용)
REM  실행 시각: 매일 오전 8:50 권장
REM ─────────────────────────────────────────────────────────

cd /d "%~dp0"
python run_agent.py --mode morning >> run_log.txt 2>&1
