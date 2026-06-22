"""
agent_core.py — 수급 전문 애널리스트 AI 에이전트 (메인)
──────────────────────────────────────────────────────────
Core Workflow:
  1. fetch_market_momentum  → 거래대금 폭발 종목 1차 필터
  2. analyze_supply_demand  → 외인·기관 세력 수급 판별
  3. scan_theme_news        → 재료 파악 + 가짜뉴스 필터
  4. score_momentum         → 종목별 모멘텀 점수 산출 (1~10)
  5. generate_report        → 마크다운 보고서 출력
  6. stress_test            → 환율/금리 시나리오 스트레스 테스트
  7. save_predictions       → 추천 종목 JSON 저장 (복기 시스템 연동)
"""

import json
import os
import datetime
import random
from dataclasses import asdict

from skills import (
    StockMomentum, SupplyDemand, ThemeNews,
    fetch_market_momentum,
    analyze_supply_demand,
    scan_theme_news,
)

# 예측 기록 저장 경로
PREDICTIONS_FILE = "predictions_log.json"
REPORT_DIR       = "reports"


# ══════════════════════════════════════════════════════════
# 1. 모멘텀 점수 산출 (1~10점)
# ══════════════════════════════════════════════════════════

def score_momentum(
    stock: StockMomentum,
    sd: SupplyDemand,
    tn: ThemeNews,
) -> float:
    """
    정량·수급·재료를 종합하여 모멘텀 점수 1~10점 산출.

    가중치:
      - 거래대금 폭발도  25%
      - 수급 점수        30%
      - 재료 감성 점수   20%
      - 기술적 위치      15%  (RSI, 등락률)
      - 테마 지속성      10%
    """
    # ① 거래대금 폭발도 (최대 10점)
    vol_score = min(stock.volume_ratio / 5 * 10, 10)

    # ② 수급 점수 (이미 0~10)
    supply_score = sd.supply_score

    # ③ 재료 감성 점수 → 0~10 변환
    sentiment_score = (tn.sentiment_score + 1) / 2 * 10

    # ④ 기술적 위치 점수 — RSI가 40~65 구간이 이상적
    rsi = stock.rsi_14
    if 40 <= rsi <= 65:
        tech_score = 10.0
    elif rsi < 40:
        tech_score = 7.0 + (rsi - 30) / 10   # 과매도 구간도 가점
    else:
        tech_score = max(0, 10 - (rsi - 65) / 3)  # 과열일수록 감점

    # ⑤ 테마 지속성 점수
    persist_map = {"장기": 10, "중기": 7, "단기": 4}
    persist_score = persist_map.get(tn.theme_persistence, 5)

    # ─── 가중 합산 ───────────────────────────────────────
    total = (
        vol_score      * 0.25 +
        supply_score   * 0.30 +
        sentiment_score* 0.20 +
        tech_score     * 0.15 +
        persist_score  * 0.10
    )

    # DART 리스크 페널티 -1.0
    if tn.dart_risk_flag:
        total -= 1.0

    return round(max(1.0, min(10.0, total)), 1)


# ══════════════════════════════════════════════════════════
# 2. 트레이딩 시나리오 생성
# ══════════════════════════════════════════════════════════

def generate_trading_scenario(stock: StockMomentum, score: float) -> dict:
    """
    내일 시초가 기준 진입 타점과 손절선 자동 산출.

    - 고점 추격 방지: 전일 종가 대비 +1~2% 이내에서만 진입
    - 손절선: 진입가 대비 -3~5% (모멘텀 점수에 따라 차등)
    - 목표가: 진입가 대비 +5~10% (Risk-Reward 최소 1:2)
    """
    close = stock.close
    # 진입가 = 시초가 예상 (종가 ±0.5% 범위)
    entry_low  = int(close * 1.005)
    entry_high = int(close * 1.020)

    # 손절폭: 점수 높을수록 타이트하게
    sl_pct = 0.05 - (score / 10) * 0.02      # 3~5%
    stop_loss = int(entry_low * (1 - sl_pct))

    # 목표가: RR = 2:1 이상 보장
    target_pct = sl_pct * 2.5
    target     = int(entry_low * (1 + target_pct))

    return {
        "entry_range": f"{entry_low:,}원 ~ {entry_high:,}원",
        "stop_loss":   f"{stop_loss:,}원 ({sl_pct*100:.1f}% 하락 시 손절)",
        "target":      f"{target:,}원 (+{target_pct*100:.1f}% 목표)",
        "rr_ratio":    f"1:{target_pct/sl_pct:.1f}",
        "note":        (
            "시초가가 진입 상단을 초과하면 당일 미진입 원칙. "
            "거래량이 전일 대비 50% 미만이면 관망."
        ),
    }


