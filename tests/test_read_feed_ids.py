"""feed.csv パース関数 read_feed_ids の仕様テスト。"""

from pathlib import Path

import pytest

import main


def _write(tmp_path: Path, content: str) -> Path:
    csv_path = tmp_path / "feed.csv"
    csv_path.write_text(content)
    return csv_path


def test_reads_valid_work_codes(tmp_path: Path) -> None:
    path = _write(tmp_path, "KC_003921_S\nKC_000001_S\n")
    assert list(main.read_feed_ids(path)) == ["KC_003921_S", "KC_000001_S"]


def test_skips_empty_lines_and_whitespace(tmp_path: Path) -> None:
    path = _write(tmp_path, "KC_003921_S\n\n   \nKC_000001_S\n")
    assert list(main.read_feed_ids(path)) == ["KC_003921_S", "KC_000001_S"]


def test_skips_invalid_codes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = _write(tmp_path, "KC_003921_S\n../etc/passwd\nfoo\n01153\nKC_000001_S\n")
    with caplog.at_level("WARNING", logger="comic-walker-rss"):
        assert list(main.read_feed_ids(path)) == ["KC_003921_S", "KC_000001_S"]
    assert any("invalid work code" in rec.message for rec in caplog.records)


def test_deduplicates_repeated_codes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = _write(tmp_path, "KC_003921_S\nKC_000001_S\nKC_003921_S\nKC_000001_S\nKC_000002_S\n")
    with caplog.at_level("WARNING", logger="comic-walker-rss"):
        assert list(main.read_feed_ids(path)) == [
            "KC_003921_S",
            "KC_000001_S",
            "KC_000002_S",
        ]
    assert sum("duplicate work code" in rec.message for rec in caplog.records) == 2


def test_uses_only_first_column(tmp_path: Path) -> None:
    path = _write(tmp_path, "KC_003921_S,extra,columns\nKC_000001_S,ignored\n")
    assert list(main.read_feed_ids(path)) == ["KC_003921_S", "KC_000001_S"]


def test_strips_surrounding_whitespace(tmp_path: Path) -> None:
    path = _write(tmp_path, "  KC_003921_S  \n")
    assert list(main.read_feed_ids(path)) == ["KC_003921_S"]
