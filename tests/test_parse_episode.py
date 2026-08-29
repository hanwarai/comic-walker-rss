"""parse_episode のフィルタリング仕様テスト。"""

from datetime import UTC, datetime

import main

WORK_CODE = "KC_003921_S"


def _episode(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "code": "KC_0039210000100011_E",
        "title": "第1話",
        "subTitle": "",
        "updateDate": "2022-04-27T02:00:00Z",
        "isActive": True,
    }
    base.update(overrides)
    return base


def test_returns_none_when_inactive() -> None:
    assert main.parse_episode(WORK_CODE, _episode(isActive=False)) is None


def test_returns_none_when_promotion() -> None:
    assert main.parse_episode(WORK_CODE, _episode(type="pr")) is None


def test_returns_none_when_missing_required_fields() -> None:
    assert main.parse_episode(WORK_CODE, _episode(code=None)) is None
    assert main.parse_episode(WORK_CODE, _episode(title="")) is None
    assert main.parse_episode(WORK_CODE, _episode(updateDate=None)) is None


def test_returns_none_on_invalid_date() -> None:
    assert main.parse_episode(WORK_CODE, _episode(updateDate="not a date")) is None


def test_parses_active_free_episode() -> None:
    parsed = main.parse_episode(WORK_CODE, _episode())
    assert parsed is not None
    assert parsed["unique_id"] == "KC_0039210000100011_E"
    assert parsed["title"] == "第1話"
    assert parsed["link"] == (
        "https://comic-walker.com/detail/KC_003921_S/episodes/"
        "KC_0039210000100011_E?episodeType=first"
    )
    assert parsed["pubdate"] == datetime(2022, 4, 27, 2, 0, 0, tzinfo=UTC)


def test_appends_subtitle_when_present() -> None:
    parsed = main.parse_episode(WORK_CODE, _episode(subTitle="序章"))
    assert parsed is not None
    assert parsed["title"] == "第1話 序章"
