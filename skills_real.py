"""
skills_real.py — 네이버 금융 기반 실제 데이터 스킬 모듈 (수정판 v3)
──────────────────────────────────────────────────────────
컬럼 구조 확인 후 정확하게 수정됨:
  cols[1]  = 종목명
  cols[2]  = 현재가
  cols[4]  = 등락률
  cols[9]  = 거래대금(백만원) → ÷100 → 억원
설치: pip install requests beautifulsoup4 pandas
"""

import re
import time
import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer":         "https://finance.naver.com",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ETF/리츠/펀드 제외 키워드
ETF_KEYWORDS = [
    "KODEX", "TIGER", "RISE", "HANARO", "KOSEF", "SOL", "ACE",
    "KINDEX", "FOCUS", "ARIRANG", "TREX", "MASTER", "하이단기",
    "레버리지", "인버스", "ETF", "리츠", "부동산"
]


@dataclass
class StockMomentum:
    code: str
    name: str
    market: str
    close: int
    change_pct: float
    volume_today: int        # 거래대금 (억)
    volume_prev_avg5: int
    volume_ratio: float
    is_5day_high: bool
    rsi_14: float

@dataclass
class SupplyDemand:
    code: str
    foreign_net: int
    institution_net: int
    individual_net: int
    foreign_consecutive_days: int
    inst_type: str
    is_meaningful: bool
    supply_score: float
    comment: str

@dataclass
class ThemeNews:
    code: str
    headline: str
    theme: str
    theme_persistence: str
    is_fake_filtered: bool
    sentiment_score: float
    dart_risk_flag: bool
    material_type: str
    comment: str


# ══════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════

def _num(text) -> int:
    """문자열 → 정수 (쉼표 제거)"""
    try:
        return int(str(text).replace(",", "").replace(" ", "").strip())
    except Exception:
        return 0

def _pct(text) -> float:
    """등락률 문자열 → float"""
    try:
        return float(re.sub(r"[^0-9.\-+]", "", str(text).strip()))
    except Exception:
        return 0.0

def _get(url: str) -> BeautifulSoup | None:
    try:
        res = SESSION.get(url, timeout=10)
        res.encoding = "euc-kr"
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"  ⚠ 요청 실패: {e}")
        return None

def _is_etf(name: str) -> bool:
    """ETF/리츠 여부 판별"""
    return any(kw in name for kw in ETF_KEYWORDS)

def _calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    s     = pd.Series(prices[::-1])   # 최신순 → 날짜순 변환
    delta = s.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean().iloc[-1]
    loss  = (-delta.clip(upper=0)).rolling(period).mean().iloc[-1]
    if loss == 0:
        return 100.0
    return round(100 - 100 / (1 + gain / loss), 1)


# ══════════════════════════════════════════════════════════
# 네이버 금융 크롤러
# ══════════════════════════════════════════════════════════

