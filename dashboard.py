"""
dashboard.py — 주식 에이전트 웹 대시보드 (Flask)
──────────────────────────────────────────────────
로컬 실행: python dashboard.py
배포: Render.com 에 그대로 push → 자동 배포
"""

import sys
# Windows CP949 인코딩 에러 방지용 UTF-8 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import json
import os
import datetime
from pathlib import Path
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

BASE_DIR         = Path(__file__).parent
PREDICTIONS_FILE = BASE_DIR / "predictions_log.json"
REPORTS_DIR      = BASE_DIR / "reports"


# ══════════════════════════════════════════════════════════
# 데이터 로드 헬퍼
# ══════════════════════════════════════════════════════════

def load_log() -> dict:
    if not PREDICTIONS_FILE.exists():
        return {}
    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_stats(log: dict) -> dict:
    all_e = [e for v in log.values() for e in v if e.get("verdict")]
    if not all_e:
        return {"total": 0, "hit": 0, "miss": 0, "partial": 0,
                "hit_rate": 0, "avg_7d": 0, "avg_30d": 0}
    total   = len(all_e)
    hits    = sum(1 for e in all_e if e["verdict"] == "HIT")
    misses  = sum(1 for e in all_e if e["verdict"] == "MISS")
    partial = sum(1 for e in all_e if e["verdict"] == "PARTIAL")
    avg_7d  = sum(e.get("return_7d_pct",  0) or 0 for e in all_e) / total
    avg_30d = sum(e.get("return_30d_pct", 0) or 0 for e in all_e) / total
    return {
        "total":    total,
        "hit":      hits,
        "miss":     misses,
        "partial":  partial,
        "hit_rate": round(hits / total * 100, 1),
        "avg_7d":   round(avg_7d,  2),
        "avg_30d":  round(avg_30d, 2),
    }


def get_latest_picks(log: dict) -> list:
    if not log:
        return []
    latest_date = sorted(log.keys())[-1]
    return log[latest_date]


def get_recent_dates(log: dict, n: int = 7) -> list:
    return sorted(log.keys())[-n:]


# ══════════════════════════════════════════════════════════
# HTML 템플릿
# ══════════════════════════════════════════════════════════

HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 수급 주도주 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d2e; --card2: #222538;
    --border: #2e3150; --text: #e2e8f0; --muted: #8892a4;
    --green: #22c55e; --red: #ef4444; --yellow: #eab308;
    --blue: #3b82f6; --purple: #a855f7; --accent: #6366f1;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; min-height: 100vh; }

  /* 헤더 */
  header { background: var(--card); border-bottom: 1px solid var(--border);
           padding: 14px 28px; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 18px; font-weight: 700; color: var(--accent); letter-spacing: -0.3px; }
  .last-update { font-size: 12px; color: var(--muted); }
  .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green);
              display: inline-block; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  /* 레이아웃 */
  main { max-width: 1280px; margin: 0 auto; padding: 24px 20px; }
  .section-title { font-size: 13px; color: var(--muted); text-transform: uppercase;
                   letter-spacing: .08em; margin-bottom: 14px; font-weight: 600; }

  /* 지표 카드 그리드 */
  .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 28px; }
  .metric-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
                 padding: 18px 20px; }
  .metric-card .label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
  .metric-card .value { font-size: 28px; font-weight: 700; }
  .metric-card .sub   { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .green { color: var(--green); } .red { color: var(--red); }
  .blue  { color: var(--blue);  } .purple { color: var(--purple); } .yellow { color: var(--yellow); }

  /* 2단 그리드 */
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }
  @media (max-width: 768px) { .grid2 { grid-template-columns: 1fr; } }

  /* 차트 카드 */
  .chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .chart-card h3 { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
  .chart-wrap { position: relative; height: 200px; }

  /* 종목 테이블 */
  .picks-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
                overflow: hidden; margin-bottom: 28px; }
  .picks-card h3 { font-size: 14px; font-weight: 600; padding: 18px 20px 14px; border-bottom: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; }
  th { font-size: 11px; color: var(--muted); text-align: left; padding: 10px 16px;
       background: var(--card2); font-weight: 600; text-transform: uppercase; letter-spacing: .05em; }
  td { padding: 12px 16px; font-size: 13px; border-top: 1px solid var(--border); vertical-align: middle; }
  tr:hover td { background: var(--card2); }

  /* 뱃지 */
  .badge { display: inline-block; padding: 3px 10px; border-radius: 99px; font-size: 11px; font-weight: 700; }
  .badge-hit     { background: #14532d; color: var(--green); }
  .badge-partial { background: #713f12; color: var(--yellow); }
  .badge-miss    { background: #7f1d1d; color: var(--red); }
  .badge-pending { background: var(--card2); color: var(--muted); }
  .badge-buy  { background: #1e3a5f; color: #60a5fa; }
  .badge-hold { background: #2d2b12; color: var(--yellow); }

  /* 점수 바 */
  .score-bar { display: flex; align-items: center; gap: 8px; }
  .bar-bg { flex: 1; height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; max-width: 80px; }
  .bar-fill { height: 100%; border-radius: 3px; background: var(--accent); }

  /* 피드백 박스 */
  .feedback-box { background: #1a1a2e; border-left: 3px solid var(--accent);
                  border-radius: 0 8px 8px 0; padding: 10px 14px; font-size: 12px;
                  color: var(--muted); margin-top: 6px; }

  /* 메인 행 & 상세 행 */
  .main-row { cursor: pointer; transition: background 0.2s; }
  .main-row:hover td { background: var(--card2) !important; }
  .detail-row td { background: #131625 !important; border-top: none !important; }
  
  /* 상세 보기 화살표 회전 */
  .toggle-icon { display: inline-block; transition: transform 0.2s; color: var(--muted); font-size: 10px; }
  .main-row.expanded .toggle-icon { transform: rotate(180deg); color: var(--accent); }

  /* 상세 컨테이너 */
  .detail-container {
    padding: 20px;
    border-radius: 8px;
    background: var(--card);
    border: 1px solid var(--border);
    animation: fadeIn 0.25s ease-out;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(-5px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* 상세 그리드 */
  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }
  @media (max-width: 768px) {
    .detail-grid { grid-template-columns: 1fr; }
  }

  /* 상세 카드 */
  .detail-card {
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
  }
  .detail-card h4 {
    font-size: 13px;
    color: var(--accent);
    margin-bottom: 10px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .detail-card-content {
    font-size: 12px;
    color: #cbd5e1;
    line-height: 1.6;
  }

  /* 배지 그룹 */
  .badge-group {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  .badge-theme-detail { background: #1e1b4b; color: #a5b4fc; font-size: 11px; padding: 2px 8px; border-radius: 4px; }
  .badge-mat-detail { background: #064e3b; color: #6ee7b7; font-size: 11px; padding: 2px 8px; border-radius: 4px; }
  .badge-pers-detail { background: #7c2d12; color: #ffedd5; font-size: 11px; padding: 2px 8px; border-radius: 4px; }

  /* 수급 현황 리스트 */
  .supply-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .supply-item {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    padding-bottom: 4px;
    border-bottom: 1px dashed var(--border);
  }
  .supply-item:last-child { border-bottom: none; }

  /* 상세 선정 이유 박스 */
  .reason-box-new {
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    margin-top: 14px;
  }
  .reason-box-new h4 {
    font-size: 13px;
    color: var(--green);
    margin-bottom: 10px;
    font-weight: 600;
  }
  .reason-list-new {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .reason-item-new {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12.5px;
    color: #cbd5e1;
    line-height: 1.5;
  }
  .reason-item-new .dot { color: var(--green); font-size: 12px; flex-shrink: 0; }

  /* AI 피드백 박스 */
  .feedback-box-new {
    background: #1e1b4b;
    border-left: 4px solid var(--purple);
    border-radius: 4px 8px 8px 4px;
    padding: 12px 16px;
    font-size: 12.5px;
    color: #e0e7ff;
    margin-top: 14px;
    line-height: 1.6;
  }


  /* 날짜 탭 */
  .date-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .date-tab { padding: 5px 14px; border-radius: 99px; font-size: 12px; cursor: pointer;
              border: 1px solid var(--border); background: transparent; color: var(--muted);
              transition: all .15s; }
  .date-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* 면책 */
  .disclaimer { font-size: 11px; color: var(--muted); text-align: center;
                padding: 20px 0 8px; border-top: 1px solid var(--border); margin-top: 8px; }
</style>
</head>
<body>

<header>
  <h1>📊 AI 수급 주도주 대시보드</h1>
  <span class="last-update"><span class="live-dot"></span>{{ now }}</span>
</header>

<main>

  <!-- ① 지표 요약 -->
  <p class="section-title">전체 성과 요약</p>
  <div class="metrics">
    <div class="metric-card">
      <div class="label">전체 추천 건수</div>
      <div class="value blue">{{ stats.total }}</div>
      <div class="sub">누적 종목</div>
    </div>
    <div class="metric-card">
      <div class="label">7일 적중률</div>
      <div class="value {% if stats.hit_rate >= 50 %}green{% else %}yellow{% endif %}">
        {{ stats.hit_rate }}%
      </div>
      <div class="sub">HIT {{ stats.hit }}건 / MISS {{ stats.miss }}건</div>
    </div>
    <div class="metric-card">
      <div class="label">평균 7일 수익률</div>
      <div class="value {% if stats.avg_7d >= 0 %}green{% else %}red{% endif %}">
        {{ "%+.2f"|format(stats.avg_7d) }}%
      </div>
      <div class="sub">추천 종목 평균</div>
    </div>
    <div class="metric-card">
      <div class="label">평균 30일 수익률</div>
      <div class="value {% if stats.avg_30d >= 0 %}green{% else %}red{% endif %}">
        {{ "%+.2f"|format(stats.avg_30d) }}%
      </div>
      <div class="sub">장기 성과</div>
    </div>
    <div class="metric-card">
      <div class="label">오늘 추천 종목 수</div>
      <div class="value purple">{{ latest_picks|length }}</div>
      <div class="sub">{{ today }}</div>
    </div>
  </div>

  <!-- ② 차트 -->
  <div class="grid2">
    <div class="chart-card">
      <h3>📈 날짜별 평균 7일 수익률</h3>
      <div class="chart-wrap"><canvas id="returnChart"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>🎯 HIT / PARTIAL / MISS 분포</h3>
      <div class="chart-wrap"><canvas id="verdictChart"></canvas></div>
    </div>
  </div>

  <!-- ③ 오늘 추천 종목 -->
  <div class="picks-card">
    <h3>🏆 최신 추천 종목 — {{ today }}</h3>
    <table>
      <thead>
        <tr>
          <th>#</th><th>종목</th><th>테마</th><th>모멘텀 점수</th>
          <th>진입 구간</th><th>손절선</th><th>목표가</th><th>판정</th><th style="width:60px;text-align:center;">상세</th>
        </tr>
      </thead>
      <tbody>
        {% for pick in latest_picks %}
        <tr class="main-row" onclick="toggleDetail('latest-detail-{{ loop.index }}', this)">
          <td style="color:var(--muted)">{{ loop.index }}</td>
          <td>
            <strong>{{ pick.name }}</strong><br>
            <span style="font-size:11px;color:var(--muted)">{{ pick.code }}</span>
          </td>
          <td><span class="badge badge-buy">{{ pick.theme }}</span></td>
          <td>
            <div class="score-bar">
              <span style="font-weight:700;min-width:28px">{{ pick.momentum_score }}</span>
              <div class="bar-bg">
                <div class="bar-fill" style="width:{{ (pick.momentum_score / 10 * 100)|int }}%"></div>
              </div>
            </div>
          </td>
          <td style="font-size:12px">{{ pick.entry_range }}</td>
          <td style="color:var(--red);font-size:12px">{{ pick.stop_loss }}</td>
          <td style="color:var(--green);font-size:12px">{{ pick.target }}</td>
          <td>
            {% if pick.verdict == 'HIT' %}
              <span class="badge badge-hit">HIT</span>
            {% elif pick.verdict == 'MISS' %}
              <span class="badge badge-miss">MISS</span>
            {% elif pick.verdict == 'PARTIAL' %}
              <span class="badge badge-partial">PARTIAL</span>
            {% else %}
              <span class="badge badge-pending">대기중</span>
            {% endif %}
          </td>
          <td style="text-align: center;"><span class="toggle-icon">▼</span></td>
        </tr>
        <tr id="latest-detail-{{ loop.index }}" class="detail-row" style="display: none;">
          <td colspan="9" style="padding: 16px 20px;">
            <div class="detail-container">
              <div class="detail-grid">
                <!-- 📰 재료 및 뉴스 -->
                <div class="detail-card">
                  <h4>📰 재료 및 뉴스 분석</h4>
                  <div class="detail-card-content">
                    {% if pick.headline %}
                      <strong>핵심 뉴스:</strong> {{ pick.headline }}
                    {% else %}
                      <span style="color:var(--muted)">뉴스 정보 없음</span>
                    {% endif %}
                  </div>
                  <div class="badge-group">
                    <span class="badge-theme-detail">테마: {{ pick.theme or '-' }}</span>
                    <span class="badge-mat-detail">재료유형: {{ pick.material_type or '-' }}</span>
                    <span class="badge-pers-detail">지속성: {{ pick.theme_persistence or '-' }}</span>
                  </div>
                </div>
                <!-- 📊 세력 수급 해석 -->
                <div class="detail-card">
                  <h4>📊 세력 수급 현황</h4>
                  <div class="supply-list">
                    <div class="supply-item">
                      <span>외국인 순매매</span>
                      <strong class="{% if pick.foreign_net is not none and pick.foreign_net >= 0 %}green{% else %}red{% endif %}">
                        {{ "{:+,}".format(pick.foreign_net) if pick.foreign_net is not none else '-' }}{{ '주' if (pick.foreign_net and pick.foreign_net|abs > 2000) else '억' if pick.foreign_net is not none else '' }}
                      </strong>
                    </div>
                    <div class="supply-item">
                      <span>기관 순매매</span>
                      <strong class="{% if pick.institution_net is not none and pick.institution_net >= 0 %}green{% else %}red{% endif %}">
                        {{ "{:+,}".format(pick.institution_net) if pick.institution_net is not none else '-' }}{{ '주' if (pick.institution_net and pick.institution_net|abs > 2000) else '억' if pick.institution_net is not none else '' }}
                      </strong>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- ✦ 상세 선정 배경 -->
              {% if pick.selection_reason %}
                <div class="reason-box-new">
                  <h4>✦ 상세 분석 요약</h4>
                  <ul class="reason-list-new">
                    {% for item in pick.selection_reason.split(' | ') %}
                      <li class="reason-item-new"><span class="dot">✦</span><span>{{ item }}</span></li>
                    {% endfor %}
                  </ul>
                </div>
              {% else %}
                <div class="reason-box-new" style="border-left-color: var(--muted);">
                  <p style="font-size:12px; color:var(--muted); margin:0;">선정 사유 정보가 없습니다. (과거 데이터)</p>
                </div>
              {% endif %}
              
              <!-- 🤖 AI 복기 피드백 -->
              {% if pick.ai_feedback %}
                <div class="feedback-box-new">
                  <strong>🤖 AI 복기:</strong> {{ pick.ai_feedback }}
                </div>
              {% endif %}
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- ④ 날짜별 히스토리 -->
  <p class="section-title">날짜별 추천 히스토리</p>
  <div class="date-tabs" id="dateTabs">
    {% for d in dates %}
    <button class="date-tab {% if loop.last %}active{% endif %}"
            onclick="showDate('{{ d }}', this)">{{ d }}</button>
    {% endfor %}
  </div>
  <div id="historyTable"></div>

</main>

<div class="disclaimer" style="margin:0 20px 20px">
  ⚠ 본 대시보드는 AI 시뮬레이션 기반 참고 자료입니다. 실제 투자 손익에 대한 책임은 투자자 본인에게 있습니다.
</div>

<script>
// ── 날짜별 수익률 차트 ──────────────────────────────────
const chartData = {{ chart_data | tojson }};

new Chart(document.getElementById('returnChart'), {
  type: 'bar',
  data: {
    labels: chartData.labels,
    datasets: [{
      label: '7일 평균 수익률(%)',
      data: chartData.returns,
      backgroundColor: chartData.returns.map(v => v >= 0 ? 'rgba(34,197,94,.7)' : 'rgba(239,68,68,.7)'),
      borderRadius: 4,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#8892a4', font: { size: 11 } }, grid: { color: '#2e3150' } },
      y: { ticks: { color: '#8892a4', font: { size: 11 }, callback: v => v + '%' },
           grid: { color: '#2e3150' } }
    }
  }
});

// ── 판정 도넛 차트 ────────────────────────────────────
const vd = {{ verdict_data | tojson }};
new Chart(document.getElementById('verdictChart'), {
  type: 'doughnut',
  data: {
    labels: ['HIT', 'PARTIAL', 'MISS'],
    datasets: [{
      data: [vd.hit, vd.partial, vd.miss],
      backgroundColor: ['rgba(34,197,94,.8)', 'rgba(234,179,8,.8)', 'rgba(239,68,68,.8)'],
      borderWidth: 0,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: 'right', labels: { color: '#e2e8f0', font: { size: 12 }, padding: 14 } }
    },
    cutout: '65%',
  }
});

// ── 상세 행 토글 ──────────────────────────────────────
function toggleDetail(id, row) {
  const detailRow = document.getElementById(id);
  if (!detailRow) return;
  
  const isCollapsed = detailRow.style.display === 'none';
  if (isCollapsed) {
    detailRow.style.display = 'table-row';
    row.classList.add('expanded');
  } else {
    detailRow.style.display = 'none';
    row.classList.remove('expanded');
  }
}

// ── 날짜별 히스토리 테이블 ────────────────────────────
const allLog = {{ all_log | tojson }};

function verdictBadge(v) {
  if (!v) return '<span class="badge badge-pending">대기중</span>';
  const map = { HIT: 'badge-hit', PARTIAL: 'badge-partial', MISS: 'badge-miss' };
  return `<span class="badge ${map[v]||'badge-pending'}">${v}</span>`;
}

function showDate(date, btn) {
  document.querySelectorAll('.date-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const entries = allLog[date] || [];
  if (!entries.length) {
    document.getElementById('historyTable').innerHTML =
      '<p style="color:var(--muted);padding:20px">데이터 없음</p>';
    return;
  }
  const rows = entries.map((e, idx) => {
    // 수급 데이터 포맷팅
    const fNet = e.foreign_net !== undefined && e.foreign_net !== null
      ? (e.foreign_net > 0 ? '+' : '') + Number(e.foreign_net).toLocaleString() + (Math.abs(e.foreign_net) > 2000 ? '주' : '억')
      : '-';
    const iNet = e.institution_net !== undefined && e.institution_net !== null
      ? (e.institution_net > 0 ? '+' : '') + Number(e.institution_net).toLocaleString() + (Math.abs(e.institution_net) > 2000 ? '주' : '억')
      : '-';
      
    const fClass = (e.foreign_net || 0) >= 0 ? 'green' : 'red';
    const iClass = (e.institution_net || 0) >= 0 ? 'green' : 'red';

    // 뉴스 표시
    const newsHtml = e.headline
      ? `<div class="detail-card-content"><strong>핵심 뉴스:</strong> ${e.headline}</div>`
      : '<div class="detail-card-content" style="color:var(--muted)">뉴스 정보 없음</div>';

    // 선정 사유 표시
    let reasonsHtml = '';
    if (e.selection_reason) {
      const items = e.selection_reason.split(' | ');
      reasonsHtml = `
        <div class="reason-box-new">
          <h4>✦ 상세 분석 요약</h4>
          <ul class="reason-list-new">
            ${items.map(item => `<li class="reason-item-new"><span class="dot">✦</span><span>${item}</span></li>`).join('')}
          </ul>
        </div>
      `;
    } else {
      reasonsHtml = `
        <div class="reason-box-new" style="border-left-color: var(--muted);">
          <p style="font-size:12px; color:var(--muted); margin:0;">선정 사유 정보가 없습니다. (과거 데이터)</p>
        </div>
      `;
    }

    // AI 피드백
    const feedbackHtml = e.ai_feedback
      ? `<div class="feedback-box-new"><strong>🤖 AI 복기:</strong> ${e.ai_feedback}</div>`
      : '';

    return `
    <tr class="main-row" onclick="toggleDetail('history-detail-${idx}', this)">
      <td><strong>${e.name}</strong><br><span style="font-size:11px;color:var(--muted)">${e.code}</span></td>
      <td><span class="badge badge-buy">${e.theme||'-'}</span></td>
      <td style="font-weight:700">${e.momentum_score}/10</td>
      <td style="color:${(e.return_1d_pct||0)>=0?'var(--green)':'var(--red)'}">${e.return_1d_pct!=null?(e.return_1d_pct>=0?'+':'')+e.return_1d_pct+'%':'-'}</td>
      <td style="color:${(e.return_7d_pct||0)>=0?'var(--green)':'var(--red)'}">${e.return_7d_pct!=null?(e.return_7d_pct>=0?'+':'')+e.return_7d_pct+'%':'-'}</td>
      <td style="color:${(e.return_30d_pct||0)>=0?'var(--green)':'var(--red)'}">${e.return_30d_pct!=null?(e.return_30d_pct>=0?'+':'')+e.return_30d_pct+'%':'-'}</td>
      <td>${verdictBadge(e.verdict)}</td>
      <td style="text-align: center;"><span class="toggle-icon">▼</span></td>
    </tr>
    <tr id="history-detail-${idx}" class="detail-row" style="display: none;">
      <td colspan="8" style="padding: 16px 20px;">
        <div class="detail-container">
          <div class="detail-grid">
            <!-- 📰 재료 및 뉴스 -->
            <div class="detail-card">
              <h4>📰 재료 및 뉴스 분석</h4>
              ${newsHtml}
              <div class="badge-group">
                <span class="badge-theme-detail">테마: ${e.theme||'-'}</span>
                <span class="badge-mat-detail">재료유형: ${e.material_type||'-'}</span>
                <span class="badge-pers-detail">지속성: ${e.theme_persistence||'-'}</span>
              </div>
            </div>
            <!-- 📊 세력 수급 해석 -->
            <div class="detail-card">
              <h4>📊 세력 수급 현황</h4>
              <div class="supply-list">
                <div class="supply-item">
                  <span>외국인 순매매</span>
                  <strong class="${fClass}">${fNet}</strong>
                </div>
                <div class="supply-item">
                  <span>기관 순매매</span>
                  <strong class="${iClass}">${iNet}</strong>
                </div>
              </div>
            </div>
          </div>
          ${reasonsHtml}
          ${feedbackHtml}
        </div>
      </td>
    </tr>
  `;}).join('');

  document.getElementById('historyTable').innerHTML = `
    <div class="picks-card">
      <table>
        <thead><tr>
          <th>종목</th><th>테마</th><th>점수</th>
          <th>1일 수익</th><th>7일 수익</th><th>30일 수익</th><th>판정</th><th style="width:60px;text-align:center;">상세</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// 최신 날짜 기본 표시
const dates = {{ dates | tojson }};
if (dates.length) {
  const lastTab = document.querySelectorAll('.date-tab');
  if (lastTab.length) showDate(dates[dates.length-1], lastTab[lastTab.length-1]);
}
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════
# 라우트
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    log           = load_log()
    stats         = get_stats(log)
    latest_picks  = get_latest_picks(log)
    dates         = get_recent_dates(log, n=10)
    today         = datetime.date.today().isoformat()
    now           = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 차트 데이터
    chart_labels  = []
    chart_returns = []
    for d in dates:
        entries = log.get(d, [])
        vals    = [e.get("return_7d_pct") or 0 for e in entries if e.get("return_7d_pct") is not None]
        chart_labels.append(d[5:])           # MM-DD 형식
        chart_returns.append(round(sum(vals) / len(vals), 2) if vals else 0)

    return render_template_string(
        HTML,
        stats        = stats,
        latest_picks = latest_picks,
        dates        = dates,
        today        = today,
        now          = now,
        chart_data   = {"labels": chart_labels, "returns": chart_returns},
        verdict_data = {"hit": stats["hit"], "partial": stats["partial"], "miss": stats["miss"]},
        all_log      = log,
    )


@app.route("/api/log")
def api_log():
    return jsonify(load_log())


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats(load_log()))


@app.route("/health")
def health():
    return "OK", 200


# ══════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"🚀 대시보드 실행: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
