"""ComicWalker（comic-walker.com）の無料エピソードを取得する Atom RSS ジェネレータ。"""

from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import feedgenerator
import requests
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("comic-walker-rss")

BASE_URL = "https://comic-walker.com"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/detail/{{work_code}}/"
EPISODE_URL_TEMPLATE = (
    f"{BASE_URL}/detail/{{work_code}}/episodes/{{episode_code}}?episodeType=first"
)
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# パストラバーサル防止のための作品コード検証パターン
WORK_CODE_RE = re.compile(r"^KC_\d+_[A-Z]$")

FEEDS_DIR = Path("feeds")
FEED_LIST_PATH = Path("feed.csv")
TEMPLATE_DIR = Path("templates")


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def extract_next_data(html: str) -> dict[str, Any] | None:
    """`<script id="__NEXT_DATA__">` の JSON を辞書として返す。"""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag is None or not tag.string:
        return None
    try:
        result = json.loads(tag.string)
    except json.JSONDecodeError:
        return None
    if not isinstance(result, dict):
        return None
    return result


def find_work_data(next_data: dict[str, Any]) -> dict[str, Any] | None:
    """`__NEXT_DATA__` から `/api/contents/details/work` クエリのデータを取り出す。"""
    queries = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("dehydratedState", {})
        .get("queries", [])
    )
    for query in queries:
        key = query.get("queryKey")
        if (
            isinstance(key, list)
            and key
            and key[0] == "/api/contents/details/work"
        ):
            data = query.get("state", {}).get("data")
            if isinstance(data, dict):
                return data
    return None


def parse_episode(work_code: str, episode: dict[str, Any]) -> dict[str, Any] | None:
    """1 エピソード分の dict を整形。無料公開外（`isActive == False`）と販促 (`type == "pr"`) は捨てる。"""
    if not episode.get("isActive"):
        return None
    if episode.get("type") == "pr":
        return None
    code = episode.get("code")
    title = episode.get("title")
    update_date = episode.get("updateDate")
    if not code or not title or not update_date:
        return None
    try:
        # ISO 8601。`Z` 付きはそのままだと fromisoformat が読めないので置換
        pubdate = datetime.fromisoformat(update_date.replace("Z", "+00:00"))
    except ValueError:
        return None

    sub_title = episode.get("subTitle") or ""
    full_title = f"{title} {sub_title}".strip() if sub_title else title

    return {
        "unique_id": str(code),
        "title": full_title,
        "link": EPISODE_URL_TEMPLATE.format(
            work_code=work_code, episode_code=code
        ),
        "pubdate": pubdate,
    }


def build_feed_for_work(
    session: requests.Session, work_code: str
) -> dict[str, str] | None:
    detail_url = DETAIL_URL_TEMPLATE.format(work_code=work_code)
    logger.info("%s %s", work_code, detail_url)

    response = session.get(detail_url, timeout=REQUEST_TIMEOUT)
    if not response.ok:
        logger.warning("failed to retrieve %s (status=%s)", work_code, response.status_code)
        return None

    next_data = extract_next_data(response.text)
    if next_data is None:
        logger.warning("no __NEXT_DATA__ for %s", work_code)
        return None

    work_data = find_work_data(next_data)
    if work_data is None:
        logger.warning("no work data for %s", work_code)
        return None

    work = work_data.get("work")
    if not isinstance(work, dict):
        logger.warning("no work entry for %s", work_code)
        return None

    title = work.get("title")
    if not title:
        logger.warning("no title for %s", work_code)
        return None
    description = work.get("summary") or ""
    image = work.get("thumbnail") or work.get("bookCover")

    rss = feedgenerator.Atom1Feed(
        title=title,
        link=detail_url,
        description=description,
        language="ja",
        image=image,
    )

    first_episodes = work_data.get("firstEpisodes") or {}
    episodes = first_episodes.get("result", []) if isinstance(first_episodes, dict) else []

    free_count = 0
    for ep in episodes:
        if not isinstance(ep, dict):
            continue
        parsed = parse_episode(work_code, ep)
        if parsed is None:
            continue
        rss.add_item(
            unique_id=parsed["unique_id"],
            title=parsed["title"],
            link=parsed["link"],
            description="",
            pubdate=parsed["pubdate"],
            content="",
        )
        free_count += 1

    logger.info("%s %s (%d free episodes)", work_code, title, free_count)

    FEEDS_DIR.mkdir(exist_ok=True)
    with (FEEDS_DIR / f"{work_code}.xml").open("w", encoding="utf-8") as fp:
        rss.write(fp, "utf-8")

    return {"id": work_code, "title": title}


def read_feed_ids(path: Path) -> Iterator[str]:
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fp:
        for row in csv.reader(fp):
            if not row:
                continue
            work_code = row[0].strip()
            if not work_code:
                continue
            if not WORK_CODE_RE.fullmatch(work_code):
                logger.warning("invalid work code %r, skipping", work_code)
                continue
            if work_code in seen:
                logger.warning("duplicate work code %r, skipping", work_code)
                continue
            seen.add(work_code)
            yield work_code


def render_index(feeds: list[dict[str, str]]) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("index.html")
    FEEDS_DIR.mkdir(exist_ok=True)
    (FEEDS_DIR / "index.html").write_text(template.render(feeds=feeds), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = create_session()
    rendered: list[dict[str, str]] = []
    for work_code in read_feed_ids(FEED_LIST_PATH):
        try:
            result = build_feed_for_work(session, work_code)
        except Exception:
            logger.exception("failed to build feed for %s", work_code)
            continue
        if result:
            rendered.append(result)
    render_index(rendered)


if __name__ == "__main__":
    main()
