"""Notifications the traders send after each run: Pushover, ntfy, a Slack webhook, the
log, or nowhere. NOTIFY_CHANNEL=auto picks the first one that's configured."""

import logging
from typing import Protocol

import httpx

from .settings import Settings

logger = logging.getLogger(__name__)

TIMEOUT = 10.0


class Notifier(Protocol):
    name: str

    async def send(self, title: str, message: str) -> None:
        """Deliver a notification. Raises httpx.HTTPError if delivery fails."""
        ...


class LogNotifier:
    name = "log"

    async def send(self, title: str, message: str) -> None:
        logger.info("Notification [%s] %s", title, message)


class NullNotifier:
    name = "none"

    async def send(self, title: str, message: str) -> None:
        pass


class PushoverNotifier:
    name = "pushover"
    URL = "https://api.pushover.net/1/messages.json"

    def __init__(self, user: str, token: str):
        self.user, self.token = user, token

    async def send(self, title: str, message: str) -> None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                self.URL, data={"user": self.user, "token": self.token, "title": title, "message": message}
            )
            response.raise_for_status()


class NtfyNotifier:
    name = "ntfy"

    def __init__(self, url: str):
        self.url = url

    async def send(self, title: str, message: str) -> None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(self.url, content=message.encode(), headers={"Title": title})
            response.raise_for_status()


class SlackNotifier:
    name = "slack"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, title: str, message: str) -> None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(self.webhook_url, json={"text": f"*{title}*\n{message}"})
            response.raise_for_status()


def create_notifier(settings: Settings) -> Notifier:
    channel = settings.notify_channel.strip().lower()
    pushover = (settings.secret("pushover_user"), settings.secret("pushover_token"))
    slack = settings.secret("slack_webhook_url")
    if channel == "auto":
        if all(pushover):
            channel = "pushover"
        elif settings.ntfy_url:
            channel = "ntfy"
        elif slack:
            channel = "slack"
        else:
            channel = "log"
    match channel:
        case "pushover" if all(pushover):
            return PushoverNotifier(*pushover)  # pyright: ignore[reportArgumentType]
        case "ntfy" if settings.ntfy_url:
            return NtfyNotifier(settings.ntfy_url)
        case "slack" if slack:
            return SlackNotifier(slack)
        case "none":
            return NullNotifier()
        case "log":
            return LogNotifier()
    logger.warning("NOTIFY_CHANNEL=%s isn't fully configured; logging notifications instead", channel)
    return LogNotifier()


async def notify(notifier: Notifier, title: str, message: str) -> str:
    """Send, and describe the outcome for the agent rather than raising."""
    try:
        await notifier.send(title, message)
    except httpx.HTTPError as e:
        logger.warning("%s notification failed: %s", notifier.name, e)
        return "The push notification could not be sent"
    if notifier.name in ("log", "none"):
        return "Notification recorded (no push channel is configured)"
    return "Push notification sent"
