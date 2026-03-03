"""Resend email delivery implementation of EmailSender."""

from __future__ import annotations

import resend

from lookout.interfaces.email_sender import EmailSender


class ResendSender(EmailSender):
    """Sends emails via the Resend API."""

    def __init__(self, api_key: str):
        resend.api_key = api_key

    def send(self, to: str | list[str], from_addr: str, subject: str, html_body: str,
             attachments: list[dict] | None = None) -> bool:
        recipients = [addr.strip() for addr in to.split(",")] if isinstance(to, str) else to
        params: resend.Emails.SendParams = {
            "from": from_addr,
            "to": recipients,
            "subject": subject,
            "html": html_body,
        }
        if attachments:
            params["attachments"] = attachments
        result = resend.Emails.send(params)
        return result is not None and "id" in result
