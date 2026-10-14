import pytest

from agentic_ai.proton import (
    is_conversation_starred,
    star_conversation,
)


class FakeStarButton:
    def __init__(self, starred: bool) -> None:
        self.starred = starred
        self.click_count = 0

    @property
    def first(self) -> "FakeStarButton":
        return self

    async def count(self) -> int:
        return 1
    
  

    async def get_attribute(self, name: str) -> str | None:
        if name == "aria-pressed":
            return "true" if self.starred else "false"

        if name == "aria-label":
            return (
                "Unstar conversation"
                if self.starred
                else "Star conversation"
            )

        if name == "title":
            return None

        if name == "class":
            return "starbutton starred" if self.starred else "starbutton"

        return None

    async def inner_text(self) -> str:
        return (
            "Unstar conversation"
            if self.starred
            else "Star conversation"
        )

    async def click(self) -> None:
        self.click_count += 1
        self.starred = True

class FakeRow:
    def __init__(
        self,
        star_button: FakeStarButton,
        visible: bool = True,
    ) -> None:
        self.star_button = star_button
        self.visible = visible

    async def is_visible(self) -> bool:
        return self.visible

    def locator(self, selector: str) -> FakeStarButton:
        assert selector == "button.starbutton"
        return self.star_button


class FakeRows:
    def __init__(self, rows: list[FakeRow]) -> None:
        self.rows = rows

    async def count(self) -> int:
        return len(self.rows)

    def nth(self, index: int) -> FakeRow:
        return self.rows[index]


class FakePage:
    def __init__(
        self,
        rows: list[FakeRow],
        url: str = "https://mail.proton.me/u/1/trash",
    ) -> None:
        self.rows = FakeRows(rows)
        self.url = url

    def locator(self, selector: str) -> FakeRows:
        assert selector == "div.item-container--row"
        return self.rows
    
    async def wait_for_timeout(self, milliseconds: float) -> None:
        return 

        
class FakeBrokenStarButton(FakeStarButton):
    async def click(self) -> None:
        self.click_count += 1
        # Deliberately do not change self.starred.


@pytest.mark.asyncio
async def test_star_conversation_rejects_failed_star():
    star_button = FakeBrokenStarButton(starred=False)
    row = FakeRow(star_button)
    page = FakePage([row])

    with pytest.raises(RuntimeError):
        await star_conversation(page, index=0)

    assert star_button.click_count == 1
    assert star_button.starred is False


@pytest.mark.asyncio
async def test_is_conversation_starred_when_starred():
    star_button = FakeStarButton(starred=True)
    row = FakeRow(star_button)

    result = await is_conversation_starred(row)

    assert result is True


@pytest.mark.asyncio
async def test_is_conversation_starred_when_not_starred():
    star_button = FakeStarButton(starred=False)
    row = FakeRow(star_button)

    result = await is_conversation_starred(row)

    assert result is False


@pytest.mark.asyncio
async def test_star_conversation_stars_unstarred_email():
    star_button = FakeStarButton(starred=False)
    row = FakeRow(star_button)
    page = FakePage([row])

    await star_conversation(page, index=0)

    assert star_button.starred is True
    assert star_button.click_count == 1


@pytest.mark.asyncio
async def test_star_conversation_does_not_click_again():
    star_button = FakeStarButton(starred=True)
    row = FakeRow(star_button)
    page = FakePage([row])

    await star_conversation(page, index=0)

    assert star_button.starred is True
    assert star_button.click_count == 0


@pytest.mark.asyncio
async def test_star_conversation_rejects_invalid_index():
    row = FakeRow(FakeStarButton(False))
    page = FakePage([row])

    with pytest.raises(IndexError):
        await star_conversation(page, index=99)


@pytest.mark.asyncio
async def test_star_conversation_rejects_wrong_page():
    row = FakeRow(FakeStarButton(False))
    page = FakePage(
        [row],
        url="https://mail.proton.me/u/1/inbox",
    )

    with pytest.raises(RuntimeError):
        await star_conversation(page, index=0)


@pytest.mark.asyncio
async def test_star_conversation_rejects_invisible_row():
    row = FakeRow(
        FakeStarButton(False),
        visible=False,
    )
    page = FakePage([row])

    with pytest.raises(RuntimeError):
        await star_conversation(page, index=0)
        
