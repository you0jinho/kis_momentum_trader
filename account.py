"""계좌 잔고 / 보유종목 조회"""
from typing import Dict, Tuple

from api_client import ApiClient
from config import TrId, CANO, ACNT_PRDT_CD
from logger import logger


class Account:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def get_balances(self) -> Tuple[Dict[str, int], int]:
        """
        보유 종목(symbol -> 수량)과 주문가능 현금을 반환.
        ※ 잔고조회는 계좌 단위 조회라 종목코드를 파라미터로 넘기지 않음
          (참고했던 코드에서 symbol 인자를 넘기던 부분은 불필요해서 제거함).
        ⚠️ 확인 필요: tr_id(VTTC8434R) 및 응답 필드명(hldg_qty, dnca_tot_amt)은
          KIS 공식 문서에서 재확인할 것.
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
        available_cash = int(output2[0].get("dnca_tot_amt", 0)) if output2 else 0

        logger.info(f"[잔고조회] 보유종목={holdings} / 가용현금={available_cash:,}원")
        return holdings, available_cash