def _fetch_market_summary(market: str = "KOSPI", pages: int = 5) -> list[dict]:
    """
    네이버 금융 시장 시세 크롤링
    컬럼: [순위, 종목명, 현재가, 전일비, 등락률, 액면가,
           시가총액, 거래량, 외인비율, 거래대금(백만), PER, ROE]
    """
    market_code = "0" if market == "KOSPI" else "1"
    results = []

    for page in range(1, pages + 1):
        url  = (f"https://finance.naver.com/sise/sise_market_sum.naver"
                f"?sosok={market_code}&page={page}")
        soup = _get(url)
        if not soup:
            break

        rows = soup.select("table.type_2 tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) < 10:
                continue
            try:
                # 종목명 & 코드
                a_tag = cols[1].select_one("a")
                if not a_tag:
                    continue
                name = a_tag.text.strip()
                href = a_tag.get("href", "")
                m    = re.search(r"code=(\d+)", href)
                if not m:
                    continue
                code = m.group(1)

                # ETF/리츠 제외
                if _is_etf(name):
                    continue

                close      = _num(cols[2].text)
                change_pct = _pct(cols[4].text)

                # 거래대금: 백만원 단위 → 억원으로 변환 (÷100)
                vol_million = _num(cols[9].text)
                vol_billion = vol_million // 100   # 억원

                if close > 0 and vol_billion > 0:
                    results.append({
                        "code":       code,
                        "name":       name,
                        "market":     market,
                        "close":      close,
                        "change_pct": change_pct,
                        "volume_amt": vol_billion,   # 억원
                    })
            except Exception:
                continue
        time.sleep(0.3)

    return results


def _fetch_price_history(code: str, pages: int = 2) -> list[int]:
    """네이버 일별 시세 → 종가 리스트 (최신순)"""
    prices = []
    for page in range(1, pages + 1):
        url  = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
        soup = _get(url)
        if not soup:
            break
        for row in soup.select("table.type2 tr"):
            cols = row.select("td")
            if len(cols) < 7:
                continue
            try:
                t = cols[1].text.strip().replace(",", "")
                if t.isdigit():
                    prices.append(int(t))
            except Exception:
                continue
        time.sleep(0.2)
    return prices


def _fetch_supply_demand(code: str) -> dict:
    """네이버 금융 외인/기관 수급 크롤링
    테이블 구조: [날짜, 종가, 전일비, 등락률, 거래량, 기관순매매, 외국인순매매, ...]
    """
    url  = f"https://finance.naver.com/item/frgn.naver?code={code}"
    soup = _get(url)
    if not soup:
        return {"foreign_net": 0, "inst_net": 0, "indiv_net": 0, "consecutive": 0}

    foreign_net = inst_net = indiv_net = consecutive = 0
    prev_foreign_pos = True

    try:
        # type2 테이블 중 두 번째가 외인/기관 순매매 테이블
        type2_tables = soup.select("table.type2")
        if len(type2_tables) < 2:
            return {"foreign_net": 0, "inst_net": 0, "indiv_net": 0, "consecutive": 0}

        rows = type2_tables[1].select("tr")
        data_rows = [r for r in rows if len(r.select("td")) >= 7]

        for i, row in enumerate(data_rows[:5]):
            cols = row.select("td")
            try:
                inst_val    = _num(cols[5].text)   # 기관 순매매
                foreign_val = _num(cols[6].text)   # 외국인 순매매

                if i == 0:
                    inst_net    = inst_val
                    foreign_net = foreign_val
                    indiv_net   = -(inst_val + foreign_val)

                # 외국인 연속 순매수 계산
                if foreign_val > 0 and prev_foreign_pos:
                    consecutive += 1
                else:
                    prev_foreign_pos = False
            except Exception:
                continue
    except Exception as e:
        print(f"  ⚠ 수급 파싱 오류 ({code}): {e}")

    return {"foreign_net": foreign_net, "inst_net": inst_net,
            "indiv_net": indiv_net, "consecutive": consecutive}


def _fetch_news(code: str) -> list[str]:
    """네이버 금융 종목 뉴스"""
    url  = f"https://finance.naver.com/item/news_news.naver?code={code}&page=1"
    soup = _get(url)
    if not soup:
        return []
    return [a.text.strip() for a in soup.select("td.title a") if a.text.strip()][:5]


# ══════════════════════════════════════════════════════════
# SKILL 1 — fetch_market_momentum
# ══════════════════════════════════════════════════════════

def fetch_market_momentum(
    min_volume_billion: int = 500,
    volume_surge_ratio: float = 2.0,
    max_rsi: float = 80.0,
    top_n: int = 20,
) -> list[StockMomentum]:

    print(f"  📡 네이버 금융 시세 수집 중...")
    all_stocks = []

    for market in ["KOSPI", "KOSDAQ"]:
        stocks = _fetch_market_summary(market, pages=5)
        all_stocks.extend(stocks)
        print(f"     {market}: {len(stocks)}종목 (ETF 제외)")
        time.sleep(0.5)

    # 거래대금 기준 상위 20% 임계선
    vols      = sorted([s["volume_amt"] for s in all_stocks if s["volume_amt"] > 0], reverse=True)
    threshold = vols[int(len(vols) * 0.2)] if vols else 500

    # 최소 거래대금 필터
    candidates = [s for s in all_stocks if s["volume_amt"] >= min_volume_billion]
    candidates.sort(key=lambda x: x["volume_amt"], reverse=True)

    print(f"     거래대금 {min_volume_billion}억↑: {len(candidates)}종목 → RSI 계산 중...")

    results = []
    for s in candidates[:60]:
        try:
            prices    = _fetch_price_history(s["code"], pages=2)
            rsi       = _calc_rsi(prices) if len(prices) >= 15 else 50.0

            if rsi > max_rsi:
                continue

            vol_today    = s["volume_amt"]
            is_5day_high = vol_today >= threshold
            vol_ratio    = round(vol_today / max(threshold, 1) * 2, 2)

            if vol_ratio < volume_surge_ratio and not is_5day_high:
                continue

            results.append(StockMomentum(
                code=s["code"], name=s["name"], market=s["market"],
                close=s["close"], change_pct=s["change_pct"],
                volume_today=vol_today, volume_prev_avg5=threshold,
                volume_ratio=vol_ratio, is_5day_high=is_5day_high,
                rsi_14=rsi,
            ))
            time.sleep(0.3)
        except Exception:
            continue

    results.sort(key=lambda x: x.volume_today, reverse=True)
    print(f"  → 1차 필터 통과: {len(results)}종목")
    return results[:top_n]


# ══════════════════════════════════════════════════════════
# SKILL 2 — analyze_supply_demand
# ══════════════════════════════════════════════════════════

def analyze_supply_demand(stocks: list[StockMomentum]) -> list:
    meaningful = []

    for stock in stocks:
        try:
            d = _fetch_supply_demand(stock.code)
            f = d["foreign_net"]
            g = d["inst_net"]
            p = d["indiv_net"]
            c = d["consecutive"]

            supply_score  = round(
                min(max(f + g, 0) / max(stock.volume_today * 100, 1) * 10, 10), 2
            )
            is_meaningful = (f + g) > 0   # 외인 또는 기관 순매수

            if not is_meaningful:
                continue

            comment = (f"외국인 주도 ({f:+,}주), 연속 {c}일 순매수"
                       if f >= g else f"기관 주도 ({g:+,}주)")

            meaningful.append((stock, SupplyDemand(
                code=stock.code, foreign_net=f, institution_net=g,
                individual_net=p, foreign_consecutive_days=c,
                inst_type="기관합계", is_meaningful=True,
                supply_score=supply_score, comment=comment,
            )))
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠ 수급 실패 ({stock.code}): {e}")

    print(f"  → 세력 수급 확인: {len(meaningful)}종목")
    return meaningful


# ══════════════════════════════════════════════════════════
# SKILL 3 — scan_theme_news
# ══════════════════════════════════════════════════════════

_THEMES = {
    "AI 반도체":  ["HBM","AI 서버","엔비디아","반도체","GPU","NPU"],
    "2차전지":    ["배터리","리튬","양극재","전기차","IRA","에코프로"],
    "바이오":     ["FDA","임상","신약","바이오","허가"],
    "방산":       ["방산","수출","NATO","미사일","K방산"],
    "반도체장비": ["장비","CAPEX","식각","증착","세정"],
    "금융":       ["NIM","밸류업","배당","금리","은행"],
    "게임":       ["신작","출시","흥행","게임"],
}
_FAKE = ["루머","소문","카더라","미확인","익명"]
_RISK = ["지연","취소","적자","하향","위험","손실"]


def scan_theme_news(supply_pairs: list) -> list:
    results = []

    for stock, sd in supply_pairs:
        try:
            headlines = _fetch_news(stock.code) or [f"{stock.name} 거래대금 급증"]
            text      = " ".join(headlines) + " " + stock.name
            scores    = {t: sum(1 for k in kws if k in text)
                         for t, kws in _THEMES.items()}
            theme     = max(scores, key=scores.get) if any(scores.values()) else "기타"
            mat       = ("수주" if any(k in text for k in ["수주","계약","수출"]) else
                         "실적" if any(k in text for k in ["실적","영업이익","매출"]) else
                         "정책" if any(k in text for k in ["정책","IRA","보조금"]) else "테마")
            persist   = {"AI 반도체":"장기","방산":"장기","반도체장비":"장기",
                         "2차전지":"중기","바이오":"중기","금융":"중기"}.get(theme,"단기")
            pos       = sum(1 for h in headlines
                            for k in ["수주","승인","계약","증가","호실적"] if k in h)
            neg       = sum(1 for h in headlines for k in _RISK if k in h)
            sentiment = round(min(max((pos-neg)/max(len(headlines),1),-1.0),1.0),2)
            is_fake   = any(s in h for h in headlines for s in _FAKE)
            dart_risk = any(s in h for h in headlines for s in _RISK)
            headline  = f"[주의] 미확인 재료" if is_fake else headlines[0]
            comment   = {"장기":"구조적 수혜 6개월+",
                         "중기":"2~3개월 모멘텀 유효",
                         "단기":"이벤트성 단기 재료"}[persist]
            if dart_risk:
                comment += " ⚠ 리스크 감지"

            results.append((stock, sd, ThemeNews(
                code=stock.code, headline=headline, theme=theme,
                theme_persistence=persist, is_fake_filtered=not is_fake,
                sentiment_score=sentiment, dart_risk_flag=dart_risk,
                material_type=mat, comment=comment,
            )))
            time.sleep(0.2)
        except Exception as e:
            print(f"  ⚠ 뉴스 실패 ({stock.code}): {e}")

    results = [(s,sd,tn) for s,sd,tn in results if tn.is_fake_filtered]
    print(f"  → 재료 확인 + 가짜뉴스 필터 통과: {len(results)}종목")
    return results
