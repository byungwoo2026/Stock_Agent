"""
kakao_notify.py — 카카오톡 나에게 보내기 알림 모듈
──────────────────────────────────────────────────
설정 방법 (최초 1회):
  1. https://developers.kakao.com 접속 → 로그인
  2. [내 애플리케이션] → [애플리케이션 추가]
  3. 앱 이름: "주식 에이전트" (임의)
  4. [앱 키] 탭 → REST API 키 복사 → .env 에 KAKAO_REST_API_KEY 에 붙여넣기
  5. 왼쪽 메뉴 [카카오 로그인] → 활성화 ON
  6. [Redirect URI] 에 http://localhost 추가
  7. python kakao_notify.py --auth  실행 → 브라우저 열림 → 동의 → URL 복붙
     → access_token / refresh_token 자동 저장
"""

import os
import json
import argparse
import datetime
import urllib.request
import urllib.parse
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE   = Path(__file__).parent / ".kakao_token.json"
KAKAO_AUTH   = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN  = "https://kauth.kakao.com/oauth/token"
KAKAO_ME_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


# ══════════════════════════════════════════════════════════
# 토큰 관리
# ══════════════════════════════════════════════════════════

def _save_token(data: dict):
    data["saved_at"] = datetime.datetime.now().isoformat()
    TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 토큰 저장 완료: {TOKEN_FILE}")


def _load_token() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


def _refresh_access_token(rest_key: str, token_data: dict) -> str | None:
    """리프레시 토큰으로 액세스 토큰 갱신"""
    params = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "client_id":     rest_key,
        "refresh_token": token_data["refresh_token"],
    }).encode()
    req  = urllib.request.Request(KAKAO_TOKEN, data=params, method="POST")
    try:
        with urllib.request.urlopen(req) as res:
            new_data = json.loads(res.read())
        token_data["access_token"] = new_data["access_token"]
        if "refresh_token" in new_data:
            token_data["refresh_token"] = new_data["refresh_token"]
        _save_token(token_data)
        print("🔄 액세스 토큰 자동 갱신 완료")
        return token_data["access_token"]
    except Exception as e:
        print(f"❌ 토큰 갱신 실패: {e}")
        return None


def get_access_token() -> str | None:
    """유효한 액세스 토큰 반환 (필요 시 자동 갱신)"""
    rest_key = os.getenv("KAKAO_REST_API_KEY")
    if not rest_key:
        print("❌ .env 에 KAKAO_REST_API_KEY 가 없습니다.")
        return None

    token_data = _load_token()
    if not token_data:
        print("❌ 카카오 토큰 없음. 먼저 `python kakao_notify.py --auth` 를 실행하세요.")
        return None

    # 저장 시각 기준 5시간 초과 시 갱신 (액세스 토큰 유효기간 6시간)
    saved_at = datetime.datetime.fromisoformat(token_data.get("saved_at", "2000-01-01"))
    if (datetime.datetime.now() - saved_at).seconds > 18000:
        return _refresh_access_token(rest_key, token_data)

    return token_data["access_token"]


# ══════════════════════════════════════════════════════════
# 최초 인증 (브라우저 흐름)
# ══════════════════════════════════════════════════════════

def authorize():
    """
    최초 1회 실행 — 브라우저 열어서 카카오 로그인 후
    리다이렉트 URL 에서 code 값 추출 → 토큰 발급
    """
    rest_key = os.getenv("KAKAO_REST_API_KEY")
    if not rest_key:
        print("❌ .env 파일에 KAKAO_REST_API_KEY=your_key 를 추가하세요.")
        return

    auth_url = (
        f"{KAKAO_AUTH}?client_id={rest_key}"
        f"&redirect_uri=http://localhost"
        f"&response_type=code"
        f"&scope=talk_message"
    )
    print(f"\n🌐 브라우저를 열고 카카오 로그인을 진행합니다...")
    print(f"   URL: {auth_url}\n")
    webbrowser.open(auth_url)

    print("로그인 완료 후, 브라우저 주소창의 전체 URL 을 복사해 붙여넣으세요.")
    print("(예: http://localhost/?code=XXXXXXXXX)\n")
    redirected = input("URL 붙여넣기: ").strip()

    # code 파싱
    parsed = urllib.parse.urlparse(redirected)
    code   = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
    if not code:
        print("❌ URL 에서 code 를 찾지 못했습니다. 다시 시도해 주세요.")
        return

    # 토큰 발급
    params = urllib.parse.urlencode({
        "grant_type":   "authorization_code",
        "client_id":    rest_key,
        "redirect_uri": "http://localhost",
        "code":         code,
    }).encode()
    req = urllib.request.Request(KAKAO_TOKEN, data=params, method="POST")
    with urllib.request.urlopen(req) as res:
        token_data = json.loads(res.read())

    if "access_token" not in token_data:
        print(f"❌ 토큰 발급 실패: {token_data}")
        return

    _save_token(token_data)
    print("\n✅ 카카오톡 인증 완료! 이제 알림을 보낼 수 있습니다.")


