"""
초반 변동성 돌파 & 초단기 모멘텀 전략 (09:00~09:30 집중)

진행 순서
1) 09:00~09:05  : 종목별 고가/저가를 실제로 폴링하며 기록 (돌파 기준가 산출)
2) 09:05~09:20  : 현재가가 09:05까지의 고가를 위로 돌파하면 즉시 시장가 매수
3) 보유 중      : 진입 후 3분 경과 OR +0.3% 수익 OR -0.3% 손실 도달 시 즉시 시장가 매도
4) 09:30        : 잔여 포지션 전량 강제 청산 후 프로그램 종료

상태 저장(trader_state.json):
프로그램을 멈췄다가 같은 날 다시 켜도 범위기록/보유포지션을 잃지 않도록,
주요 이벤트(범위기록/매수/매도) 직후마다 현재 상태를 파일에 저장하고,
시작할 때 "오늘 날짜"로 저장된 상태가 있으면 그대로 복구한다.

매수/매도 시에는 종목명을 같이 표시하고, 주문 직전(전)과 체결확인 시(후)의
현금 잔고를 같이 로그로 남겨서 실제로 잔고가 변하는지 확인할 수 있다.
"""
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from typing import Dict, Optional

import config
from api_client import ApiClient
from market_data import MarketData
from account import Account
from orders import Orders
from logger import logger


@dataclass
class RangeInfo:
    high: int
    low: int


@dataclass
class Position:
    qty: int
    entry_price: int
    entry_time: float  # time.time() 기준 타임스탬프


