"""Optional email delivery of briefs over SMTP (free with a Gmail app password)."""
from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage

import config

log = logging.getLogger("quantum-advisor.notify")


def email_enabled() -> bool:
    return bool(config.SMTP_HOST and config.MAIL_FROM)


def brief_email(brief: dict) -> tuple[str, str, str]:
    """(subject, plain text, html) for a morning or closing brief."""
    s = brief.get("summary") or {}
    title = "Morning brief" if brief["kind"] == "morning" else "Closing brief"
    subject = f"{title}: {s.get('headline', '')}"[:150]
    lines = [s.get("headline", ""), ""] + [f"- {p}" for p in s.get("points", [])]
    if s.get("actions"):
        lines += ["", "To check:"] + [f"- {a}" for a in s["actions"]]
    lines += [""]
    for i in brief.get("items", []):
        if i.get("error"):
            lines.append(f"{i['ticker']}: no price data")
        else:
            lines.append(f"{i['ticker']}: ₹{i['price']:,.2f} ({i['changePct']:+.2f}%)"
                         + (f" | {i['news'][0]['title']}" if i.get("news") else ""))
    if config.APP_URL:
        lines += ["", f"Open the full brief: {config.APP_URL.rstrip('/')}/app#watch"]
    lines += ["", "Educational analysis, not investment advice."]
    text = "\n".join(lines)
    body = "".join(f"<p>{html.escape(line)}</p>" if line else "<br>" for line in lines)
    return subject, text, f"<div style='font-family:sans-serif;font-size:14px'>{body}</div>"


def send_brief(to: str, brief: dict) -> bool:
    if not email_enabled() or "@" not in (to or ""):
        return False
    subject, text, html_body = brief_email(brief)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, config.MAIL_FROM, to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("brief email to %s failed: %s", to, exc)
        return False
