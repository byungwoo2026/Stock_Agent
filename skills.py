"""
skills.py — 수급 전문 애널리스트 에이전트 스킬 모듈
────────────────────────────────────────────────────
스킬 3종:
  1. fetch_market_momentum  — 거래대금 폭발 종목 1차 필터링
  2. analyze_supply_demand  — 외인/기관 수급 판별
  3. scan_theme_news        — 재료(모멘텀) 파악 + 가짜뉴스 필터

※ 현재는 시뮬레이션 데이터 기반.
   실전 전환 시 yfinance / Open DART API / 네이버 크롤러로 교체.
"""

import random
import datetime
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════
# 공통 데이터 구조
# ══════════════════════════════════════════════════════════

@dataclass
class StockMomentum:
    """1차 필터링 결과"""
    code: str
    name: str
    market: str                   # KOSPI / KOSDAQ
    close: int                    # 당일 종가 (원)
    change_pct: float             # 등락률 (%)
    volume_today: int             # 당일 거래대금 (억)
    volume_prev_avg5: int         # 최근 5일 평균 거래대금 (억)
    volume_ratio: float           # 거래대금 비율 (오늘 / 5일평균)
    is_5day_high: bool            # 5일 내 거래대금 최고치 갱신 여부
    rsi_14: float                 # RSI(14)


@dataclass
class SupplyDemand:
    """수급 분석 결과"""
    code: str
    foreign_net: int              # 외국인 순매수 (억, 음수=순매도)
    institution_net: int          # 기관 순매수 (억)
    individual_net: int           # 개인 순매수 (억)
    foreign_consecutive_days: int # 외국인 연속 순매수 일수
    inst_type: str                # 주도 기관 유형 (연기금/투신/은행 등)
    is_meaningful: bool           # 세력 수급 여부 (True=외인·기관 주도)
    supply_score: float           # 수급 점수 (0~10)
    comment: str                  # 수급 해석 코멘트


@dataclass
class ThemeNews:
    """재료 분석 결과"""
    code: str
    headline: str                 # 핵심 뉴스 한 줄
    theme: str                    # 테마명
    theme_persistence: str        # 테마 지속성 (단기/중기/장기)
    is_fake_filtered: bool        # 가짜뉴스 필터 통과 여부
    sentiment_score: float        # 감성 점수 (-1.0 ~ +1.0)
    dart_risk_flag: bool          # DART 공시 리스크 감지
    material_type: str            # 재료 유형 (수주/실적/정책/테마)
    comment: str                  # 재료 지속성 평가


# ══════════════════════════════════════════════════════════
# 시뮬레이션 데이터 풀
# ══════════════════════════════════════════════════════════

_STOCK_POOL = [
    ("005930", "삼성전자",     "KOSPI",  75000),
    ("000660", "SK하이닉스",   "KOSPI", 195000),
    ("035420", "NAVER",        "KOSPI", 220000),
    ("373220", "LG에너지솔루션","KOSPI", 310000),
    ("207940", "삼성바이오로직스","KOSPI",840000),
    ("006400", "삼성SDI",      "KOSPI", 290000),
    ("051910", "LG화학",       "KOSPI", 320000),
    ("035720", "카카오",       "KOSPI",  48000),
    ("247540", "에코프로비엠",  "KOSDAQ",250000),
    ("086520", "에코프로",     "KOSDAQ", 95000),
    ("091990", "셀트리온헬스케어","KOSDAQ",80000),
    ("196170", "알테오젠",     "KOSDAQ",240000),
    ("403870", "HPSP",         "KOSDAQ", 60000),
    ("058470", "리노공업",     "KOSDAQ",210000),
    ("357780", "솔브레인",     "KOSDAQ",290000),
    ("112040", "위메이드",     "KOSDAQ", 35000),
    ("263750", "펄어비스",     "KOSDAQ", 42000),
    ("039030", "이오테크닉스", "KOSDAQ", 98000),
    ("316140", "우리금융지주", "KOSPI",  16000),
    ("055550", "신한지주",     "KOSPI",  47000),
]