class BreakoutScalpTrader:
    def __init__(self) -> None:
        self.client = ApiClient()
        self.market = MarketData(self.client)
        self.account = Account(self.client)
        self.orders = Orders(self.client)

        self.universe = config.UNIVERSE
        self.ranges: Dict[str, RangeInfo] = {}
        self.positions: Dict[str, Position] = {}
        self.allocation_cash: int = 0

        self._t_range_start = dt_time(*config.RANGE_START)
        self._t_range_end = dt_time(*config.RANGE_END)
        self._t_entry_end = dt_time(*config.ENTRY_END)
        self._t_eod = dt_time(*config.EOD_CUTOFF)

        self._load_state()

    # ── 상태 저장/복구 (멈췄다가 재시작해도 당일 진행 상황 유지) ──────
    def _save_state(self) -> None:
        data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "ranges": {s: [r.high, r.low] for s, r in self.ranges.items()},
            "positions": {
                s: {"qty": p.qty, "entry_price": p.entry_price, "entry_time": p.entry_time}
                for s, p in self.positions.items()
            },
            "allocation_cash": self.allocation_cash,
        }
        try:
            with open(config.STATE_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError as e:
            logger.error(f"[상태저장] 실패: {e}")

    def _load_state(self) -> None:
        if not os.path.exists(config.STATE_FILE_PATH):
            return
        try:
            with open(config.STATE_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.error("[상태복구] 상태 파일을 읽을 수 없어 새로 시작합니다.")
            return

        if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            logger.info("[상태복구] 오늘 날짜 상태가 아니라 무시하고 새로 시작합니다.")
            return

        for symbol, (high, low) in data.get("ranges", {}).items():
            self.ranges[symbol] = RangeInfo(high=high, low=low)
        for symbol, p in data.get("positions", {}).items():
            self.positions[symbol] = Position(
                qty=p["qty"], entry_price=p["entry_price"], entry_time=p["entry_time"]
            )
        self.allocation_cash = data.get("allocation_cash", 0)

        if self.ranges or self.positions:
            logger.info(
                f"[상태복구] 이전 실행 상태를 불러왔습니다 - 범위기록 {len(self.ranges)}종목 / "
                f"보유포지션 {len(self.positions)}종목 / 배정금액 {self.allocation_cash:,}원"
            )

    # ── 잔고 조회 헬퍼 (매수/매도 전후 비교용) ────────────────────────
    def _log_cash_balance(self, label: str) -> None:
        """
        매수/매도 직전에 호출해서 "주문 전 잔고"를 로그로 남긴다.
        예수금은 T+2 정산 때문에 당일 거래가 바로 안 보일 수 있어서,
        금일매수/금일매도 금액도 같이 찍어 실제 거래 여부를 더 확실히 판단할 수 있게 한다.
        """
        try:
            _, cash_info = self.account.get_balances()
            logger.info(
                f"[{label} 전 잔고] 예수금: {cash_info['dnca_tot_amt']:,}원 "
                f"(금일매수 {cash_info['thdt_buy_amt']:,}원 / 금일매도 {cash_info['thdt_sll_amt']:,}원)"
            )
        except Exception as e:
            logger.error(f"[{label} 전 잔고조회 실패] {e}")

    def _confirm_execution(self, symbol: str, label: str) -> None:
        """
        주문 1건당 1회만 잔고를 재조회해서 보유수량 + 현금 정보를 함께 확인.
        (호출 최소화를 위해 보유수량/현금을 한 번의 조회로 같이 가져온다)
        """
        name = config.get_symbol_name(symbol)
        try:
            holdings, cash_info = self.account.get_balances()
            qty = holdings.get(symbol, 0)
            logger.info(
                f"[{label} 후 잔고] {name}({symbol}) 보유수량: {qty}주 / "
                f"예수금: {cash_info['dnca_tot_amt']:,}원 "
                f"(금일매수 {cash_info['thdt_buy_amt']:,}원 / 금일매도 {cash_info['thdt_sll_amt']:,}원)"
            )
        except Exception as e:
            logger.error(f"[{label} 후 잔고조회 실패] {name}({symbol}): {e}")

    # ── Phase 0: 09:00~09:05 고가/저가 기록 ──────────────────────────
    def record_range(self) -> None:
        for symbol in self.universe:
            try:
                price = self.market.get_current_price(symbol)
            except Exception as e:
                logger.error(f"[범위기록] {symbol} 시세조회 실패: {e}")
                time.sleep(config.SYMBOL_CALL_DELAY_SEC)
                continue

            r = self.ranges.get(symbol)
            if r is None:
                self.ranges[symbol] = RangeInfo(high=price, low=price)
            else:
                r.high = max(r.high, price)
                r.low = min(r.low, price)
            time.sleep(config.SYMBOL_CALL_DELAY_SEC)

        snapshot = {s: (r.high, r.low) for s, r in self.ranges.items()}
        logger.info(f"[범위기록] 현재까지 (고가, 저가): {snapshot}")
        self._save_state()

    def _ensure_allocation(self) -> None:
        """
        종목당 투입 가능 금액을 한 번만 계산해서 재사용 (잔고조회 호출 최소화).
        가용 현금을 유니버스 종목 수로 균등 분배하고, 일부 여유(CASH_SAFETY_MARGIN)를 둔다.
        """
        if self.allocation_cash:
            return
        try:
            _, cash_info = self.account.get_balances()
            available_cash = cash_info["dnca_tot_amt"]
            n = max(1, len(self.universe))
            self.allocation_cash = int(available_cash * config.CASH_SAFETY_MARGIN / n)
            logger.info(
                f"[자금배정] 예수금 {available_cash:,}원 / 유니버스 {n}종목 / "
                f"종목당 배정 {self.allocation_cash:,}원"
            )
            self._save_state()
        except Exception as e:
            logger.error(f"[자금배정] 잔고조회 실패: {e}")

    # ── Phase 1: 09:05~09:20 돌파 매수 ───────────────────────────────
    def check_breakout_entries(self) -> None:
        self._ensure_allocation()
        if not self.allocation_cash:
            return

        for symbol in self.universe:
            if symbol in self.positions:
                continue
            r = self.ranges.get(symbol)
            if r is None:
                continue

            try:
                price = self.market.get_current_price(symbol)
            except Exception as e:
                logger.error(f"[돌파감시] {symbol} 시세조회 실패: {e}")
                time.sleep(config.SYMBOL_CALL_DELAY_SEC)
                continue

            if price > r.high:
                name = config.get_symbol_name(symbol)
                qty = max(1, self.allocation_cash // price)
                logger.info(
                    f"🔥 [돌파 매수] {name}({symbol}) 09:05 고가 {r.high:,}원 돌파 "
                    f"(현재가 {price:,}원) -> {qty}주 시장가 매수"
                )
                try:
                    self._log_cash_balance(f"{name}({symbol}) 매수")
                    self.orders.buy_market(symbol, qty)
                    self.positions[symbol] = Position(
                        qty=qty, entry_price=price, entry_time=time.time()
                    )
                    self._save_state()
                    self._confirm_execution(symbol, "매수")
                except Exception as e:
                    logger.error(f"[돌파 매수 실패] {name}({symbol}): {e}")

            time.sleep(config.SYMBOL_CALL_DELAY_SEC)

    # ── Phase 2: 보유 포지션 청산 조건 점검 ──────────────────────────
    def check_exits(self, force: bool = False) -> None:
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            name = config.get_symbol_name(symbol)
            try:
                price = self.market.get_current_price(symbol)
            except Exception as e:
                logger.error(f"[청산감시] {name}({symbol}) 시세조회 실패: {e}")
                time.sleep(config.SYMBOL_CALL_DELAY_SEC)
                continue

            elapsed = time.time() - pos.entry_time
            pnl_pct = (price - pos.entry_price) / pos.entry_price

            reason: Optional[str] = None
            if force:
                reason = "09:30 EOD 강제청산"
            elif elapsed >= config.HOLD_SECONDS:
                reason = f"보유시간 {elapsed:.0f}초 도달 (3분 타임컷)"
            elif pnl_pct >= config.PROFIT_TARGET_PCT:
                reason = f"목표수익 도달 ({pnl_pct:+.2%})"
            elif pnl_pct <= config.LOSS_LIMIT_PCT:
                reason = f"손실한도 도달 ({pnl_pct:+.2%})"

            if reason:
                logger.info(
                    f"🚨 [청산] {name}({symbol}) {pos.qty}주 현재가 {price:,}원 매도 - 이유: {reason}"
                )
                try:
                    self._log_cash_balance(f"{name}({symbol}) 매도")
                    self.orders.sell_market(symbol, pos.qty)
                    del self.positions[symbol]
                    self._save_state()
                    self._confirm_execution(symbol, "매도")
                except Exception as e:
                    logger.error(f"[청산 실패] {name}({symbol}): {e}")

            time.sleep(config.SYMBOL_CALL_DELAY_SEC)

    # ── 메인 루프 ────────────────────────────────────────────────────
    def run(self) -> None:
        logger.info("===== 초단기 모멘텀 돌파 전략 시작 =====")
        while True:
            now = datetime.now().time()

            if now < self._t_range_start:
                logger.info(f"[대기] 현재 {now.strftime('%H:%M:%S')} - 09:00 이전 대기 중")
                time.sleep(config.IDLE_POLL_SEC)

            elif self._t_range_start <= now < self._t_range_end:
                self.record_range()
                time.sleep(config.RANGE_POLL_SEC)

            elif self._t_range_end <= now < self._t_entry_end:
                self.check_breakout_entries()
                self.check_exits()
                time.sleep(config.TRADE_POLL_SEC)

            elif self._t_entry_end <= now < self._t_eod:
                # 신규 진입은 마감, 보유 포지션 청산 조건만 계속 점검
                self.check_exits()
                time.sleep(config.TRADE_POLL_SEC)

            else:
                logger.info("===== 09:30 도달: 잔여 포지션 강제 전량 청산 =====")
                self.check_exits(force=True)
                logger.info("===== 금일 전략 종료 =====")
                if os.path.exists(config.STATE_FILE_PATH):
                    os.remove(config.STATE_FILE_PATH)
                break