# ══════════════════════════════════════════════════════════
# 3. 보고서 생성 (마크다운)
# ══════════════════════════════════════════════════════════

def generate_report(
    final_list: list[tuple[StockMomentum, SupplyDemand, ThemeNews, float]],
    stress_results: list[dict] | None = None,
) -> str:
    """
    요구사항 지정 형식의 마크다운 보고서 생성.
    """
    today = datetime.date.today().strftime("%Y년 %m월 %d일")
    lines = []

    lines.append(f"# 📊 KOSPI/KOSDAQ 수급 주도주 분석 보고서")
    lines.append(f"> **분석 일자**: {today}  |  **작성**: AI 수급 전문 애널리스트 에이전트")
    lines.append(f"> **필터 조건**: 거래대금 500억↑ · 거래대금 전일比 200%↑ 또는 5일 최고 갱신 · RSI 80 미만 · 세력 수급 확인")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 🏆 최종 추천 종목 ({len(final_list)}개)")
    lines.append("")

    for rank, (stock, sd, tn, score) in enumerate(final_list, 1):
        scenario = generate_trading_scenario(stock, score)

        # ─── 점수 시각화 바 ──────────────────────────────
        filled = int(score)
        score_bar = "█" * filled + "░" * (10 - filled)

        # ─── 수급 방향 아이콘 ────────────────────────────
        sup_icon = "🟢" if sd.foreign_net > 0 and sd.institution_net > 0 else \
                   "🟡" if (sd.foreign_net + sd.institution_net) > 0 else "🔴"

        lines.append(
            f"### {rank}. [{stock.name} ({stock.code})] — "
            f"모멘텀 점수: **{score}/10** `{score_bar}`"
        )
        lines.append(f"> 시장: {stock.market} | 테마: **{tn.theme}** | 재료유형: {tn.material_type}")
        lines.append("")

        # 수급 현황
        lines.append(f"- **수급 현황** {sup_icon}")
        lines.append(
            f"  - 거래대금: **{stock.volume_today:,}억원** "
            f"(5일평균 대비 {stock.volume_ratio:.1f}배 폭발{'🔥' if stock.volume_ratio >= 3 else ''})"
        )
        lines.append(
            f"  - 외국인: `{sd.foreign_net:+,}억` | "
            f"기관: `{sd.institution_net:+,}억` | "
            f"개인: `{sd.individual_net:+,}억`"
        )
        if sd.foreign_consecutive_days > 0:
            lines.append(f"  - 외국인 연속 순매수: **{sd.foreign_consecutive_days}일** ({sd.inst_type} 주도)")
        lines.append(f"  - 수급 해석: {sd.comment}")
        lines.append("")

        # 차트 위치
        rsi_label = (
            "과매수 주의" if stock.rsi_14 >= 70 else
            "중립 — 추가 상승 여력" if stock.rsi_14 >= 50 else
            "과매도 반등 구간"
        )
        lines.append(f"- **차트 위치** 📈")
        lines.append(
            f"  - 당일 등락: `{stock.change_pct:+.2f}%` | 종가: `{stock.close:,}원`"
        )
        lines.append(
            f"  - RSI(14): **{stock.rsi_14}** → {rsi_label}"
        )
        lines.append(
            f"  - 5일 내 거래대금 최고: {'✅ 갱신' if stock.is_5day_high else '❌ 미갱신'}"
        )
        lines.append("")

        # 재료 분석
        dart_flag = " ⚠️ DART 리스크 감지" if tn.dart_risk_flag else ""
        lines.append(f"- **재료 분석** 📰{dart_flag}")
        lines.append(f"  - 핵심 뉴스: {tn.headline}")
        lines.append(
            f"  - 감성 점수: `{tn.sentiment_score:+.2f}` | "
            f"테마 지속성: **{tn.theme_persistence}** "
            f"({'⭐⭐⭐' if tn.theme_persistence == '장기' else '⭐⭐' if tn.theme_persistence == '중기' else '⭐'})"
        )
        lines.append(f"  - {tn.comment}")
        lines.append("")

        # 트레이딩 시나리오
        lines.append(f"- **트레이딩 시나리오** 🎯")
        lines.append(f"  - 진입 구간: `{scenario['entry_range']}`")
        lines.append(f"  - 손절선(Stop-loss): `{scenario['stop_loss']}`")
        lines.append(f"  - 목표가: `{scenario['target']}` (R:R = {scenario['rr_ratio']})")
        lines.append(f"  - ℹ️ {scenario['note']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ─── 스트레스 테스트 섹션 ─────────────────────────────
    if stress_results:
        lines.append("## 🧪 시나리오별 스트레스 테스트")
        lines.append("")
        for result in stress_results:
            lines.append(f"### 시나리오: {result['scenario']}")
            lines.append(f"- 가정: {result['assumption']}")
            lines.append(f"- 섹터별 예상 영향:")
            for sector, impact in result["sector_impacts"].items():
                icon = "🔴" if impact < -3 else "🟡" if impact < 0 else "🟢"
                lines.append(f"  - {sector}: {icon} `{impact:+.1f}%`")
            lines.append(f"- **종합 의견**: {result['conclusion']}")
            lines.append("")

    # ─── 면책 고지 ───────────────────────────────────────
    lines.append("---")
    lines.append("> ⚠️ **면책 고지**: 본 보고서는 AI가 시뮬레이션 데이터를 기반으로 자동 생성한 자료입니다.")
    lines.append("> 실제 투자 결정은 반드시 본인의 판단과 책임 하에 이루어져야 하며, 투자 손실에 대한 책임은 투자자 본인에게 있습니다.")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════
# 4. 스트레스 테스트
# ══════════════════════════════════════════════════════════

def run_stress_test(
    final_list: list[tuple[StockMomentum, SupplyDemand, ThemeNews, float]]
) -> list[dict]:
    """
    거시 변수 충격 시나리오 분석.
    시나리오: ① 환율 +5% 급등  ② 미 국채금리 +100bp  ③ 유가 -20%
    """
    scenarios = [
        {
            "scenario": "원/달러 환율 +5% 급등",
            "assumption": "원화 약세 심화 (예: 1,350원 → 1,418원) 가정",
            "sector_impacts": {
                "반도체·수출주": +4.5,
                "2차전지(소재 수입 의존)": -2.1,
                "바이오(달러 수익)": +3.0,
                "내수·금융": -1.5,
                "게임(글로벌 매출)": +1.8,
            },
            "conclusion": (
                "수출 비중 높은 반도체·바이오에 수혜. "
                "원자재 수입 비중 높은 2차전지·내수주 단기 부담."
            ),
        },
        {
            "scenario": "미 국채 10년물 금리 +100bp 상승",
            "assumption": "연준 추가 긴축 시그널로 글로벌 Risk-Off 심화",
            "sector_impacts": {
                "성장주(바이오·게임)": -5.5,
                "금융·은행": +2.5,
                "반도체(밸류에이션 부담)": -3.0,
                "2차전지(성장주 할인율↑)": -4.0,
                "방산·인프라": +1.0,
            },
            "conclusion": (
                "고밸류 성장주 전반에 할인율 상승 압력. "
                "금융주·저PER 가치주 상대적 수혜. "
                "포트폴리오 내 성장주 비중 축소 검토 필요."
            ),
        },
        {
            "scenario": "국제 유가 -20% 급락",
            "assumption": "글로벌 경기침체 우려로 WTI 배럴당 -20$ 하락",
            "sector_impacts": {
                "정유·화학(마진 개선)": +3.5,
                "항공·운송": +4.0,
                "2차전지(소재가 연동)": -1.5,
                "반도체": +0.5,
                "에너지·자원주": -6.0,
            },
            "conclusion": (
                "에너지 비용 감소로 항공·운송·화학 수혜. "
                "에너지주 직격. 전반적 소비자물가 안정 → 금리 하락 기대로 성장주 반사이익."
            ),
        },
    ]
    return scenarios


# ══════════════════════════════════════════════════════════
# 5. 예측 저장 (validate_predictions.py 연동용)
# ══════════════════════════════════════════════════════════

def save_predictions(
    final_list: list[tuple[StockMomentum, SupplyDemand, ThemeNews, float]]
) -> None:
    """
    추천 종목과 분석 근거를 JSON으로 저장.
    validate_predictions.py가 익일 실제 수익률과 대조하는 데 사용.
    """
    today_str = datetime.date.today().isoformat()

    # 기존 로그 로드
    log = {}
    if os.path.exists(PREDICTIONS_FILE):
        with open(PREDICTIONS_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)

    entries = []
    for stock, sd, tn, score in final_list:
        scenario = generate_trading_scenario(stock, score)
        entries.append({
            "code":              stock.code,
            "name":              stock.name,
            "market":            stock.market,
            "close_at_signal":   stock.close,
            "momentum_score":    score,
            "theme":             tn.theme,
            "material_type":     tn.material_type,
            "theme_persistence": tn.theme_persistence,
            "supply_score":      sd.supply_score,
            "foreign_net":       sd.foreign_net,
            "institution_net":   sd.institution_net,
            "entry_range":       scenario["entry_range"],
            "stop_loss":         scenario["stop_loss"],
            "target":            scenario["target"],
            # 추후 validate_predictions.py가 채워 넣는 필드
            "actual_close_1d":   None,
            "actual_close_7d":   None,
            "actual_close_30d":  None,
            "return_1d_pct":     None,
            "return_7d_pct":     None,
            "return_30d_pct":    None,
            "verdict":           None,   # HIT / MISS / PARTIAL
            "ai_feedback":       None,
        })

    log[today_str] = entries

    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"✅ 예측 기록 저장 완료: {PREDICTIONS_FILE} ({today_str}, {len(entries)}건)")


