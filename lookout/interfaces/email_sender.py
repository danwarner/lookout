"""ABC for email delivery."""

from abc import ABC, abstractmethod


class EmailSender(ABC):
    """Sends formatted digest emails."""

    @abstractmethod
    def send(self, to: str, from_addr: str, subject: str, html_body: str) -> bool:
        """Send an HTML email.

        Returns True if sent successfully.
        """
        ...
