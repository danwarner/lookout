"""ABC for email delivery."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmailSender(ABC):
    """Sends formatted digest emails."""

    @abstractmethod
    def send(self, to: str, from_addr: str, subject: str, html_body: str,
             attachments: list[dict] | None = None) -> bool:
        """Send an HTML email with optional file attachments.

        attachments: list of {"filename": str, "content": str (base64-encoded)}
        Returns True if sent successfully.
        """
        ...
