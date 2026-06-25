"""계좌 잔고 / 보유종목 조회"""
from typing import Dict, Tuple

from api_client import ApiClient
from config import TrId, CANO, ACNT_PRDT_CD
from logger import logger


class Account:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def get_balances(self) -> Tuple[Dict[str, int], dict]:
        """
        보유 종목(symbol -> 수량)과 현금 관련 정보를 반환한다.

        ⚠️ 중요: "예수금총액"(dnca_tot_amt)은 한국 증시 T+2 결제 구조 때문에
        당일 매수/매도를 바로 반영하지 않을 수 있다 (정산 전 금액). 그래서
        "정말 오늘 거래가 있었는지"를 확인하려면 예수금이 아니라 아래
        thdt_buy_amt(금일매수금액)/thdt_sll_amt(금일매도금액)를 봐야 한다 —
        이 두 필드는 정산과 무관하게 오늘 체결된 거래가 있으면 즉시 누적된다.

        cash_info 반환 필드:
        - dnca_tot_amt  : 예수금총액 (정산 기준, 당일 변동 안 보일 수 있음)
        - thdt_buy_amt  : 금일매수금액 (오늘 매수 체결이 있으면 즉시 반영)
        - thdt_sll_amt  : 금일매도금액 (오늘 매도 체결이 있으면 즉시 반영)
        - tot_evlu_amt  : 총평가금액 (보유종목 평가금액 + D+2 예수금)

        ※ 잔고조회는 계좌 단위 조회라 종목코드를 파라미터로 넘기지 않음.
        ⚠️ tr_id(VTTC8434R)·필드명은 KIS 공식 GitHub(koreainvestment/open-trading-api)
        의 kis_domstk.py 샘플과 대조해 확인함.
        """
        params = {
            "CANO": CANO,
            "ACNT_PRDT_CD": ACNT_PRDT_CD,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        res = self.client.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            TrId.BALANCE,
            params,
        )

        holdings: Dict[str, int] = {}
        for item in res.get("output1", []):
            qty = int(item.get("hldg_qty", 0))
            if qty > 0:
                holdings[item["pdno"]] = qty

        output2 = res.get("output2", [{}])
        row = output2[0] if output2 else {}
        cash_info = {
            "dnca_tot_amt": int(row.get("dnca_tot_amt", 0)),
            "thdt_buy_amt": int(row.get("thdt_buy_amt", 0)),
            "thdt_sll_amt": int(row.get("thdt_sll_amt", 0)),
            "tot_evlu_amt": int(row.get("tot_evlu_amt", 0)),
        }

        logger.info(
            f"[잔고조회] 보유종목={holdings} / 예수금={cash_info['dnca_tot_amt']:,}원 "
            f"/ 금일매수={cash_info['thdt_buy_amt']:,}원 / 금일매도={cash_info['thdt_sll_amt']:,}원"
        )
        return holdings, cash_info