_THEMES = {
    "AI 반도체": ("HBM·AI 서버 수요 폭발에 따른 메모리 공급 타이트 전망", "장기", "수주", 0.85),
    "2차전지":   ("북미 IRA 보조금 적용 가속화로 배터리 수주 기대감 부각", "중기", "정책", 0.70),
    "바이오":    ("FDA 품목허가 승인 임박, 글로벌 파트너사 기술이전 계약 체결", "중기", "수주", 0.78),
    "방산":      ("NATO 회원국 방산 예산 확대 및 수출 수주 모멘텀 지속", "장기", "수주", 0.82),
    "금융":      ("고금리 장기화로 NIM 개선, 밸류업 프로그램 수혜 기대", "중기", "실적", 0.60),
    "게임":      ("신작 사전예약 흥행 및 글로벌 출시 일정 확정", "단기", "테마", 0.55),
    "반도체장비": ("HBM 생산 증설 투자 사이클 수혜, 고객사 CAPEX 확대 수혜", "장기", "실적", 0.88),
    "바이오시밀러":("바이오시밀러 美 론칭 본격화, 오리지널 대비 30% 가격 경쟁력 확보", "중기", "실적", 0.72),
}

_INST_TYPES = ["연기금", "투신(펀드)", "외국계IB", "은행", "보험", "사모펀드"]


# ══════════════════════════════════════════════════════════
# SKILL 1 — fetch_market_momentum
# ══════════════════════════════════════════════════════════

def fetch_market_momentum(
    min_volume_billion: int = 500,
    volume_surge_ratio: float = 2.0,
    max_rsi: float = 80.0,
    top_n: int = 20,
) -> list[StockMomentum]:
    """
    거래대금 폭발 종목 1차 필터링.

    Args:
        min_volume_billion  : 최소 거래대금 기준 (억). 기본 500억
        volume_surge_ratio  : 전일 대비 거래대금 폭발 배율. 기본 2.0배 (200%)
        max_rsi             : RSI 과열 상한선. 80 초과 종목 제외
        top_n               : 최대 반환 종목 수

    Returns:
        List[StockMomentum]: 조건 통과 종목 리스트 (거래대금 내림차순)
    """
    random.seed(datetime.date.today().toordinal())   # 날짜 고정 시드
    results = []

    for code, name, market, base_price in _STOCK_POOL:
        vol_today    = random.randint(200, 8000)     # 억 단위
        vol_prev_avg = random.randint(100, 3000)
        ratio        = vol_today / max(vol_prev_avg, 1)
        rsi          = round(random.uniform(28, 88), 1)
        change_pct   = round(random.uniform(-5, 15), 2)
        close        = int(base_price * (1 + change_pct / 100))
        is_5d_high   = random.random() < 0.4

        # ── 필터 조건 ──────────────────────────────────────
        if vol_today < min_volume_billion:
            continue
        if ratio < volume_surge_ratio and not is_5d_high:
            continue
        if rsi > max_rsi:
            continue                                 # 과열 제외

        results.append(StockMomentum(
            code=code, name=name, market=market,
            close=close, change_pct=change_pct,
            volume_today=vol_today, volume_prev_avg5=vol_prev_avg,
            volume_ratio=round(ratio, 2),
            is_5day_high=is_5d_high,
            rsi_14=rsi,
        ))

    results.sort(key=lambda x: x.volume_today, reverse=True)
    return results[:top_n]


# ══════════════════════════════════════════════════════════
# SKILL 2 — analyze_supply_demand
# ══════════════════════════════════════════════════════════

def analyze_supply_demand(stocks: list[StockMomentum]) -> list[tuple[StockMomentum, SupplyDemand]]:
    """
    외인·기관 수급 판별 — 세력 수급 vs 개인 투기성 자금 분류.

    Returns:
        (StockMomentum, SupplyDemand) 튜플 리스트.
        수급이 '의미 있는' 종목만 반환 (is_meaningful=True).
    """
    random.seed(datetime.date.today().toordinal() + 1)
    meaningful = []

    for stock in stocks:
        vol = stock.volume_today
        # 거래대금에 비례한 수급 시뮬레이션
        foreign_net  = random.randint(-int(vol*0.3), int(vol*0.5))
        inst_net     = random.randint(-int(vol*0.2), int(vol*0.4))
        indiv_net    = -(foreign_net + inst_net)           # 잔여=개인

        consecutive  = random.randint(0, 10) if foreign_net > 0 else 0
        inst_type    = random.choice(_INST_TYPES) if inst_net > 0 else "없음"

        # 수급 의미 판별: 외인+기관 합산이 전체의 30% 이상
        total_buy    = max(foreign_net + inst_net, 0)
        supply_score = round(min(total_buy / max(vol, 1) * 10, 10), 2)
        is_meaningful = (foreign_net + inst_net) > vol * 0.30

        if not is_meaningful:
            continue

        # 수급 코멘트 자동 생성
        if foreign_net > inst_net:
            comment = (f"외국인 주도 ({foreign_net:+,}억), "
                       f"연속 순매수 {consecutive}일 — 신뢰도 높음")
        else:
            comment = (f"기관({inst_type}) 주도 ({inst_net:+,}억), "
                       f"외인 소폭 참여 — 중기 수급 유입 가능성")

        sd = SupplyDemand(
            code=stock.code,
            foreign_net=foreign_net,
            institution_net=inst_net,
            individual_net=indiv_net,
            foreign_consecutive_days=consecutive,
            inst_type=inst_type,
            is_meaningful=True,
            supply_score=supply_score,
            comment=comment,
        )
        meaningful.append((stock, sd))

    return meaningful


