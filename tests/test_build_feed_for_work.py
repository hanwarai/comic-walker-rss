"""build_feed_for_work のエンドツーエンド (HTTP モック) テスト。"""

import json
from pathlib import Path

import pytest
import requests_mock as rm_module

import main

WORK_CODE = "KC_003921_S"
DETAIL_URL = main.DETAIL_URL_TEMPLATE.format(work_code=WORK_CODE)
FIXTURES = Path(__file__).parent / "fixtures"


def _detail_html(
    title: str = "テスト作品",
    summary: str = "あらすじ本文",
    thumbnail: str = "https://example.com/cover.jpg",
    episodes: list[dict[str, object]] | None = None,
) -> str:
    next_data = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "queryKey": [
                                "/api/contents/details/work",
                                {"workCode": WORK_CODE},
                            ],
                            "state": {
                                "data": {
                                    "work": {
                                        "title": title,
                                        "summary": summary,
                                        "thumbnail": thumbnail,
                                    },
                                    "firstEpisodes": {
                                        "total": len(episodes or []),
                                        "result": episodes or [],
                                    },
                                }
                            },
                        }
                    ]
                }
            }
        }
    }
    payload = json.dumps(next_data, ensure_ascii=False)
    return (
        "<!doctype html><html><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'
        "</body></html>"
    )


@pytest.fixture
def feeds_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(main, "FEEDS_DIR", tmp_path)
    return tmp_path


def test_filters_inactive_episodes(requests_mock: rm_module.Mocker, feeds_dir: Path) -> None:
    html = _detail_html(
        title="魔術師クノンは見えている",
        episodes=[
            {
                "code": "KC_0039210000100011_E",
                "title": "第1話",
                "subTitle": "",
                "updateDate": "2022-04-27T02:00:00Z",
                "isActive": True,
            },
            {
                "code": "KC_0039210000200011_E",
                "title": "第2話",
                "subTitle": "",
                "updateDate": "2023-11-09T02:00:00Z",
                "isActive": False,  # 期限切れの無料公開は除外
            },
        ],
    )
    requests_mock.get(DETAIL_URL, text=html)

    result = main.build_feed_for_work(main.create_session(), WORK_CODE)
    assert result == {"id": WORK_CODE, "title": "魔術師クノンは見えている"}

    xml = (feeds_dir / f"{WORK_CODE}.xml").read_text(encoding="utf-8")
    assert "第1話" in xml
    assert "第2話" not in xml
    assert (
        "https://comic-walker.com/detail/KC_003921_S/episodes/"
        "KC_0039210000100011_E?episodeType=first"
    ) in xml


def test_emits_episodes_in_descending_order(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    """firstEpisodes は昇順で来るが、フィードは新しい話を先頭にする。"""
    html = _detail_html(
        episodes=[
            {
                "code": "KC_OLD_E",
                "title": "第1話",
                "subTitle": "",
                "updateDate": "2022-04-27T02:00:00Z",
                "isActive": True,
            },
            {
                "code": "KC_MID_E",
                "title": "第2話",
                "subTitle": "",
                "updateDate": "2023-11-09T02:00:00Z",
                "isActive": True,
            },
            {
                "code": "KC_NEW_E",
                "title": "第3話",
                "subTitle": "",
                "updateDate": "2026-04-27T02:00:00Z",
                "isActive": True,
            },
        ],
    )
    requests_mock.get(DETAIL_URL, text=html)

    main.build_feed_for_work(main.create_session(), WORK_CODE)
    xml = (feeds_dir / f"{WORK_CODE}.xml").read_text(encoding="utf-8")
    pos_old = xml.index("KC_OLD_E")
    pos_mid = xml.index("KC_MID_E")
    pos_new = xml.index("KC_NEW_E")
    assert pos_new < pos_mid < pos_old


def test_returns_none_on_404(requests_mock: rm_module.Mocker, feeds_dir: Path) -> None:
    requests_mock.get(DETAIL_URL, status_code=404)
    assert main.build_feed_for_work(main.create_session(), WORK_CODE) is None
    assert not (feeds_dir / f"{WORK_CODE}.xml").exists()


def test_returns_none_without_next_data(requests_mock: rm_module.Mocker, feeds_dir: Path) -> None:
    requests_mock.get(DETAIL_URL, text="<html><body>nope</body></html>")
    assert main.build_feed_for_work(main.create_session(), WORK_CODE) is None


def test_returns_none_without_work_query(requests_mock: rm_module.Mocker, feeds_dir: Path) -> None:
    payload = json.dumps({"props": {"pageProps": {"dehydratedState": {"queries": []}}}})
    html = (
        "<html><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'
        "</body></html>"
    )
    requests_mock.get(DETAIL_URL, text=html)
    assert main.build_feed_for_work(main.create_session(), WORK_CODE) is None


def test_real_fixture_yields_active_episodes(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    """実際の comic-walker.com の HTML スナップショットでパースが成立すること。"""
    fixture = FIXTURES / "KC_003921_S.html"
    requests_mock.get(DETAIL_URL, text=fixture.read_text(encoding="utf-8"))

    result = main.build_feed_for_work(main.create_session(), WORK_CODE)

    assert result is not None
    assert result["id"] == WORK_CODE
    assert result["title"] == "魔術師クノンは見えている"

    xml = (feeds_dir / f"{WORK_CODE}.xml").read_text(encoding="utf-8")
    # 恒久無料の第1話は必ず含まれる
    assert "KC_0039210000100011_E" in xml
    assert "第1話" in xml
