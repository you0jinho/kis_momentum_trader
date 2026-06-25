"""
환경설정 모듈
- 인증 정보는 환경변수에서만 로드 (하드코딩 금지)
- 모의투자 도메인 / 거래 종목 / 전략 파라미터 정의
- API 필드명·tr_id 중 확신이 낮은 값은 이 파일의 TrId 클래스에 모아
  "확인 필요" 로 표시해두었음. 실제 호출 전에 KIS 공식 문서/GitHub
  샘플(koreainvestment/open-trading-api)에서 한 번씩 대조해서 쓸 것.
"""
import os
import sys
from typing import List

from dotenv import load_dotenv

# .env 파일이 있으면 그 내용을 환경변수로 로드한다.
# (이미 터미널에 export/set 으로 설정된 값이 있으면 그게 우선됨 - override=False)
load_dotenv()

# ── 인증 정보 (환경변수) ──────────────────────────────────────────
ACCOUNT_NO: str = os.environ.get("GH_ACCOUNT", "")
APP_KEY: str = os.environ.get("GH_APPKEY", "")
APP_SECRET: str = os.environ.get("GH_APPSECRET", "")


def validate_credentials() -> None:
    """필수 환경변수가 비어있으면 즉시 종료 (조용히 None으로 진행되는 것 방지)."""
    missing = [
        name
        for name, val in [
            ("GH_ACCOUNT", ACCOUNT_NO),
            ("GH_APPKEY", APP_KEY),
            ("GH_APPSECRET", APP_SECRET),
        ]
        if not val
    ]
    if missing:
        sys.exit(f"[설정 오류] 다음 환경변수가 설정되지 않았습니다: {', '.join(missing)}")


# 계좌번호 형식: "12345678-01" 또는 "1234567801" 둘 다 허용
if "-" in ACCOUNT_NO:
    CANO, ACNT_PRDT_CD = ACCOUNT_NO.split("-", 1)
else:
    CANO, ACNT_PRDT_CD = ACCOUNT_NO[:8], (ACCOUNT_NO[8:10] or "01")

# ── 모의투자 도메인 (실전 도메인 사용 금지) ───────────────────────
BASE_URL: str = "https://openapivts.koreainvestment.com:29443"

# ── 거래 대상 유니버스 ───────────────────────────────────────────
# ⚠️ 아래 종목은 "돌파 전략 테스트용 예시"일 뿐 투자 추천이 아닙니다.
#    실제 투입할 종목은 직접 선정/검토하세요. (모의투자 환경에서만 사용)
UNIVERSE: List[str] = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "005380",  # 현대차
    "247540",  # 에코프로비엠 (2차전지, 코스닥, 고변동성)
    "042700",  # 한미반도체 (반도체 장비, 코스닥, 고변동성)
    "196170",  # 알테오젠 (바이오, 코스닥, 고변동성)
]

# 종목코드 -> 종목명 (로그에 코드만 찍히면 알아보기 어려워서, 매수/매도 시
# 사람이 읽기 쉬운 이름을 같이 보여주기 위한 매핑)
SYMBOL_NAMES: dict = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "005380": "현대차",
    "247540": "에코프로비엠",
    "042700": "한미반도체",
    "196170": "알테오젠",
}


def get_symbol_name(symbol: str) -> str:
    """매핑에 없는 종목이어도 코드 자체를 이름처럼 반환해서 안전하게 동작."""
    return SYMBOL_NAMES.get(symbol, symbol)

# ── 전략 시간 구간 (시, 분) ───────────────────────────────────────
RANGE_START = (9, 0)    # 고가/저가 기록 시작
RANGE_END = (9, 5)      # 고가/저가 기록 종료 -> 돌파 기준가 확정
ENTRY_END = (9, 20)     # 신규 매수 진입 마감
EOD_CUTOFF = (9, 30)    # 잔여 포지션 강제 전량 청산

# ── 전략 파라미터 ────────────────────────────────────────────────
HOLD_SECONDS: int = 180             # 진입 후 최대 보유 시간(초) = 3분
PROFIT_TARGET_PCT: float = 0.003    # +0.3% 도달 시 청산
LOSS_LIMIT_PCT: float = -0.003      # -0.3% 도달 시 청산

# 가용 예수금을 종목 수로 균등 분배할 때, 전부 다 쓰지 않고 일부 여유를 둔다.
# (체결가 변동/수수료 등으로 예수금이 부족해지는 상황 방지)
CASH_SAFETY_MARGIN: float = 0.9

# ── 폴링 간격 (모의투자 호출 제한 보수적으로) ─────────────────────
# 유니버스가 3종목 -> 6종목으로 늘어난 만큼, 호출 폭증을 막기 위해
# 간격도 같이 늘렸음. 종목을 더 추가하면 이 값도 같이 늘리는 걸 권장.
RANGE_POLL_SEC: int = 20   # 09:00~09:05 구간
TRADE_POLL_SEC: int = 18   # 09:05~09:30 구간 (매수 감시 + 청산 감시)
IDLE_POLL_SEC: int = 30    # 09:00 이전 대기 구간

# 종목 여러 개를 한 바퀴 돌 때, 한꺼번에 몰아서 호출하면 모의투자가 순간적인
# 버스트로 보고 막을 수 있어서 (간헐적 500 에러 원인 중 하나), 종목 하나씩
# 조회할 때마다 살짝 쉬어준다.
SYMBOL_CALL_DELAY_SEC: float = 0.5

# ── 상태 저장 파일 (멈췄다가 재시작해도 당일 진행 상황 복구) ──────
TOKEN_CACHE_PATH: str = "token_cache.json"
STATE_FILE_PATH: str = "trader_state.json"

# ── 주문 구분 코드 ───────────────────────────────────────────────
ORD_DVSN_LIMIT: str = "00"   # 지정가
ORD_DVSN_MARKET: str = "01"  # 시장가


class TrId:
    """
    ✅ CURRENT_PRICE/BALANCE/BUY_ORDER/SELL_ORDER 모두 test_connection.py 및
    실제 매수/매도 시도에서 호출 성공(rt_cd="0")을 확인했음. orders.py가 이제
    응답의 ODNO(주문번호)를 로그에 남기므로, 한투 앱/HTS 주문내역에서 그
    번호로 실제 접수 여부를 대조 확인할 수 있다.
    """
    CURRENT_PRICE = "FHKST01010100"  # 주식현재가 시세조회 - 확인됨
    BALANCE = "VTTC8434R"            # 모의투자 주식잔고조회 - 확인됨
    BUY_ORDER = "VTTC0802U"          # 모의투자 주식 현금매수주문 - 확인됨
    SELL_ORDER = "VTTC0801U"         # 모의투자 주식 현금매도주문 - 확인됨