# ══════════════════════════════════════════════════════════
# 메시지 전송
# ══════════════════════════════════════════════════════════

def _build_message(report_summary: dict, dashboard_url: str = "") -> str:
    """카카오톡 텍스트 메시지 본문 생성"""
    today = datetime.date.today().strftime("%Y/%m/%d")
    top   = report_summary.get("top_picks", [])

    lines = [
        f"📊 [{today}] AI 수급 주도주 분석",
        f"{'─' * 28}",
    ]

    for i, pick in enumerate(top[:3], 1):       # 상위 3종목만
        signal_icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(
            pick.get("signal", "HOLD"), "⚪"
        )
        lines.append(
            f"{i}. {signal_icon} {pick['name']} ({pick['code']})\n"
            f"   점수 {pick['score']}/10 | {pick['theme']}\n"
            f"   진입 {pick['entry']} / 손절 {pick['stop_loss']}"
        )

    lines.append(f"{'─' * 28}")
    hit_rate = report_summary.get("hit_rate_7d", "N/A")
    lines.append(f"📈 최근 7일 적중률: {hit_rate}")

    if dashboard_url:
        lines.append(f"\n🔗 대시보드: {dashboard_url}")

    lines.append("\n⚠ 본 알림은 참고용입니다. 투자 책임은 본인에게 있습니다.")
    return "\n".join(lines)


def send_kakao_message(report_summary: dict, dashboard_url: str = "") -> bool:
    """
    카카오톡 나에게 보내기.

    Args:
        report_summary : agent_core.py 실행 결과 요약 dict
        dashboard_url  : 웹 대시보드 URL (선택)
    Returns:
        bool: 성공 여부
    """
    access_token = get_access_token()
    if not access_token:
        return False

    text_body = _build_message(report_summary, dashboard_url)

    template = json.dumps({
        "object_type": "text",
        "text": text_body,
        "link": {
            "web_url":   dashboard_url or "https://kakao.com",
            "mobile_web_url": dashboard_url or "https://kakao.com",
        },
    }, ensure_ascii=False)

    data = urllib.parse.urlencode({"template_object": template}).encode("utf-8")
    req  = urllib.request.Request(
        KAKAO_ME_URL,
        data=data,
        headers={"Authorization": f"Bearer {access_token}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as res:
            result = json.loads(res.read())
        if result.get("result_code") == 0:
            print("✅ 카카오톡 전송 성공!")
            return True
        else:
            print(f"❌ 카카오톡 전송 실패: {result}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"❌ HTTP 오류 {e.code}: {body}")
        return False


# ══════════════════════════════════════════════════════════
# 직접 실행 (인증 or 테스트)
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="카카오톡 알림 모듈")
    parser.add_argument("--auth", action="store_true", help="최초 카카오 인증 실행")
    parser.add_argument("--test", action="store_true", help="테스트 메시지 전송")
    args = parser.parse_args()

    if args.auth:
        authorize()
    elif args.test:
        dummy = {
            "top_picks": [
                {"name": "솔브레인", "code": "357780", "score": 8.6,
                 "theme": "반도체장비", "signal": "BUY",
                 "entry": "310,000원", "stop_loss": "300,000원"},
                {"name": "신한지주", "code": "055550", "score": 8.1,
                 "theme": "금융", "signal": "BUY",
                 "entry": "47,000원", "stop_loss": "45,500원"},
                {"name": "이오테크닉스", "code": "039030", "score": 8.1,
                 "theme": "반도체장비", "signal": "HOLD",
                 "entry": "95,000원", "stop_loss": "92,000원"},
            ],
            "hit_rate_7d": "40.0%",
        }
        send_kakao_message(dummy, dashboard_url="https://your-app.onrender.com")
    else:
        print("사용법: python kakao_notify.py --auth  (최초 인증)")
        print("        python kakao_notify.py --test  (테스트 전송)")
