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


TRASH_URL_PATTERN = re.compile(
    r"^https://mail\.proton\.me/u/\d+/trash(?:[?#].*)?$"
)

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


async def open_trash(page: Page) -> None:
    """Navigate directly to Trash for the logged-in Proton account."""

    if await is_trash_page(page):
        print("Already on Trash.")
        return

    # Extract the account ID from the current logged-in URL.
    account_match = re.match(
        r"^https://mail\.proton\.me/u/(\d+)(?:/|$)",
        page.url,
    )

    if account_match is None:
        raise RuntimeError(
            "Cannot determine the Proton account ID from "
            f"the current URL: {page.url!r}"
        )

    account_id = account_match.group(1)
    trash_url = f"https://mail.proton.me/u/{account_id}/trash"

    await page.goto(
        trash_url,
        wait_until="domcontentloaded",
    )

    await page.wait_for_url(
        TRASH_URL_PATTERN,
        timeout=15_000,
    )

    # Confirm that the Trash page has loaded its pagination indicator.
    page_indicator = page.locator("button").filter(
        has_text=re.compile(r"^\d+/\d+$")
    )

    await page_indicator.first.wait_for(
        state="visible",
        timeout=15_000,
    )

    if await page_indicator.count() != 1:
        raise RuntimeError(
            "Opened Trash, but could not uniquely identify "
            "its page indicator."
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


async def open_trash_conversation(
    page: Page,
    index: int,
) -> EmailContent:
    """Open a Trash conversation by its global Trash index."""

    if await is_trash_conversation_page(page):
        print("Conversation already open.")
        await return_to_trash(page)

    if not await is_trash_page(page):
        raise RuntimeError(
            "The current Proton page is not Trash."
        )

    if index < 0:
        raise IndexError(
            f"Conversation index {index} is invalid."
        )

    page_indicator = page.locator(
        'button'
    ).filter(
        has_text=re.compile(r"^\d+/\d+$")
    )

    if await page_indicator.count() != 1:
        raise RuntimeError(
            "Could not find the Trash page indicator."
        )

    page_text = (await page_indicator.inner_text()).strip()

    match = re.fullmatch(r"(\d+)/(\d+)", page_text)

    if match is None:
        raise RuntimeError(
            f"Could not parse Trash page indicator: {page_text!r}"
        )

    current_page = int(match.group(1))
    page_count = int(match.group(2))

    target_page = (index // 50) + 1
    row_index = index % 50

    if target_page > page_count:
        raise IndexError(
            f"Conversation index {index} is outside "
            f"the available Trash pages."
        )


    async def wait_for_page(expected_page: int) -> None:
        for _ in range(50):
            text = (await page_indicator.inner_text()).strip()
            match = re.fullmatch(r"(\d+)/(\d+)", text)

            if match is not None:
                actual_page = int(match.group(1))
                actual_count = int(match.group(2))

                if actual_page == expected_page:
                    if actual_count != page_count:
                        raise RuntimeError(
                            "Trash page count changed during navigation."
                        )
                    return

            await page.wait_for_timeout(100)

        text = (await page_indicator.inner_text()).strip()
        raise RuntimeError(
            f"Expected Trash page {expected_page}; "
            f"indicator remained at {text!r}."
        )

    while current_page < target_page:
        next_button = page.get_by_role(
            "button",
            name="Next page",
            exact=True,
        )

        if await next_button.is_disabled():
            raise RuntimeError(
                f"Could not reach Trash page {target_page}."
            )

        await next_button.click()
        await wait_for_page(current_page + 1)
        current_page += 1

    while current_page > target_page:
        previous_button = page.get_by_role(
            "button",
            name="Previous page",
            exact=True,
        )

        if await previous_button.is_disabled():
            raise RuntimeError(
                f"Could not return to Trash page {target_page}."
            )

        await previous_button.click()
        await wait_for_page(current_page - 1)
        current_page -= 1
 
    rows = page.locator(
        "div.item-container--row"
    )

    row_count = await rows.count()

    if row_index >= row_count:
        raise IndexError(
            f"Conversation index {index} maps to row "
            f"{row_index}, but page {target_page} only "
            f"contains {row_count} rows."
        )

    row = rows.nth(row_index)

    if not await row.is_visible():
        raise RuntimeError(
            f"Conversation {index} is not visible."
        )

    await row.click()

    await page.wait_for_timeout(500)

    if not await is_trash_conversation_page(page):
        raise RuntimeError(
            "Proton did not open the requested conversation."
        )

    raw_text = await page.locator(
        "body"
    ).inner_text()

    return EmailContent(
        conversation_index=index,
        raw_text=raw_text,
    )

async def get_trash_page_information(
    page: Page,
    *,
    page_number: int | None = None,
) -> TrashPageInformation:
    """Return structured information about the visible Trash page."""
    if not await is_trash_page(page):
        raise RuntimeError(
            "The current Proton Mail page is not Trash."
        )

    page_indicator = page.locator("button").filter(
        has_text=re.compile(r"^\d+/\d+$")
    )

    if await page_indicator.count() != 1:
        raise RuntimeError(
            "Could not find the Trash page indicator."
        )

    page_text = (await page_indicator.inner_text()).strip()

    match = re.fullmatch(r"(\d+)/(\d+)", page_text)

    if match is None:
        raise RuntimeError(
            f"Could not parse Trash page indicator: {page_text!r}"
        )

    detected_page_number = int(match.group(1))
    detected_page_count = int(match.group(2))

    if (
        page_number is not None
        and detected_page_number != page_number
    ):
        raise RuntimeError(
            f"Expected Trash page {page_number}, "
            f"but Proton shows page {detected_page_number}."
        )

    rows = page.locator("div.item-container--row")

    conversations: list[RawTrashConversation] = []

    row_count = await rows.count()

    for row_index in range(row_count):
        row = rows.nth(row_index)

        if not await row.is_visible():
            continue

        global_index = (
            (detected_page_number - 1) * 50
            + row_index
        )

        conversations.append(
            RawTrashConversation(
                index=global_index,
                page_number=detected_page_number,
                row_index=row_index,
                raw_text=(
                    await row.inner_text()
                ).strip(),
            )
        )

    return TrashPageInformation(
        title=await page.title(),
        url=page.url,
        page_number=detected_page_number,
        page_count=detected_page_count,
        conversation_count=len(conversations),
        conversations=conversations,
    )



async def get_recent_trash_conversations(
    page: Page,
    max_pages: int = 2,
) -> list[RawTrashConversation]:
    """Collect conversations from the first N Trash pages."""

    if max_pages < 1:
        raise ValueError("max_pages must be at least 1.")

    if not await is_trash_page(page):
        raise RuntimeError(
            "The current Proton Mail page is not Trash."
        )

    page_indicator = page.locator("button").filter(
        has_text=re.compile(r"^\d+/\d+$")
    )

    async def read_page_state() -> tuple[int, int]:
        if await page_indicator.count() != 1:
            raise RuntimeError(
                "Could not find the Trash page indicator."
            )

        text = (await page_indicator.inner_text()).strip()
        match = re.fullmatch(r"(\d+)/(\d+)", text)

        if match is None:
            raise RuntimeError(
                f"Could not parse Trash page indicator: {text!r}"
            )

        return int(match.group(1)), int(match.group(2))

    async def wait_for_page(
        expected_page: int,
    ) -> tuple[int, int]:
        # Wait for Proton's displayed page number to change.
        for _ in range(50):
            current, total = await read_page_state()

            if current == expected_page:
                return current, total

            await page.wait_for_timeout(100)

        current, total = await read_page_state()
        raise RuntimeError(
            f"Expected Trash page {expected_page}, "
            f"but Proton shows {current}/{total}."
        )

    current_page, page_count = await read_page_state()

    # Start at page 1 so global conversation indexes are consistent.
    while current_page > 1:
        previous_button = page.get_by_role(
            "button",
            name="Previous page",
            exact=True,
        )

        if await previous_button.is_disabled():
            raise RuntimeError(
                "Could not navigate back to Trash page 1."
            )

        await previous_button.click()
        current_page, page_count = await wait_for_page(
            current_page - 1
        )

    pages_to_scan = min(max_pages, page_count)
    conversations: list[RawTrashConversation] = []

    for expected_page in range(1, pages_to_scan + 1):
        if expected_page > 1:
            next_button = page.get_by_role(
                "button",
                name="Next page",
                exact=True,
            )

            if await next_button.is_disabled():
                raise RuntimeError(
                    f"Could not navigate to Trash page "
                    f"{expected_page}."
                )

            await next_button.click()
            await wait_for_page(expected_page)

        page_info = await get_trash_page_information(
            page,
            page_number=expected_page,
        )
        conversations.extend(page_info.conversations)

    return conversations


async def get_all_trash_conversations( page: Page, ) -> list[RawTrashConversation]:
    """Collect conversations from every Trash page."""
    if not await is_trash_page(page):
        raise RuntimeError(
            "The current Proton page is not Trash."
        )

    page_indicator = page.locator("button").filter(
        has_text=re.compile(r"^\d+/\d+$")
    )

    if await page_indicator.count() != 1:
        raise RuntimeError(
            "Could not find the Trash page indicator."
        )

    page_text = (await page_indicator.inner_text()).strip()

    match = re.fullmatch(r"(\d+)/(\d+)", page_text)

    if match is None:
        raise RuntimeError(
            f"Could not parse Trash page indicator: {page_text!r}"
        )

    current_page = int(match.group(1))
    page_count = int(match.group(2))

    # Always begin collecting from page 1.
    while current_page > 1:
        previous_button = page.get_by_role(
            "button",
            name="Previous page",
            exact=True,
        )

        for _ in range(50):
            if not await previous_button.is_disabled():
                break

            await page.wait_for_timeout(100)
        else:
            raise RuntimeError(
                "Previous page remained disabled while "
                f"trying to return to page {current_page - 1}."
            )

        await previous_button.click()

        expected_page = current_page - 1

        for _ in range(50):
            await page.wait_for_timeout(100)

            page_text = (await page_indicator.inner_text()).strip()

            if page_text == f"{expected_page}/{page_count}":
                break
        else:
            raise RuntimeError(
                f"Proton did not reach Trash page {expected_page}."
            )

        current_page = expected_page

    conversations: list[RawTrashConversation] = []

    # Collect every page.
    for expected_page in range(1, page_count + 1):
        page_information = await get_trash_page_information(
            page,
            page_number=expected_page,
        )

        conversations.extend(
            page_information.conversations
        )

        if expected_page == page_count:
            break

        next_button = page.get_by_role(
            "button",
            name="Next page",
            exact=True,
        )

        # Proton may temporarily disable the button while
        # the current page finishes rendering.
        for _ in range(50):
            if not await next_button.is_disabled():
                break

            await page.wait_for_timeout(100)
        else:
            raise RuntimeError(
                f"Next page remained disabled after "
                f"Trash page {expected_page}."
            )

        await next_button.click()

        expected_next_page = expected_page + 1

        # Wait for Proton to actually finish the page transition.
        for _ in range(50):
            await page.wait_for_timeout(100)

            page_text = (await page_indicator.inner_text()).strip()

            if page_text == f"{expected_next_page}/{page_count}":
                break
        else:
            raise RuntimeError(
                f"Proton did not reach Trash page "
                f"{expected_next_page}."
            )

    return conversations