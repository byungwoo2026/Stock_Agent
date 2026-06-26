"""
streamlit_app.py — AI 수급 주도주 대시보드 (Streamlit 버전)
────────────────────────────────────────────────────────────
로컬 실행: streamlit run streamlit_app.py
배포: Streamlit Cloud (share.streamlit.io) 에서 GitHub 연동
"""

import json
import os
import datetime
from pathlib import Path

import streamlit as st
import pandas as pd

# ── 페이지 설정 ────────────────────────────────────────────
st.set_page_config(
    page_title="AI 수급 주도주 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 커스텀 CSS ─────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
  html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
  .metric-card {
    background: #1a1d2e; border: 1px solid #2e3150;
    border-radius: 12px; padding: 18px 20px; text-align: center;
  }
  .metric-label { font-size: 12px; color: #8892a4; margin-bottom: 6px; }
  .metric-value { font-size: 28px; font-weight: 700; }
  .pick-card {
    background: #1a1d2e; border: 1px solid #2e3150;
    border-radius: 12px; padding: 16px 20px; margin-bottom: 12px;
  }
  .badge {
    display: inline-block; padding: 3px 10px; border-radius: 99px;
    font-size: 12px; font-weight: 700;
  }
  .badge-buy  { background: #1e3a5f; color: #60a5fa; }
  .badge-hit  { background: #14532d; color: #22c55e; }
  .badge-miss { background: #7f1d1d; color: #ef4444; }
  .badge-partial { background: #713f12; color: #eab308; }
  .stDataFrame { border-radius: 10px; overflow: hidden; }
  div[data-testid="stMetricValue"] { font-size: 28px !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent

@st.cache_data(ttl=300)   # 5분 캐시
def load_log() -> dict:
    path = BASE_DIR / "predictions_log.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_all_entries(log: dict) -> list:
    return [e for v in log.values() for e in v]


def get_evaluated(log: dict) -> list:
    return [e for e in get_all_entries(log) if e.get("verdict")]


def get_stats(log: dict) -> dict:
    evaluated = get_evaluated(log)
    if not evaluated:
        return {"total": 0, "hit": 0, "miss": 0, "partial": 0,
                "hit_rate": 0.0, "avg_7d": 0.0, "avg_30d": 0.0}
    total   = len(evaluated)
    hits    = sum(1 for e in evaluated if e["verdict"] == "HIT")
    misses  = sum(1 for e in evaluated if e["verdict"] == "MISS")
    partial = sum(1 for e in evaluated if e["verdict"] == "PARTIAL")
    avg_7d  = sum(e.get("return_7d_pct") or 0 for e in evaluated) / total
    avg_30d = sum(e.get("return_30d_pct") or 0 for e in evaluated) / total
    return {
        "total": total, "hit": hits, "miss": misses, "partial": partial,
        "hit_rate": round(hits / total * 100, 1),
        "avg_7d":   round(avg_7d, 2),
        "avg_30d":  round(avg_30d, 2),
    }


# ══════════════════════════════════════════════════════════
# 메인 UI
# ══════════════════════════════════════════════════════════

# ── 헤더 ─────────────────────────────────────────────────
col_title, col_time = st.columns([4, 1])
with col_title:
    st.markdown("## 📊 AI 수급 주도주 대시보드")
with col_time:
    st.markdown(
        f"<div style='text-align:right;color:#8892a4;font-size:13px;padding-top:14px'>"
        f"🟢 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>",
        unsafe_allow_html=True
    )

st.divider()

# ── 데이터 로드 ───────────────────────────────────────────
log   = load_log()
stats = get_stats(log)
today = datetime.date.today().isoformat()
latest_picks = log.get(today, [])
if not latest_picks and log:
    latest_date  = sorted(log.keys())[-1]
    latest_picks = log[latest_date]
else:
    latest_date = today

# ── 새로고침 버튼 ─────────────────────────────────────────
if st.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

st.markdown("### 📈 전체 성과 요약")

# ── 지표 카드 5개 ─────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("전체 추천 건수", f"{stats['total']}건", help="누적 추천 종목 수")
with c2:
    st.metric("7일 적중률",
              f"{stats['hit_rate']}%",
              f"HIT {stats['hit']}건 / MISS {stats['miss']}건")
with c3:
    delta_color = "normal" if stats["avg_7d"] >= 0 else "inverse"
    st.metric("평균 7일 수익률", f"{stats['avg_7d']:+.2f}%")
with c4:
    st.metric("평균 30일 수익률", f"{stats['avg_30d']:+.2f}%")
with c5:
    st.metric("오늘 추천 종목", f"{len(latest_picks)}개", today)

st.divider()

# ── 차트 ─────────────────────────────────────────────────
st.markdown("### 📊 성과 차트")
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**날짜별 평균 7일 수익률**")
    dates   = sorted(log.keys())[-10:]
    returns = []
    for d in dates:
        vals = [e.get("return_7d_pct") or 0
                for e in log.get(d, []) if e.get("return_7d_pct") is not None]
        returns.append(round(sum(vals)/len(vals), 2) if vals else 0)

    if any(r != 0 for r in returns):
        chart_df = pd.DataFrame({"수익률(%)": returns}, index=[d[5:] for d in dates])
        st.bar_chart(chart_df, color="#6366f1")
    else:
        st.info("아직 수익률 데이터가 없습니다.")

with chart_col2:
    st.markdown("**HIT / PARTIAL / MISS 분포**")
    if stats["total"] > 0:
        verdict_df = pd.DataFrame({
            "건수": [stats["hit"], stats["partial"], stats["miss"]]
        }, index=["HIT ✅", "PARTIAL 🟡", "MISS ❌"])
        st.bar_chart(verdict_df, color=["#22c55e"])
    else:
        st.info("아직 판정 데이터가 없습니다.")

st.divider()

# ── 최신 추천 종목 ────────────────────────────────────────
st.markdown(f"### 🏆 최신 추천 종목 — {latest_date}")

if not latest_picks:
    st.warning("오늘 분석 데이터가 없습니다. 에이전트를 실행해 주세요.")
    st.code("python run_agent.py --mode evening")
else:
    for i, pick in enumerate(latest_picks, 1):
        score   = pick.get("momentum_score", 0)
        verdict = pick.get("verdict")
        theme   = pick.get("theme", "-")

        verdict_icon = {"HIT": "🟢", "PARTIAL": "🟡", "MISS": "🔴"}.get(verdict, "⚪")
        score_bar    = "█" * int(score) + "░" * (10 - int(score))

        with st.expander(
            f"{i}. {verdict_icon} **{pick['name']}** ({pick['code']}) "
            f"| 점수 {score}/10 `{score_bar}` | 테마: {theme}",
            expanded=(i <= 3)
        ):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.markdown("**📌 진입 구간**")
                st.code(pick.get("entry_range", "-"))
            with col_b:
                st.markdown("**🛑 손절선**")
                st.code(pick.get("stop_loss", "-"))
            with col_c:
                st.markdown("**🎯 목표가**")
                st.code(pick.get("target", "-"))

            col_d, col_e, col_f = st.columns(3)
            with col_d:
                r1d = pick.get("return_1d_pct")
                st.metric("1일 수익률",
                          f"{r1d:+.2f}%" if r1d is not None else "대기중")
            with col_e:
                r7d = pick.get("return_7d_pct")
                st.metric("7일 수익률",
                          f"{r7d:+.2f}%" if r7d is not None else "대기중")
            with col_f:
                r30d = pick.get("return_30d_pct")
                st.metric("30일 수익률",
                          f"{r30d:+.2f}%" if r30d is not None else "대기중")

            # ── 선정 배경/사유 ────────────────────────────
            if pick.get("selection_reason"):
                st.markdown("**📋 선정 배경 및 사유**")
                reasons = pick["selection_reason"].split(" | ")
                for r in reasons:
                    st.markdown(f"- {r}")

            if pick.get("headline"):
                st.caption(f"📰 핵심 뉴스: {pick['headline']}")

            if pick.get("ai_feedback"):
                st.info(f"🤖 AI 복기: {pick['ai_feedback']}")

st.divider()

# ── 날짜별 히스토리 ───────────────────────────────────────
st.markdown("### 📅 날짜별 추천 히스토리")

all_dates = sorted(log.keys(), reverse=True)
if not all_dates:
    st.info("데이터가 없습니다.")
else:
    selected_date = st.selectbox("날짜 선택", all_dates)
    entries = log.get(selected_date, [])

    if entries:
        rows = []
        for e in entries:
            verdict = e.get("verdict", "대기중")
            icon    = {"HIT": "🟢", "PARTIAL": "🟡", "MISS": "🔴"}.get(verdict, "⚪")
            rows.append({
                "종목":       f"{e['name']} ({e['code']})",
                "테마":       e.get("theme", "-"),
                "점수":       e.get("momentum_score", 0),
                "1일 수익":   f"{e['return_1d_pct']:+.2f}%" if e.get("return_1d_pct") is not None else "-",
                "7일 수익":   f"{e['return_7d_pct']:+.2f}%" if e.get("return_7d_pct") is not None else "-",
                "30일 수익":  f"{e['return_30d_pct']:+.2f}%" if e.get("return_30d_pct") is not None else "-",
                "판정":       f"{icon} {verdict}",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # AI 피드백 표시
        for e in entries:
            if e.get("ai_feedback"):
                st.warning(f"🤖 **{e['name']}** AI 복기: {e['ai_feedback']}")
    else:
        st.info("해당 날짜 데이터 없음")

st.divider()

# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 설정")
    st.markdown("**에이전트 수동 실행**")
    st.code("python run_agent.py --mode evening")
    st.code("python run_agent.py --mode morning")

    st.divider()
    st.markdown("**전체 통계**")
    st.write(f"- 총 추천: {stats['total']}건")
    st.write(f"- 적중률: {stats['hit_rate']}%")
    st.write(f"- 7일 평균: {stats['avg_7d']:+.2f}%")

    st.divider()
    st.caption("⚠ 본 대시보드는 AI 시뮬레이션 기반 참고 자료입니다. 투자 손실 책임은 투자자 본인에게 있습니다.")
