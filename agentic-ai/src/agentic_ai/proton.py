from __future__ import annotations

import re

from playwright.async_api import (
    BrowserContext,
    Locator,
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


async def star_conversation( page: Page, index: int,) -> None:
    """Mark a Trash conversation as starred."""

    if not await is_trash_page(page):
        raise RuntimeError( "The current Proton page is not Trash." )

    rows = page.locator( "div.item-container--row" )

    row_count = await rows.count()

    if row_count == 0:
        raise RuntimeError( "No Trash conversations are visible." )

    if index < 0 or index >= row_count:
        raise IndexError(
            f"Conversation index {index} is invalid. "
            f"Valid indexes: 0-{row_count - 1}."
        )

    row = rows.nth(index)

    if not await row.is_visible():
        raise RuntimeError( f"Conversation {index} is not visible." )

    already_starred = ( await is_conversation_starred(row) )

    if already_starred:
        print( f"Conversation {index} is already starred." )
        return

    star_button = row.locator( "button.starbutton" )

    await star_button.click()

    await page.wait_for_timeout(300)

    starred_after_click = ( await is_conversation_starred(row) )

    if not starred_after_click:
        raise RuntimeError(
            f"Conversation {index} was clicked, "
            "but verification shows it is not starred."
        )

    print( f"Conversation {index} is now starred." )

async def is_conversation_starred( row: Locator, ) -> bool:
    """Return whether a conversation is currently starred."""
    star_button = row.locator( "button.starbutton" )

    if await star_button.count() != 1:
        raise RuntimeError(
            "Conversation does not have exactly "
            "one star button."
        )

    button = star_button.first

    aria_pressed = await button.get_attribute( "aria-pressed" )

    if aria_pressed is not None:
        if aria_pressed == "true":
            return True

        if aria_pressed == "false":
            return False

    aria_label   = await button.get_attribute( "aria-label" )
    title        = await button.get_attribute( "title" )
    text         = ( await button.inner_text() ).strip()
    class_name   = await button.get_attribute( "class" ) or ""
    state_values = [  aria_label or "", title or "", text, class_name, ]
    combined     = " ".join( state_values ).lower()

    if ( "unstar" in combined or "starred" in combined ):
        return True

    if ( "star conversation" in combined or "not starred" in combined ):
        return False

    raise RuntimeError(
        "Could not determine the star state. "
        f"aria-label={aria_label!r}, "
        f"title={title!r}, "
        f"text={text!r}, "
        f"class={class_name!r}"
    )

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


async def return_to_trash( page: Page, ) -> None:
    """Return from an opened conversation to Trash."""

    if await is_trash_page(page):
        print("Already on Trash.")
        return

    if not await is_trash_conversation_page(page):
        raise RuntimeError(
            "The current Proton page is neither "
            "Trash nor a Trash conversation."
        )

    await ensure_navigation_expanded(page)

    trash_link = page.locator( 'a[href$="/trash"]' )

    await trash_link.wait_for(  state="visible" )

    await trash_link.click()

    await page.wait_for_url( TRASH_URL_PATTERN )

    print("Returned to Trash.")

async def open_trash_conversation( page: Page, index: int,) -> EmailContent:
    """Open a specific Trash conversation."""

    if await is_trash_conversation_page(page):
        print("Conversation already open.")
        await return_to_trash(page)

    if not await is_trash_page(page):
        raise RuntimeError( "The current Proton page is not Trash." )

    rows = page.locator( "div.item-container--row")

    row_count = await rows.count()

    if index < 0 or index >= row_count:
        raise IndexError(
            f"Conversation index {index} is invalid. "
            f"Available rows: 0-{row_count - 1}."
        )

    row = rows.nth(index)

    if not await row.is_visible():
        raise RuntimeError(f"Conversation {index} is not visible.")

    await row.click()

    await page.wait_for_timeout(500)

    if not await is_trash_conversation_page(page):
        raise RuntimeError( "Proton did not open the requested conversation." )

    raw_text = await page.locator(  "body" ).inner_text()

    return EmailContent( conversation_index=index, raw_text=raw_text, )
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