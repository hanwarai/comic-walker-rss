# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ComicWalker（comic-walker.com）の無料エピソードを取得し、Atom RSS フィードとして配信するジェネレーター。GitHub Actions で 12 時間ごとに自動実行され、GitHub Pages として公開される。

## Commands

```bash
# 依存パッケージインストール
uv sync --all-extras

# フィード生成
uv run main.py

# テスト実行（requests-mock で I/O モック）
uv run pytest

# 型検査（CI ゲート）
uv run mypy main.py
```

## Architecture

```
feed.csv → main.py → feeds/*.xml + feeds/index.html → GitHub Pages
```

**処理フロー（main.py）:**
1. `feed.csv` から作品コード（`KC_XXXXXX_S` 形式）を読み込む
2. `https://comic-walker.com/detail/{workCode}/` を GET し、`<script id="__NEXT_DATA__">` 内の JSON をパース
3. JSON から作品情報（タイトル・あらすじ・サムネイル）と `firstEpisodes.result[]` を取り出す
4. `isActive == True` のエピソードのみ Atom フィードに追加（無料公開期間内のもの）。`firstEpisodes` は昇順なので `reversed()` して新しい話が先頭に来るようにする
5. Jinja2 テンプレート（`templates/index.html`）で `feeds/index.html` を生成

**主要ファイル:**
- `main.py` — 全処理ロジック
- `feed.csv` — トラッキング対象作品コードのリスト（1 列、`KC_XXXXXX_S` 形式）
- `templates/index.html` — Jinja2 テンプレート（Bootstrap 5）
- `feeds/` — 生成ファイル出力先（gitignore 済み、`.gitkeep` のみ管理）

## CI/CD

GitHub Actions（`.github/workflows/gh-pages.yaml`）:
- トリガー: main へ push、12 時間ごとの schedule、`workflow_dispatch`
- 処理: `uv sync` → `uv run mypy main.py` → `uv run pytest` → `uv run main.py` → `feeds/` を GitHub Pages にデプロイ
- scheduled run が失敗した場合、`notify-failure` ジョブが `ci-failure` ラベルで Issue を起票（既存 open Issue があればコメント追記）

## Notes

- パッケージマネージャーは `uv`（`pip` は使わない）
- Python 3.13（`.python-version`）
- 出力 URL: `https://hanwarai.github.io/comic-walker-rss/{workCode}.xml`
- `read_feed_ids` は `KC_<digits>_S` 形式の ID のみを許可し、重複は自動除去
- `updateDate` は ISO 8601（UTC）。`feedgenerator` がタイムゾーン付き `datetime` を要求するため、そのまま `datetime.fromisoformat` で UTC として解釈する

## Gotchas

- 作品ページの DOM ではなく `__NEXT_DATA__` の JSON にエピソード情報が入っている。Next.js の構造（`props.pageProps.dehydratedState.queries[0].state.data`）が変わるとパースが壊れる
- `firstEpisodes` と `latestEpisodes` は同じ全エピソード集合（並び順だけ違う）。本ジェネレータは `firstEpisodes` を使う
- `isActive: True` = 現在無料で読める / `False` = 無料公開期間が終了し有料のみ。`deliveryPeriod` は無料期間の終了時刻（`9999-12-31T14:59:59Z` は恒久無料）
- WAF/Bot 対策は現状なし。User-Agent を付ければ素の `requests` で取得可能
