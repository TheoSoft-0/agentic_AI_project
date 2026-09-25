from __future__ import annotations

import re
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


PROTON_URL = "https://mail.proton.me/"

LOGGED_IN_URL_PATTERN = re.compile( r"^https://mail\.proton\.me/u/\d+/" )

TRASH_URL_PATTERN = re.compile(r"^https://mail\.proton\.me/u/\d+/trash(?:\?.*)?$" )



def get_profile_directory( project_root: Path, profile_name: str,) -> Path:
    """Return the persistent browser profile directory."""
    return (
        project_root
        / ".browser_profile"
        / profile_name
    )

async def start_browser(project_root: Path,profile_name: str,headless: bool = False,) -> tuple[Playwright, BrowserContext, Page]:
    """Start Chromium using a persistent browser profile."""
    profile_dir = get_profile_directory( project_root, profile_name, )

    profile_dir.mkdir( parents=True, exist_ok=True,)

    playwright = await async_playwright().start()

    context = (
        await playwright.chromium
        .launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
        )
    )

    if context.pages: page = context.pages[0]
    else: page = await context.new_page()

    return playwright, context, page




async def detect_visible_buttons(
    page: Page,
) -> list[dict[str, int | str]]:
    """Return information about visible buttons."""
    buttons = page.locator("button")

    detected: list[dict[str, int | str]] = []

    for index in range(await buttons.count()):
        button = buttons.nth(index)

        if not await button.is_visible():
            continue

        text = (await button.inner_text()).strip()
        aria_label = await button.get_attribute(
            "aria-label"
        )

        if not text and not aria_label:
            continue

        detected.append(
            {
                "index": index,
                "text": text,
                "aria_label": aria_label or "",
            }
        )

    return detected








async def open_proton_trash(
    project_root: Path,
) -> tuple[
    Playwright,
    BrowserContext,
    Page,
    dict[str, object],
]:
    """Open Proton Mail and return information from Trash."""
    playwright, context, page = (
        await start_proton_browser(
            project_root=project_root,
            headless=False,
        )
    )

    await ensure_logged_in(page)
    await open_trash(page)

    trash_information = (
        await get_trash_page_information(page)
    )

    return (
        playwright,
        context,
        page,
        trash_information,
    )


async def close_browser( playwright: Playwright, context: BrowserContext,) -> None:
    """Close the browser context and Playwright."""
    await context.close()
    await playwright.stop()