# ══════════════════════════════════════════════════════════
# SKILL 3 — scan_theme_news
# ══════════════════════════════════════════════════════════

_THEME_MAP = {
    "005930": "AI 반도체", "000660": "AI 반도체",
    "247540": "2차전지",  "373220": "2차전지", "006400": "2차전지", "051910": "2차전지",
    "207940": "바이오",   "091990": "바이오시밀러", "196170": "바이오",
    "403870": "반도체장비","058470": "반도체장비", "357780": "반도체장비",
    "039030": "반도체장비",
    "035420": "AI 반도체",
    "035720": "게임",
    "112040": "게임",     "263750": "게임",
    "316140": "금융",     "055550": "금융",
    "086520": "2차전지",
}

_FAKE_NEWS_KEYWORDS = ["루머", "카더라", "익명", "설", "소문", "예상", "기대감만"]

def scan_theme_news(
    supply_pairs: list[tuple[StockMomentum, SupplyDemand]]
) -> list[tuple[StockMomentum, SupplyDemand, ThemeNews]]:
    """
    재료(모멘텀) 파악 + 가짜뉴스 필터링.

    - 확인된 수주·실적·정책 재료만 통과
    - 루머·테마성 재료는 dart_risk_flag 또는 is_fake_filtered=False 처리

    Returns:
        (StockMomentum, SupplyDemand, ThemeNews) 튜플 리스트.
    """
    random.seed(datetime.date.today().toordinal() + 2)
    results = []

    for stock, sd in supply_pairs:
        theme_key = _THEME_MAP.get(stock.code, random.choice(list(_THEMES.keys())))
        headline, persistence, mat_type, sentiment = _THEMES[theme_key]

        # 가짜뉴스 확률: 테마·게임주에서 높음
        fake_prob = 0.35 if mat_type == "테마" else 0.10
        is_fake   = random.random() < fake_prob

        # DART 리스크 플래그: 바이오·소형주에서 간헐적 발생
        dart_risk = random.random() < 0.15

        # 감성 점수 노이즈
        final_sentiment = round(sentiment + random.uniform(-0.15, 0.10), 2)
        final_sentiment = max(-1.0, min(1.0, final_sentiment))

        # 가짜뉴스 필터 통과 실패 시 헤드라인 교체
        if is_fake:
            headline = f"[루머 필터됨] {stock.name} 관련 미확인 재료 유포 — 공식 확인 불가"

        comment_persist = {
            "장기": "정책·구조적 수혜로 6개월 이상 테마 지속 가능성 높음",
            "중기": "실적 발표 시즌까지 2~3개월 모멘텀 유효",
            "단기": "이벤트성 재료. 1~2주 내 소멸 가능 — 단기 트레이딩 관점 접근",
        }[persistence]

        if dart_risk:
            comment_persist += " ⚠ DART 공시에서 리스크 문구 감지 — 추가 확인 요망"

        tn = ThemeNews(
            code=stock.code,
            headline=headline,
            theme=theme_key,
            theme_persistence=persistence,
            is_fake_filtered=not is_fake,
            sentiment_score=final_sentiment,
            dart_risk_flag=dart_risk,
            material_type=mat_type,
            comment=comment_persist,
        )
        results.append((stock, sd, tn))

    # 가짜뉴스 필터 통과한 종목만 최종 반환
    results = [(s, sd, tn) for s, sd, tn in results if tn.is_fake_filtered]
    return results
