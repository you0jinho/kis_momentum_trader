"""
초반 변동성 돌파 & 초단기 모멘텀 전략 (09:00~09:30 집중)

진행 순서
1) 09:00~09:05  : 종목별 고가/저가를 실제로 폴링하며 기록 (돌파 기준가 산출)
2) 09:05~09:20  : 현재가가 09:05까지의 고가를 위로 돌파하면 즉시 시장가 매수
3) 보유 중      : 진입 후 3분 경과 OR +0.3% 수익 OR -0.3% 손실 도달 시 즉시 시장가 매도
4) 09:30        : 잔여 포지션 전량 강제 청산 후 프로그램 종료
"""
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

    # ── Phase 0: 09:00~09:05 고가/저가 기록 ──────────────────────────
    def record_range(self) -> None:
        for symbol in self.universe:
            try:
                price = self.market.get_current_price(symbol)
            except Exception as e:
                logger.error(f"[범위기록] {symbol} 시세조회 실패: {e}")
                continue

            r = self.ranges.get(symbol)
            if r is None:
                self.ranges[symbol] = RangeInfo(high=price, low=price)
            else:
                r.high = max(r.high, price)
                r.low = min(r.low, price)

        snapshot = {s: (r.high, r.low) for s, r in self.ranges.items()}
        logger.info(f"[범위기록] 현재까지 (고가, 저가): {snapshot}")

    def _ensure_allocation(self) -> None:
        """
        종목당 투입 가능 금액을 한 번만 계산해서 재사용 (잔고조회 호출 최소화).
        가용 현금을 유니버스 종목 수로 균등 분배하고, 일부 여유(CASH_SAFETY_MARGIN)를 둔다.
        """
        if self.allocation_cash:
            return
        try:
            _, available_cash = self.account.get_balances()
            n = max(1, len(self.universe))
            self.allocation_cash = int(available_cash * config.CASH_SAFETY_MARGIN / n)
            logger.info(
                f"[자금배정] 가용현금 {available_cash:,}원 / 유니버스 {n}종목 / "
                f"종목당 배정 {self.allocation_cash:,}원"
            )
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
                continue

            if price > r.high:
                qty = max(1, self.allocation_cash // price)
                logger.info(
                    f"🔥 [돌파 매수] {symbol} 09:05 고가 {r.high:,}원 돌파 "
                    f"(현재가 {price:,}원) -> {qty}주 시장가 매수"
                )
                try:
                    self.orders.buy_market(symbol, qty)
                    self.positions[symbol] = Position(
                        qty=qty, entry_price=price, entry_time=time.time()
                    )
                    self._confirm_execution(symbol)
                except Exception as e:
                    logger.error(f"[돌파 매수 실패] {symbol}: {e}")

    # ── Phase 2: 보유 포지션 청산 조건 점검 ──────────────────────────
    def check_exits(self, force: bool = False) -> None:
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            try:
                price = self.market.get_current_price(symbol)
            except Exception as e:
                logger.error(f"[청산감시] {symbol} 시세조회 실패: {e}")
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
                    f"🚨 [청산] {symbol} {pos.qty}주 현재가 {price:,}원 매도 - 이유: {reason}"
                )
                try:
                    self.orders.sell_market(symbol, pos.qty)
                    del self.positions[symbol]
                    self._confirm_execution(symbol)
                except Exception as e:
                    logger.error(f"[청산 실패] {symbol}: {e}")

    def _confirm_execution(self, symbol: str) -> None:
        """주문 1건당 1회만 잔고를 재조회해 체결 여부를 확인 (호출 최소화)."""
        try:
            holdings, _ = self.account.get_balances()
            qty = holdings.get(symbol, 0)
            logger.info(f"[체결확인] {symbol} 현재 보유수량: {qty}주")
        except Exception as e:
            logger.error(f"[체결확인 실패] {symbol}: {e}")

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
                break
