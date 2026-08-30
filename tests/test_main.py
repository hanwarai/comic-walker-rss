"""main() の index 復旧経路と read_existing_feed_title のテスト。"""

import json
from pathlib import Path

import pytest
import requests_mock as rm_module

import main

WORK_A = "KC_003921_S"
WORK_B = "KC_000455_S"


def _detail_html(title: str) -> str:
    """`__NEXT_DATA__` を 1 話だけ含む最小の作品ページ。"""
    next_data = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "queryKey": ["/api/contents/details/work", {}],
                            "state": {
                                "data": {
                                    "work": {"title": title, "summary": "", "thumbnail": ""},
                                    "firstEpisodes": {
                                        "total": 1,
                                        "result": [
                                            {
                                                "code": "KC_0000000000100011_E",
                                                "title": "第1話",
                                                "subTitle": "",
                                                "updateDate": "2026-04-27T02:00:00Z",
                                                "isActive": True,
                                            }
                                        ],
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


def _detail_url(work_code: str) -> str:
    return main.DETAIL_URL_TEMPLATE.format(work_code=work_code)


@pytest.fixture
def feeds_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "feeds"
    out.mkdir()
    monkeypatch.setattr(main, "FEEDS_DIR", out)
    return out


def _write_feed_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    path = tmp_path / "feed.csv"
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(main, "FEED_LIST_PATH", path)


# ---------------------------------------------------------------------------
# read_existing_feed_title (前回デプロイ分からの復旧)
# ---------------------------------------------------------------------------


def test_read_existing_feed_title_reads_generated_feed(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    """自分が生成した Atom XML から作品名を読み戻せる (feedgenerator との往復)。"""
    requests_mock.get(_detail_url(WORK_A), text=_detail_html("魔術師クノンは見えている"))
    main.build_feed_for_work(main.create_session(), WORK_A)

    assert main.read_existing_feed_title(WORK_A) == "魔術師クノンは見えている"


def test_read_existing_feed_title_returns_none_when_missing(feeds_dir: Path) -> None:
    assert main.read_existing_feed_title(WORK_A) is None


def test_read_existing_feed_title_returns_none_for_broken_xml(
    feeds_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (feeds_dir / f"{WORK_A}.xml").write_text("<feed><unclosed>", encoding="utf-8")

    with caplog.at_level("WARNING", logger="comic-walker-rss"):
        assert main.read_existing_feed_title(WORK_A) is None
    assert f"could not parse existing feed for {WORK_A}" in caplog.text


def test_read_existing_feed_title_returns_none_without_title(feeds_dir: Path) -> None:
    (feeds_dir / f"{WORK_A}.xml").write_text(
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><id>x</id></feed>',
        encoding="utf-8",
    )

    assert main.read_existing_feed_title(WORK_A) is None


# ---------------------------------------------------------------------------
# main() の index 組み立て
# ---------------------------------------------------------------------------


def test_main_keeps_failed_work_in_index_when_seeded(
    requests_mock: rm_module.Mocker,
    feeds_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取得に失敗しても、seed 済みの XML があれば index に残す。

    gh-pages.yaml が公開中のフィードを seed してから main.py を回すので、
    一時的な取得失敗で作品が一覧から消えない。
    """
    _write_feed_csv(tmp_path, monkeypatch, f"{WORK_A}\n{WORK_B}\n")
    # WORK_B は「前回デプロイ分」として seed 済みの状態にする
    requests_mock.get(_detail_url(WORK_B), text=_detail_html("転生したらスライムだった件"))
    main.build_feed_for_work(main.create_session(), WORK_B)
    seeded = (feeds_dir / f"{WORK_B}.xml").read_text(encoding="utf-8")

    requests_mock.reset()
    requests_mock.get(_detail_url(WORK_A), text=_detail_html("魔術師クノンは見えている"))
    requests_mock.get(_detail_url(WORK_B), status_code=500)

    main.main()

    html = (feeds_dir / "index.html").read_text(encoding="utf-8")
    assert f'<a href="{WORK_A}.xml">魔術師クノンは見えている</a>' in html
    assert f'<a href="{WORK_B}.xml">転生したらスライムだった件</a>' in html, (
        "seed 済みなら index に残るはず"
    )
    # seed した XML は上書きされずそのまま残る (購読者の feed URL が 404 にならない)
    assert (feeds_dir / f"{WORK_B}.xml").read_text(encoding="utf-8") == seeded


def test_main_omits_work_without_any_feed(
    requests_mock: rm_module.Mocker,
    feeds_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """seed も取得も無い作品は index から落とす (壊れたリンクを出さない)。"""
    _write_feed_csv(tmp_path, monkeypatch, f"{WORK_A}\n{WORK_B}\n")
    requests_mock.get(_detail_url(WORK_A), text=_detail_html("魔術師クノンは見えている"))
    requests_mock.get(_detail_url(WORK_B), status_code=500)

    with caplog.at_level("WARNING", logger="comic-walker-rss"):
        main.main()

    html = (feeds_dir / "index.html").read_text(encoding="utf-8")
    assert f'<a href="{WORK_A}.xml">' in html
    assert f'<a href="{WORK_B}.xml">' not in html
    assert f"no feed for {WORK_B}, omitting from index" in caplog.text


def test_main_keeps_feed_csv_order(
    requests_mock: rm_module.Mocker,
    feeds_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_feed_csv(tmp_path, monkeypatch, f"{WORK_B}\n{WORK_A}\n")
    requests_mock.get(_detail_url(WORK_A), text=_detail_html("あとに書いた方"))
    requests_mock.get(_detail_url(WORK_B), text=_detail_html("さきに書いた方"))

    main.main()

    html = (feeds_dir / "index.html").read_text(encoding="utf-8")
    assert html.index("さきに書いた方") < html.index("あとに書いた方")
