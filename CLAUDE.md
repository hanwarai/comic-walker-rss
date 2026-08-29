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

# テスト実行（requests-mock で I/O モック。カバレッジ 80% 未満で失敗）
uv run pytest

# lint / フォーマット（CI ゲート）
uv run ruff check .
uv run ruff format --check .

# 型検査（CI ゲート。対象は pyproject の [tool.mypy] files に定義しているので引数は渡さない）
uv run mypy

# コミット時に上記をまとめて走らせる
uv run pre-commit install
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
- `.pre-commit-config.yaml` — ruff / mypy は local hook として `uv run` 経由で呼ぶ。mirrors 版だと rev と uv.lock が独立に動いて結果がずれるため

## CI/CD

**`ci.yaml`** — PR ゲート:
- トリガー: `pull_request`
- 処理: `uv sync --locked --all-extras` → `ruff check` → `ruff format --check` → `mypy` → `pytest`
- main の branch protection が `check` ジョブを必須にしている（`enforce_admins: false` なのでオーナーの直接 push は従来どおり可能）。**ジョブ名 `check` を変えると必須チェックが報告されなくなる**
- 実フェッチ（`uv run main.py`）は含めない。PR を comic-walker.com の可用性に依存させないため

**`gh-pages.yaml`** — 公開:
- トリガー: main へ push、12 時間ごとの schedule、`workflow_dispatch`
- 処理: `uv sync --locked --all-extras` → `uv run mypy` → `uv run pytest` → `uv run main.py` → `feeds/` を GitHub Pages にデプロイ
- scheduled run が失敗した場合、`notify-failure` ジョブが `ci-failure` ラベルで Issue を起票（既存 open Issue があればコメント追記）

**`dependabot-auto-merge.yaml`** — dependabot PR の自動マージ:
- non-major の更新のみ `gh pr merge --auto --squash` を有効化する。major を含むグループは手動レビューに残す
- `pull_request_target` は write 権限つきトークンで動くため、PR のコードを checkout も実行もしない。検証は `ci.yaml` の責務
- リポジトリ設定の Allow auto-merge が無効だと `--auto` は失敗するため、素の `gh pr merge` にフォールバックする（`--admin` を付けないので branch protection は効いたまま）。2026-08-30 に `allow_auto_merge` / `delete_branch_on_merge` を有効化済み
- **auto-merge されたコミットは `gh-pages.yaml` を起動しない**。`GITHUB_TOKEN` が起こしたイベントは新しい workflow run を作らないという GitHub の仕様による（例外は `workflow_dispatch` と `repository_dispatch` のみ）。`--auto` で GitHub が後から代行するマージも、有効化したアクターが github-actions[bot] なので同じく抑止される。comic-walker-rss `89f82b8` と manga-one-rss `59fc518` の双方で実測確認済み
- 上記の遅延は**受容する方針**（2026-08-30 決定）。フィード内容は実行のたびにライブ取得するので鮮度には影響せず、12 時間ごとの schedule が最大 12 時間以内にデプロイを追いつかせる。依存 bump が `gh-pages.yaml` 固有の部分（`uv run main.py` の実フェッチ、`upload-pages-artifact` / `deploy-pages`）を壊した場合も、schedule 実行の失敗を `notify-failure` が Issue として起票する。即時デプロイが必要になったら PAT / GitHub App トークンへの切り替えか、github-actions グループを auto-merge 対象から外す運用に変える

**セットアップ手順の重複について**: `ci.yaml` と `gh-pages.yaml` の checkout〜`uv sync` は同一文字列に保つこと。dependabot の github-actions グループが両ファイルを 1 コミットで bump できるため。composite action への切り出しは、dependabot が `.github/actions/**` を走査するか未確認でピンが放置されうるので採らない。`--frozen` ではなく `--locked` を使うのは、lock と pyproject のずれを dependabot PR で検出するため

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
