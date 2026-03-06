"""
Notification module — Telegram + Email alerts for trade events.

Sends real-time alerts for:
  - Trade entries and exits
  - Daily P&L summaries
  - Risk limit breaches
  - System errors

Set in .env:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
    EMAIL_FROM=...
    EMAIL_TO=...
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_PASSWORD=...
"""

from __future__ import annotations

import logging
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from config.settings import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Send messages to a Telegram chat via Bot API.

    Create a bot with @BotFather, get the token, and note your chat_id.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self) -> None:
        self._cfg = config.notifications
        self._enabled = bool(self._cfg.telegram_token and self._cfg.telegram_chat_id)
        if not self._enabled:
            logger.debug("Telegram notifier disabled (token/chat_id not set).")

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured Telegram chat."""
        if not self._enabled:
            return False
        try:
            import urllib.request, urllib.parse
            url = self.BASE_URL.format(token=self._cfg.telegram_token)
            payload = urllib.parse.urlencode({
                "chat_id":    self._cfg.telegram_chat_id,
                "text":       message,
                "parse_mode": parse_mode,
            }).encode()
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    def send_async(self, message: str) -> None:
        """Fire-and-forget asynchronous send."""
        threading.Thread(target=self.send, args=(message,), daemon=True).start()


class EmailNotifier:
    """Send HTML email alerts via SMTP."""

    def __init__(self) -> None:
        self._cfg = config.notifications
        self._enabled = bool(
            self._cfg.email_from and self._cfg.email_to and self._cfg.smtp_password
        )

    def send(self, subject: str, body_html: str) -> bool:
        if not self._enabled:
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self._cfg.email_from
            msg["To"]      = self._cfg.email_to
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self._cfg.email_from, self._cfg.smtp_password)
                server.sendmail(
                    self._cfg.email_from, self._cfg.email_to, msg.as_string()
                )
            return True
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return False


class TradeNotifier:
    """
    High-level notifier that dispatches trade/risk events to all channels.

    Usage:
        notifier = TradeNotifier()
        notifier.on_trade_entry("NIFTY CE", 150.0, 105.0, 220.0, 50, "BreakoutStrategy")
    """

    def __init__(self) -> None:
        self._telegram = TelegramNotifier()
        self._email    = EmailNotifier()

    def on_trade_entry(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        target: float,
        quantity: int,
        strategy: str,
    ) -> None:
        risk_reward = round((target - entry_price) / max(entry_price - stop_loss, 0.01), 2)
        msg = (
            f"🟢 <b>TRADE ENTRY</b>\n"
            f"Symbol   : {symbol}\n"
            f"Strategy : {strategy}\n"
            f"Entry    : ₹{entry_price:,.2f}\n"
            f"SL       : ₹{stop_loss:,.2f}\n"
            f"Target   : ₹{target:,.2f}\n"
            f"Qty      : {quantity}\n"
            f"R:R      : 1:{risk_reward}\n"
            f"Time     : {datetime.now():%H:%M:%S}"
        )
        self._telegram.send_async(msg)

    def on_trade_exit(
        self,
        symbol: str,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,
        strategy: str,
    ) -> None:
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} <b>TRADE EXIT</b>\n"
            f"Symbol   : {symbol}\n"
            f"Strategy : {strategy}\n"
            f"Exit     : ₹{exit_price:,.2f}\n"
            f"P&L      : ₹{pnl:,.2f} ({pnl_pct:+.1f}%)\n"
            f"Reason   : {reason}\n"
            f"Time     : {datetime.now():%H:%M:%S}"
        )
        self._telegram.send_async(msg)

    def on_daily_summary(
        self,
        realized_pnl: float,
        trades: int,
        win_rate: float,
    ) -> None:
        emoji = "📈" if realized_pnl >= 0 else "📉"
        msg = (
            f"{emoji} <b>DAILY SUMMARY</b> — {datetime.now():%d %b %Y}\n"
            f"Realized P&L : ₹{realized_pnl:,.2f}\n"
            f"Total Trades : {trades}\n"
            f"Win Rate     : {win_rate:.1f}%"
        )
        self._telegram.send(msg)
        if self._email._enabled:
            self._email.send(
                subject=f"Daily P&L Summary: ₹{realized_pnl:,.0f}",
                body_html=msg.replace("\n", "<br>"),
            )

    def on_risk_breach(self, reason: str) -> None:
        msg = (
            f"⚠️ <b>RISK LIMIT BREACHED</b>\n"
            f"Reason : {reason}\n"
            f"Time   : {datetime.now():%H:%M:%S}\n"
            f"Action : All trading HALTED for today."
        )
        self._telegram.send(msg)

    def on_error(self, error: str, module: str) -> None:
        msg = (
            f"🔴 <b>SYSTEM ERROR</b>\n"
            f"Module : {module}\n"
            f"Error  : {error}\n"
            f"Time   : {datetime.now():%H:%M:%S}"
        )
        self._telegram.send_async(msg)
