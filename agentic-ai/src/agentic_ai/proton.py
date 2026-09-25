from __future__ import annotations

import re

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
)

from .browser import start_browser
from .models import (
    EmailContent,
    RawTrashConversation,
    TrashConversation,
    TrashPageInformation,
)

_ACTIVE_PROTON_SESSION: tuple[
    Playwright,
    BrowserContext,
    Page,
] | None = None

PROTON_URL = "https://mail.proton.me/"

PROTON_PROFILE_NAME = "proton"

LOGGED_IN_URL_PATTERN = re.compile(r"^https://mail\.proton\.me/u/\d+/")

TRASH_URL_PATTERN = re.compile( r"^https://mail\.proton\.me/u/\d+/trash(?:\?.*)?$")


async def open_proton_mail(
    project_root,
) -> tuple[
    Playwright,
    BrowserContext,
    Page,
]:
    """
    Start Proton Mail unless our existing browser is still open.

    Reuses the existing Playwright session when possible.
    """
    global _ACTIVE_PROTON_SESSION

    if _ACTIVE_PROTON_SESSION is not None:
        playwright, context, page = _ACTIVE_PROTON_SESSION

        if not context.is_closed():
            print("browser already open")

            if page.is_closed():
                page = await context.new_page()

                if page.url != PROTON_URL:
                    await page.goto(PROTON_URL)

                _ACTIVE_PROTON_SESSION = (
                    playwright,
                    context,
                    page,
                )

            return _ACTIVE_PROTON_SESSION

        _ACTIVE_PROTON_SESSION = None

    playwright, context, page = await start_browser(
        project_root=project_root,
        profile_name=PROTON_PROFILE_NAME,
        headless=False,
    )

    await page.goto(PROTON_URL)

    _ACTIVE_PROTON_SESSION = (
        playwright,
        context,
        page,
    )

    return _ACTIVE_PROTON_SESSION


async def is_logged_in(
    page: Page,
) -> bool:
    """Return whether Proton Mail shows an authenticated mailbox."""
    return bool(
        LOGGED_IN_URL_PATTERN.match(page.url)
    )


async def ensure_logged_in(
    page: Page,
) -> None:
    """Wait for manual login when necessary."""
    if await is_logged_in(page):
        print("Already logged in.")
        return

    print("Proton Mail login is required.")
    print("Log in manually in the browser window.")

    await page.wait_for_url(
        LOGGED_IN_URL_PATTERN,
        timeout=300_000,
    )

    print("Login detected.")

CONVERSATION_URL_PATTERN = re.compile( r"^https://mail\.proton\.me/u/\d+/trash/[^/?]+")


async def is_trash_conversation_page(
    page: Page,
) -> bool:
    """Return whether a Trash conversation is currently open."""
    return bool(
        CONVERSATION_URL_PATTERN.match(page.url)
    )
async def is_trash_page(
    page: Page,
) -> bool:
    """Return whether the current page is Proton Trash."""
    return bool(
        TRASH_URL_PATTERN.match(page.url)
    )
async def ensure_navigation_expanded(
    page: Page,
) -> None:
    """Expand Proton Mail navigation when Trash is hidden."""
    trash_link = page.locator(
        'a[href$="/trash"]'
    )

    if await trash_link.is_visible():
        return

    buttons = page.locator("button")

    for index in range(await buttons.count()):
        button = buttons.nth(index)

        if not await button.is_visible():
            continue

        text = (await button.inner_text()).strip()

        if text == "More":
            await button.click()
            break
    else:
        raise RuntimeError(
            "Could not find a visible More button."
        )

    await trash_link.wait_for(
        state="visible"
    )

async def open_trash(
    page: Page,
) -> None:
    """Open Proton Mail Trash."""
    if await is_trash_page(page):
        print("Already on Trash.")
        return

    await ensure_navigation_expanded(page)

    trash_link = page.locator(
        'a[href$="/trash"]'
    )

    await trash_link.click()

    await page.wait_for_url(
        TRASH_URL_PATTERN
    )

    print("Opened Trash.")

async def close_proton_mail(
    playwright: Playwright,
    context: BrowserContext,
) -> None:
    """Close the Proton browser and clear the active session."""
    global _ACTIVE_PROTON_SESSION

    await context.close()
    await playwright.stop()

    _ACTIVE_PROTON_SESSION = None
    
async def open_trash_conversation(
    page: Page,
    index: int,
) -> EmailContent:
    """Open a Trash conversation and return its visible content."""

    if await is_trash_conversation_page(page):
        print("conversation already open")

        raw_text = await page.locator(
            "body"
        ).inner_text()

        return EmailContent(
            conversation_index=index,
            raw_text=raw_text,
        )

    if not await is_trash_page(page):
        raise RuntimeError(
            "The current Proton page is not Trash."
        )

    rows = page.locator(
        "div.item-container--row"
    )

    if index < 0 or index >= await rows.count():
        raise IndexError(
            f"Conversation index {index} does not exist."
        )

    row = rows.nth(index)

    if not await row.is_visible():
        raise RuntimeError(
            f"Conversation {index} is not visible."
        )

    await row.click()

    await page.wait_for_timeout(500)

    raw_text = await page.locator(
        "body"
    ).inner_text()

    return EmailContent(
        conversation_index=index,
        raw_text=raw_text,
    )
async def get_trash_page_information(
    page: Page,
) -> TrashPageInformation:
    """Return structured information about visible Trash conversations."""
    if not await is_trash_page(page):
        raise RuntimeError(
            "The current Proton Mail page is not Trash."
        )

    rows = page.locator(
        "div.item-container--row"
    )

    conversations: list[
        RawTrashConversation
    ] = []

    for index in range(await rows.count()):
        row = rows.nth(index)

        if not await row.is_visible():
            continue

        conversations.append(
            RawTrashConversation(
                index=index,
                raw_text=(
                    await row.inner_text()
                ).strip(),
            )
        )

    return TrashPageInformation(
        title=await page.title(),
        url=page.url,
        conversation_count=len(conversations),
        conversations=conversations,
    )