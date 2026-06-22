"""
email_notify.py — Gmail SMTP 이메일 알림 모듈
──────────────────────────────────────────────
카카오 인증 없이 Gmail 앱 비밀번호만으로 동작합니다.

사전 준비:
  1. Gmail 2단계 인증 활성화
  2. https://myaccount.google.com/apppasswords 에서 앱 비밀번호 발급
  3. .env 파일에 아래 3가지 설정:
       EMAIL_SENDER=내gmail@gmail.com
       EMAIL_APP_PASSWORD=앱비밀번호16자리
       EMAIL_RECIPIENT=받을이메일@gmail.com

테스트:
  python email_notify.py
"""

import smtplib
import datetime
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()


def send_email(
    report_summary: dict,
    dashboard_url: str = "",
    subject_prefix: str = "📊",
) -> bool:
    """
    Gmail SMTP로 분석 결과 HTML 이메일 발송.

    Args:
        report_summary : {top_picks, hit_rate_7d, avg_7d} 딕셔너리
        dashboard_url  : 웹 대시보드 URL (선택)
        subject_prefix : 제목 앞 이모지/텍스트

    Returns:
        bool: 발송 성공 여부
    """
    sender    = os.getenv("EMAIL_SENDER")
    password  = os.getenv("EMAIL_APP_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT")

    if not all([sender, password, recipient]):
        print("❌ .env 파일에 EMAIL_SENDER / EMAIL_APP_PASSWORD / EMAIL_RECIPIENT 를 설정하세요.")
        return False

    today = datetime.date.today().strftime("%Y년 %m월 %d일")
    top   = report_summary.get("top_picks", [])

    # ── 종목 테이블 행 생성 ──────────────────────────────
    rows = ""
    for i, pick in enumerate(top[:5], 1):
        score     = pick.get("score", 0)
        bar_width = int(score / 10 * 100)
        rows += f"""
        <tr style="border-bottom:1px solid #2e3150;">
          <td style="padding:12px 16px;color:#94a3b8">{i}</td>
          <td style="padding:12px 16px">
            <strong style="color:#e2e8f0">{pick['name']}</strong><br>
            <span style="color:#64748b;font-size:12px">{pick['code']}</span>
          </td>
          <td style="padding:12px 16px">
            <span style="background:#1e3a5f;color:#60a5fa;padding:3px 10px;
                         border-radius:99px;font-size:12px">{pick.get('theme','-')}</span>
          </td>
          <td style="padding:12px 16px">
            <strong style="color:#6366f1">{score}/10</strong>
            <div style="background:#2e3150;border-radius:3px;height:4px;margin-top:4px;width:80px">
              <div style="background:#6366f1;width:{bar_width}%;height:4px;border-radius:3px"></div>
            </div>
          </td>
          <td style="padding:12px 16px;color:#94a3b8;font-size:13px">{pick.get('entry','-')}</td>
          <td style="padding:12px 16px;color:#ef4444;font-size:13px">{pick.get('stop_loss','-')}</td>
        </tr>"""

    dashboard_btn = f"""
    <div style="text-align:center;margin:28px 0">
      <a href="{dashboard_url}"
         style="background:#6366f1;color:#fff;padding:12px 32px;border-radius:8px;
                text-decoration:none;font-weight:600;font-size:14px">
        🔗 웹 대시보드 열기
      </a>
    </div>""" if dashboard_url else ""

    # ── HTML 본문 ────────────────────────────────────────
    html_body = f"""
    <div style="background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',sans-serif;
                max-width:700px;margin:0 auto;border-radius:12px;overflow:hidden;
                border:1px solid #2e3150">

      <div style="background:#1a1d2e;padding:24px 28px;border-bottom:1px solid #2e3150">
        <h1 style="margin:0;font-size:20px;color:#6366f1">📊 AI 수급 주도주 분석</h1>
        <p style="margin:6px 0 0;color:#64748b;font-size:13px">
          {today} · AI 수급 전문 애널리스트 에이전트
        </p>
      </div>

      <div style="display:flex;border-bottom:1px solid #2e3150">
        <div style="flex:1;padding:16px 20px;border-right:1px solid #2e3150;text-align:center">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">추천 종목</div>
          <div style="font-size:24px;font-weight:700;color:#3b82f6">{len(top)}개</div>
        </div>
        <div style="flex:1;padding:16px 20px;border-right:1px solid #2e3150;text-align:center">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">7일 적중률</div>
          <div style="font-size:24px;font-weight:700;color:#22c55e">
            {report_summary.get('hit_rate_7d','N/A')}
          </div>
        </div>
        <div style="flex:1;padding:16px 20px;text-align:center">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">평균 7일 수익</div>
          <div style="font-size:24px;font-weight:700;color:#a855f7">
            {report_summary.get('avg_7d','+0.00')}%
          </div>
        </div>
      </div>

      <div style="padding:20px 0">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="border-bottom:1px solid #2e3150">
              <th style="padding:8px 16px;color:#64748b;font-size:11px;text-align:left">#</th>
              <th style="padding:8px 16px;color:#64748b;font-size:11px;text-align:left">종목</th>
              <th style="padding:8px 16px;color:#64748b;font-size:11px;text-align:left">테마</th>
              <th style="padding:8px 16px;color:#64748b;font-size:11px;text-align:left">점수</th>
              <th style="padding:8px 16px;color:#64748b;font-size:11px;text-align:left">진입구간</th>
              <th style="padding:8px 16px;color:#64748b;font-size:11px;text-align:left">손절선</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>

      {dashboard_btn}

      <div style="background:#1a1d2e;padding:14px 20px;border-top:1px solid #2e3150;
                  font-size:11px;color:#475569;text-align:center">
        ⚠ 본 메일은 AI 시뮬레이션 기반 참고 자료입니다.
        투자 손실에 대한 책임은 투자자 본인에게 있습니다.
      </div>
    </div>"""

    # ── 발송 ─────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{subject_prefix} [{today}] AI 수급 주도주 분석 리포트"
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())
        print(f"✅ 이메일 발송 완료 → {recipient}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("❌ Gmail 인증 실패. 앱 비밀번호를 확인하세요. (공백 제거 후 16자리)")
        return False
    except Exception as e:
        print(f"❌ 이메일 발송 오류: {e}")
        return False


# ── 직접 실행 시 테스트 ──────────────────────────────────
if __name__ == "__main__":
    dummy = {
        "top_picks": [
            {"name": "솔브레인",    "code": "357780", "score": 8.6,
             "theme": "반도체장비", "entry": "310,000원", "stop_loss": "300,000원"},
            {"name": "신한지주",    "code": "055550", "score": 8.1,
             "theme": "금융",       "entry": "47,000원",  "stop_loss": "45,500원"},
            {"name": "이오테크닉스","code": "039030", "score": 8.1,
             "theme": "반도체장비", "entry": "95,000원",  "stop_loss": "92,000원"},
        ],
        "hit_rate_7d": "60.0%",
        "avg_7d": "+2.34",
    }
    send_email(
        dummy,
        dashboard_url="https://your-app.onrender.com",
        subject_prefix="🧪 테스트"
    )
