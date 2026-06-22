"""
validate_predictions.py — 예측 추적 + AI 자가 피드백 복기 시스템
──────────────────────────────────────────────────────────────────
기능:
  1. load_predictions      — JSON 예측 로그 로드
  2. fetch_actual_prices   — 실제 수익률 조회 (yfinance 또는 시뮬레이션)
  3. evaluate_predictions  — HIT / MISS / PARTIAL 판정
  4. generate_ai_feedback  — 틀린 예측의 원인 분석 + 자가 피드백
  5. generate_scorecard    — 성적표 마크다운 출력
  6. update_threshold      — 수급 기준 임계값 자동 조정 제안

매일 아침 장 시작 전 실행:
  python validate_predictions.py
"""

import json
import os
import random
import datetime
from typing import Optional

PREDICTIONS_FILE = "predictions_log.json"
SCORECARD_DIR    = "scorecards"

# ══════════════════════════════════════════════════════════
# 1. 예측 로그 로드
# ══════════════════════════════════════════════════════════

def load_predictions() -> dict:
    if not os.path.exists(PREDICTIONS_FILE):
        print(f"❌ 예측 로그 파일 없음: {PREDICTIONS_FILE}")
        print("   agent_core.py를 먼저 실행해 주세요.")
        return {}
    with open(PREDICTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════
# 2. 실제 가격 조회 (시뮬레이션 모드)
# ══════════════════════════════════════════════════════════

def fetch_actual_prices(
    code: str,
    base_price: int,
    date_str: str,
    use_real_api: bool = False,
) -> dict:
    """
    실제 수익률 조회.

    Args:
        use_real_api: True 시 yfinance 사용, False 시 시뮬레이션
    Returns:
        dict: {"1d": price, "7d": price, "30d": price}
    """
    if use_real_api:
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{code}.KS")
            hist   = ticker.history(period="35d")
            if hist.empty:
                ticker = yf.Ticker(f"{code}.KQ")
                hist   = ticker.history(period="35d")
            closes = hist["Close"].dropna().values
            return {
                "1d":  int(closes[1])  if len(closes) > 1  else base_price,
                "7d":  int(closes[7])  if len(closes) > 7  else base_price,
                "30d": int(closes[-1]) if len(closes) > 20 else base_price,
            }
        except Exception as e:
            print(f"  ⚠ yfinance 조회 실패 ({code}): {e} → 시뮬레이션으로 대체")

    # ─── 시뮬레이션 ──────────────────────────────────────
    seed = int(date_str.replace("-", "")) + hash(code) % 1000
    rng  = random.Random(seed)

    def rand_change(mu, sigma):
        return 1 + rng.gauss(mu, sigma) / 100

    return {
        "1d":  int(base_price * rand_change(0.8, 2.5)),
        "7d":  int(base_price * rand_change(1.5, 5.0)),
        "30d": int(base_price * rand_change(2.5, 9.0)),
    }


# ══════════════════════════════════════════════════════════
# 3. 수익률 계산 + HIT/MISS 판정
# ══════════════════════════════════════════════════════════

def evaluate_predictions(log: dict, use_real_api: bool = False) -> dict:
    """
    예측 로그에 실제 수익률 채워 넣고 HIT/MISS 판정.

    판정 기준:
      - HIT     : 7일 수익률 > +3%
      - PARTIAL : 0% ~ +3% 사이
      - MISS    : 음수 수익률
    """
    updated = {}

    for date_str, entries in log.items():
        updated_entries = []
        for e in entries:
            if e.get("return_7d_pct") is not None:
                updated_entries.append(e)   # 이미 평가됨
                continue

            prices = fetch_actual_prices(
                e["code"], e["close_at_signal"], date_str, use_real_api
            )

            r1d  = round((prices["1d"]  - e["close_at_signal"]) / e["close_at_signal"] * 100, 2)
            r7d  = round((prices["7d"]  - e["close_at_signal"]) / e["close_at_signal"] * 100, 2)
            r30d = round((prices["30d"] - e["close_at_signal"]) / e["close_at_signal"] * 100, 2)

            verdict = "HIT" if r7d > 3.0 else "PARTIAL" if r7d >= 0 else "MISS"

            e.update({
                "actual_close_1d":  prices["1d"],
                "actual_close_7d":  prices["7d"],
                "actual_close_30d": prices["30d"],
                "return_1d_pct":    r1d,
                "return_7d_pct":    r7d,
                "return_30d_pct":   r30d,
                "verdict":          verdict,
            })
            updated_entries.append(e)
        updated[date_str] = updated_entries

    # 결과 저장
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    return updated


# ══════════════════════════════════════════════════════════
# 4. AI 자가 피드백 생성
# ══════════════════════════════════════════════════════════

_FEEDBACK_TEMPLATES = {
    "supply_overfit": (
        "수급 과적합 오류: 당일 거래대금 폭발이 세력 유입이 아닌 "
        "개인 단타성 자금이었을 가능성. "
        "→ 외인 연속 순매수 최소 3일 이상 조건 추가 검토."
    ),
    "material_overread": (
        "재료 해석 과대 평가: 뉴스 헤드라인의 긍정 감성에 비해 "
        "실제 실적 영향이 제한적. "
        "→ 수주 계약의 경우 계약 금액 대비 시가총액 비율(수주 레버리지) 필터 추가 검토."
    ),
    "macro_shock": (
        "예상치 못한 대외 악재 발생: 분석 시점 이후 "
        "환율 급등·금리 변동 등 매크로 충격으로 수급 이탈. "
        "→ 이는 모델 오류가 아닌 외부 변수. 스트레스 테스트 민감도 높이기."
    ),
    "tech_position": (
        "기술적 과열 구간 진입 후 추천: RSI가 분석 시점 이후 "
        "단기 급등으로 진입 타점 초과. "
        "→ 시초가 상단 초과 시 미진입 원칙 준수 강화."
    ),
    "theme_exhaustion": (
        "테마 소멸: 단기성 이벤트 재료가 예상보다 빨리 소멸. "
        "→ 단기 재료 종목 목표가 비중을 낮추고, 중기 이상 재료 우선 편입."
    ),
}

def generate_ai_feedback(entries: list[dict]) -> list[dict]:
    """
    MISS 종목에 대해 원인 분석 + 자가 피드백 생성.
    """
    rng = random.Random(42)
    for e in entries:
        if e.get("verdict") == "MISS" and not e.get("ai_feedback"):
            # 원인 추론 로직
            r7d     = e.get("return_7d_pct", 0)
            sup_sc  = e.get("supply_score", 5)
            persist = e.get("theme_persistence", "단기")
            mat     = e.get("material_type", "테마")

            if sup_sc < 4:
                key = "supply_overfit"
            elif mat == "테마" and persist == "단기":
                key = "theme_exhaustion"
            elif r7d < -5:
                key = "macro_shock"
            elif mat == "수주":
                key = "material_overread"
            else:
                key = rng.choice(list(_FEEDBACK_TEMPLATES.keys()))

            e["ai_feedback"] = _FEEDBACK_TEMPLATES[key]

    return entries


# ══════════════════════════════════════════════════════════
# 5. 임계값 자동 조정 제안
# ══════════════════════════════════════════════════════════

def update_threshold(all_entries: list[dict]) -> dict:
    """
    전체 예측 결과를 통계 분석하여 최적 임계값 제안.
    """
    if not all_entries:
        return {}

    hits    = [e for e in all_entries if e.get("verdict") == "HIT"]
    misses  = [e for e in all_entries if e.get("verdict") == "MISS"]

    def safe_avg(lst, key):
        vals = [v[key] for v in lst if v.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    hit_avg_supply   = safe_avg(hits,   "supply_score")
    miss_avg_supply  = safe_avg(misses, "supply_score")
    hit_avg_score    = safe_avg(hits,   "momentum_score")
    miss_avg_score   = safe_avg(misses, "momentum_score")

    suggestions = {}

    if hit_avg_supply and miss_avg_supply:
        new_threshold = round((hit_avg_supply + miss_avg_supply) / 2, 1)
        suggestions["supply_score_min"] = {
            "current":  4.0,
            "suggested": new_threshold,
            "reason": (
                f"HIT 평균 수급점수({hit_avg_supply}) vs "
                f"MISS 평균({miss_avg_supply}) 분석 결과 "
                f"최적 하한선 → {new_threshold} 제안"
            ),
        }

    if hit_avg_score and miss_avg_score:
        new_score_min = round((hit_avg_score + miss_avg_score) / 2, 1)
        suggestions["momentum_score_min"] = {
            "current":   6.0,
            "suggested": new_score_min,
            "reason": (
                f"모멘텀 점수 HIT 평균({hit_avg_score}) / "
                f"MISS 평균({miss_avg_score}) → "
                f"최소 추천 점수 {new_score_min}점 이상으로 조정 검토"
            ),
        }

    # 재료 유형별 적중률
    for mat_type in ["수주", "실적", "정책", "테마"]:
        subset = [e for e in all_entries if e.get("material_type") == mat_type]
        if subset:
            hit_rate = len([e for e in subset if e.get("verdict") == "HIT"]) / len(subset) * 100
            suggestions[f"hit_rate_{mat_type}"] = f"{hit_rate:.0f}% ({len(subset)}건)"

    return suggestions


# ══════════════════════════════════════════════════════════
# 6. 성적표 마크다운 출력
# ══════════════════════════════════════════════════════════

def generate_scorecard(log: dict) -> str:
    """
    전체 기간 성적표 + 날짜별 복기 보고서 생성.
    """
    lines = []
    lines.append("# 📋 AI 애널리스트 추천 성적표 & 복기 보고서")
    lines.append(f"> 생성 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    all_entries = [e for entries in log.values() for e in entries if e.get("verdict")]

    if not all_entries:
        lines.append("> ⚠️ 아직 평가된 예측 데이터가 없습니다.")
        return "\n".join(lines)

    # ─── 전체 통계 ───────────────────────────────────────
    total   = len(all_entries)
    hits    = sum(1 for e in all_entries if e["verdict"] == "HIT")
    partial = sum(1 for e in all_entries if e["verdict"] == "PARTIAL")
    misses  = sum(1 for e in all_entries if e["verdict"] == "MISS")
    hit_rate = hits / total * 100

    avg_r7d  = sum(e["return_7d_pct"]  for e in all_entries if e.get("return_7d_pct")  is not None) / total
    avg_r30d = sum(e["return_30d_pct"] for e in all_entries if e.get("return_30d_pct") is not None) / total

    lines.append("## 📊 전체 성과 요약")
    lines.append("")
    lines.append(f"| 항목 | 수치 |")
    lines.append(f"|------|------|")
    lines.append(f"| 전체 추천 건수 | {total}건 |")
    lines.append(f"| HIT (+3% 이상) | {hits}건 (`{hit_rate:.1f}%`) |")
    lines.append(f"| PARTIAL (0~3%) | {partial}건 |")
    lines.append(f"| MISS (손실)    | {misses}건 |")
    lines.append(f"| 평균 7일 수익률 | `{avg_r7d:+.2f}%` |")
    lines.append(f"| 평균 30일 수익률 | `{avg_r30d:+.2f}%` |")
    lines.append("")

    # ─── 임계값 자동 조정 제안 ───────────────────────────
    thresholds = update_threshold(all_entries)
    if thresholds:
        lines.append("## 🔧 AI 자가 학습 — 임계값 조정 제안")
        lines.append("")
        for key, val in thresholds.items():
            if isinstance(val, dict):
                lines.append(f"### `{key}`")
                lines.append(f"- 현재: `{val['current']}` → 제안: `{val['suggested']}`")
                lines.append(f"- 근거: {val['reason']}")
                lines.append("")
            else:
                lines.append(f"- **재료유형 적중률 [{key.replace('hit_rate_','')}]**: {val}")
        lines.append("")

    # ─── 날짜별 복기 ────────────────────────────────────
    lines.append("## 📅 날짜별 복기")
    lines.append("")

    for date_str, entries in sorted(log.items(), reverse=True):
        evaluated = [e for e in entries if e.get("verdict")]
        if not evaluated:
            continue

        day_hits = sum(1 for e in evaluated if e["verdict"] == "HIT")
        lines.append(f"### {date_str}  (추천 {len(evaluated)}건 / HIT {day_hits}건)")
        lines.append("")

        for e in evaluated:
            verdict = e.get("verdict", "N/A")
            icon    = {"HIT": "🟢", "PARTIAL": "🟡", "MISS": "🔴"}.get(verdict, "⚪")
            r1d     = e.get("return_1d_pct",  0) or 0
            r7d     = e.get("return_7d_pct",  0) or 0
            r30d    = e.get("return_30d_pct", 0) or 0
            score   = e.get("momentum_score", 0)

            lines.append(
                f"#### {icon} {e['name']} ({e['code']}) — {verdict}  |  점수 {score}/10"
            )
            lines.append(
                f"- 진입 기준가: `{e['close_at_signal']:,}원` | "
                f"테마: **{e['theme']}** | 재료: {e['material_type']}"
            )
            lines.append(
                f"- 실제 수익률: 1일 `{r1d:+.2f}%` / 7일 `{r7d:+.2f}%` / 30일 `{r30d:+.2f}%`"
            )

            # AI 자가 피드백
            if e.get("ai_feedback"):
                lines.append(f"- 🤖 **AI 복기**: {e['ai_feedback']}")
            elif verdict == "HIT":
                lines.append(
                    f"- ✅ 수급점수 {e.get('supply_score', '?')} + "
                    f"{e.get('theme_persistence','')} 재료의 시너지 — 분석 로직 유효"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("> ⚠️ 본 성적표는 AI 시뮬레이션 기반입니다. 실투자 성과와 다를 수 있습니다.")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════════

def run_validation(use_real_api: bool = False, save_scorecard: bool = True) -> str:
    """
    매일 아침 실행 — 예측 평가 + 복기 보고서 출력.
    """
    print("=" * 60)
    print("  🔍 예측 검증 & AI 복기 시스템 구동")
    print(f"  실행 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 로드
    print("\n[1] 예측 로그 로드...")
    log = load_predictions()
    if not log:
        return "예측 데이터 없음."

    # 2. 실제 가격 반영
    print(f"\n[2] 실제 수익률 조회 (API: {use_real_api})...")
    log = evaluate_predictions(log, use_real_api=use_real_api)

    # 3. AI 피드백 생성
    print("\n[3] MISS 종목 AI 자가 피드백 생성...")
    all_entries = []
    for entries in log.values():
        entries = generate_ai_feedback(entries)
        all_entries.extend(entries)

    # 업데이트 저장
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    # 4. 성적표 생성
    print("\n[4] 성적표 & 복기 보고서 생성...")
    scorecard = generate_scorecard(log)

    if save_scorecard:
        os.makedirs(SCORECARD_DIR, exist_ok=True)
        date_str  = datetime.date.today().strftime("%Y%m%d")
        filepath  = os.path.join(SCORECARD_DIR, f"scorecard_{date_str}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(scorecard)
        print(f"\n✅ 성적표 저장: {filepath}")

    print("\n" + "=" * 60)
    print("  검증 완료")
    print("=" * 60 + "\n")

    return scorecard


if __name__ == "__main__":
    scorecard = run_validation(use_real_api=False, save_scorecard=True)
    print(scorecard)
