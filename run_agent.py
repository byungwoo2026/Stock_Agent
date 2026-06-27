"""
run_agent.py — 에이전트 통합 실행기
─────────────────────────────────────
Task Scheduler / cron 에서 이 파일 하나만 호출하면 됩니다.

장 마감 후 (예: 매일 16:30):
    python run_agent.py --mode evening

다음 날 아침 장 전 (예: 매일 08:50):
    python run_agent.py --mode morning

수동 전체 실행:
    python run_agent.py --mode all
"""

import sys
# Windows CP949 인코딩 에러 방지용 UTF-8 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import argparse
import datetime
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from agent_core        import run_agent
from validate_predictions import run_validation
from email_notify      import send_email as send_kakao_message

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")   # 배포 후 .env 에 설정
PREDICTIONS_FILE = BASE_DIR / "predictions_log.json"
LOG_FILE = BASE_DIR / "run_log.txt"


# ══════════════════════════════════════════════════════════
# 로깅
# ══════════════════════════════════════════════════════════

def log(msg: str):
    ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ══════════════════════════════════════════════════════════
# 예측 로그에서 카카오 요약 생성
# ══════════════════════════════════════════════════════════

def build_kakao_summary() -> dict:
    """
    predictions_log.json 의 오늘 데이터를 카카오 메시지용 dict 로 변환
    """
    if not PREDICTIONS_FILE.exists():
        return {"top_picks": [], "hit_rate_7d": "N/A"}

    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        log_data = json.load(f)

    today_str = datetime.date.today().isoformat()
    entries   = log_data.get(today_str, [])

    # 7일 적중률 계산 (전체 기간)
    all_e    = [e for v in log_data.values() for e in v if e.get("verdict")]
    hit_rate = "N/A"
    if all_e:
        hits     = sum(1 for e in all_e if e["verdict"] == "HIT")
        hit_rate = f"{hits / len(all_e) * 100:.1f}%"

    # 상위 3종목 요약
    top_picks = []
    for e in sorted(entries, key=lambda x: x.get("momentum_score", 0), reverse=True)[:3]:
        top_picks.append({
            "name":      e["name"],
            "code":      e["code"],
            "score":     e.get("momentum_score", 0),
            "theme":     e.get("theme", "-"),
            "signal":    "BUY" if e.get("momentum_score", 0) >= 7 else "HOLD",
            "entry":     e.get("entry_range", "-"),
            "stop_loss": e.get("stop_loss", "-"),
        })

    return {"top_picks": top_picks, "hit_rate_7d": hit_rate}


# ══════════════════════════════════════════════════════════
# 모드별 실행
# ══════════════════════════════════════════════════════════

def run_evening():
    """장 마감 후 실행 — 분석 → 보고서 → 카카오 알림"""
    log("=" * 50)
    log("📡 [저녁 모드] 에이전트 분석 시작")
    log("=" * 50)

    # 1. 에이전트 실행
    try:
        report = run_agent(save_report=True, run_stress=True, top_k=5)
        log("✅ 에이전트 분석 완료")
    except Exception as e:
        log(f"❌ 에이전트 오류: {e}")
        return

    # 2. 카카오톡 발송
    try:
        summary = build_kakao_summary()
        success = send_kakao_message(summary, dashboard_url=DASHBOARD_URL)
        if success:
            log("✅ 카카오톡 발송 완료")
        else:
            log("⚠ 카카오톡 발송 실패 (토큰 확인 필요)")
    except Exception as e:
        log(f"❌ 카카오톡 오류: {e}")

    log("[저녁 모드] 완료")


def run_morning():
    """장 시작 전 실행 — 복기 + 성적표 카카오 발송"""
    log("=" * 50)
    log("🔍 [아침 모드] 예측 검증 시작")
    log("=" * 50)

    # 1. 복기 시스템
    try:
        use_real = os.getenv("USE_REAL_API", "false").lower() == "true"
        scorecard = run_validation(use_real_api=use_real, save_scorecard=True)
        log("✅ 복기 완료")
    except Exception as e:
        log(f"❌ 복기 오류: {e}")
        return

    # 2. 어제 성과 카카오 발송
    try:
        summary = build_kakao_summary()
        # 아침 메시지는 어제 추천 결과 요약
        if summary["top_picks"]:
            summary["top_picks"][0]["name"] = "📋 어제 추천 종목 성과"
        send_kakao_message(summary, dashboard_url=DASHBOARD_URL)
        log("✅ 아침 카카오 발송 완료")
    except Exception as e:
        log(f"❌ 아침 카카오 오류: {e}")

    log("[아침 모드] 완료")


def run_all():
    log("🔄 전체 실행 (저녁 → 아침 순서)")
    run_evening()
    run_morning()


# ══════════════════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="주식 에이전트 실행기")
    parser.add_argument(
        "--mode",
        choices=["evening", "morning", "all"],
        default="all",
        help="실행 모드 (evening=장마감후 / morning=장전 / all=전체)"
    )
    args = parser.parse_args()

    if   args.mode == "evening": run_evening()
    elif args.mode == "morning": run_morning()
    else:                        run_all()