# ══════════════════════════════════════════════════════════
# 메인 실행 루프
# ══════════════════════════════════════════════════════════

def run_agent(
    save_report: bool = True,
    run_stress:  bool = True,
    top_k:       int  = 5,
) -> str:
    """
    에이전트 전체 파이프라인 실행.

    Args:
        save_report : 보고서를 파일로 저장할지 여부
        run_stress  : 스트레스 테스트 포함 여부
        top_k       : 최종 보고서에 담을 상위 종목 수

    Returns:
        str: 마크다운 보고서 전문
    """
    print("=" * 60)
    print("  📡 수급 전문 AI 애널리스트 에이전트 구동")
    print(f"  실행 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── STEP 1: 거래대금 1차 필터링 ────────────────────────
    print("\n[STEP 1] 거래대금 폭발 종목 스크리닝...")
    momentum_list = fetch_market_momentum(
        min_volume_billion=500,
        volume_surge_ratio=2.0,
        max_rsi=80.0,
        top_n=20,
    )
    print(f"  → 1차 통과: {len(momentum_list)}종목")
    for s in momentum_list:
        print(f"     {s.name}({s.code}) | {s.volume_today:,}억 | "
              f"비율x{s.volume_ratio} | RSI {s.rsi_14}")

    # ── STEP 2: 수급 판별 ───────────────────────────────────
    print("\n[STEP 2] 외인·기관 수급 분석...")
    supply_pairs = analyze_supply_demand(momentum_list)
    print(f"  → 세력 수급 확인: {len(supply_pairs)}종목")
    for s, sd in supply_pairs:
        print(f"     {s.name} | 외인 {sd.foreign_net:+,}억 | "
              f"기관 {sd.institution_net:+,}억 | 수급점수 {sd.supply_score}")

    # ── STEP 3: 재료 스캔 ───────────────────────────────────
    print("\n[STEP 3] 테마·재료 분석 및 가짜뉴스 필터...")
    theme_list = scan_theme_news(supply_pairs)
    print(f"  → 재료 확인 + 가짜뉴스 필터 통과: {len(theme_list)}종목")

    # ── STEP 4: 모멘텀 점수 산출 + 정렬 ────────────────────
    print("\n[STEP 4] 모멘텀 점수 산출...")
    scored = []
    for stock, sd, tn in theme_list:
        score = score_momentum(stock, sd, tn)
        scored.append((stock, sd, tn, score))
        print(f"     {stock.name}: {score}/10")

    scored.sort(key=lambda x: x[3], reverse=True)
    final_list = scored[:top_k]

    # ── STEP 5: 스트레스 테스트 ─────────────────────────────
    stress_results = run_stress_test(final_list) if run_stress else None

    # ── STEP 6: 보고서 생성 ─────────────────────────────────
    print(f"\n[STEP 5] 보고서 생성 (Top {top_k})...")
    report = generate_report(final_list, stress_results)

    # ── STEP 7: 예측 저장 (복기 연동) ───────────────────────
    save_predictions(final_list)

    # ── 파일 저장 ────────────────────────────────────────────
    if save_report:
        os.makedirs(REPORT_DIR, exist_ok=True)
        date_str  = datetime.date.today().strftime("%Y%m%d")
        filepath  = os.path.join(REPORT_DIR, f"report_{date_str}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ 보고서 저장: {filepath}")

    print("\n" + "=" * 60)
    print("  에이전트 실행 완료")
    print("=" * 60 + "\n")

    return report


# ══════════════════════════════════════════════════════════
# 직접 실행
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    report = run_agent(save_report=True, run_stress=True, top_k=5)
    print(report)
