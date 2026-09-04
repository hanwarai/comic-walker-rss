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
5. 今回取得できなかった作品は `read_existing_feed_title()` が seed 済みの `feeds/{workCode}.xml` から作品名を読み戻し、index に残す（seed も取得も無い場合だけ index から落とす）
6. Jinja2 テンプレート（`templates/index.html`）で `feeds/index.html` を生成

**主要ファイル:**
- `main.py` — 全処理ロジック
- `feed.csv` — トラッキング対象作品コードのリスト（1 列、`KC_XXXXXX_S` 形式）
- `templates/index.html` — Jinja2 テンプレート（Bootstrap 5）
- `feeds/` — 生成ファイル出力先（gitignore 済み、`.gitkeep` のみ管理）
- `tests/` — pytest。HTTP は `requests-mock` でモックし、実ページのスナップショットは `tests/fixtures/*.html` に置く
- `.pre-commit-config.yaml` — ruff / mypy は local hook として `uv run` 経由で呼ぶ。mirrors 版だと rev と uv.lock が独立に動いて結果がずれるため
- `.github/dependabot.yaml` — github-actions / uv / pre-commit の 3 エコシステムを weekly で追跡

## CI/CD

**`ci.yaml`** — PR ゲート:
- トリガー: `pull_request`
- 処理: `uv sync --locked --all-extras` → **actionlint** → **潰れた式の guard** → `ruff check` → `ruff format --check` → `mypy` → `pytest`
- actionlint（ワークフロー定義の lint）は `raven-actions/actionlint` を SHA ピン + バージョンコメントで使う。actionlint 本体のバージョンは action 既定の `latest` に任せる — ここを固定すると Dependabot が追えないピンになり黙って腐るため。pre-commit hook にはしない（Go か Docker がローカルに必要になるので CI 限定にしている）
- **潰れた式の guard**（actionlint の直後）は、二重波括弧が一重に潰れた式を grep で弾く。`${ github.x }` / `${github.x}` は YAML としてもワークフロー定義としても妥当な**ただの文字列**なので actionlint も `yaml.safe_load` も警告を出さず、CI が green のまま壊れる。2026-09-04 に 6 リポジトリの `dependabot-auto-merge.yaml` がこれで壊れ、`PR_URL` / `GH_TOKEN` がリテラルのまま渡って Dependabot PR が約 5 日滞留した。シェル変数の展開は波括弧の直後に空白を置かず変数名にドットや括弧も含まないため、`${VAR}` や `${err:-default}` は誤検知しない
- main の branch protection が `check` ジョブを必須にしている（`enforce_admins: false` なのでオーナーの直接 push は従来どおり可能）。**ジョブ名 `check` を変えると必須チェックが報告されなくなる**
- 実フェッチ（`uv run main.py`）は含めない。PR を comic-walker.com の可用性に依存させないため

**`gh-pages.yaml`** — 公開:
- トリガー: main へ push、12 時間ごとの schedule、`workflow_dispatch`
- 処理: `uv sync --locked --all-extras` → `uv run mypy` → `uv run pytest` → **公開中の `feeds/*.xml` を curl で seed** → `uv run main.py` → `feeds/` を GitHub Pages にデプロイ
- seed が必要な理由: `feeds/` は `.gitkeep` しか追跡していないので checkout 直後は空。取得に失敗した作品はその回の `main.py` が XML を書けず、seed が無いとデプロイから丸ごと落ちて `{workCode}.xml` が 404 になる（購読者に影響し、復旧は次の成功実行まで最大 12 時間）。seed 対象は `feed.csv` の作品コードに限る — 公開中のファイルをグロブで拾うと `feed.csv` から消した作品が復活してしまう
- scheduled run が失敗した場合、`notify-failure` ジョブが `ci-failure` ラベルで Issue を起票（既存 open Issue があればコメント追記）

**`dependabot-auto-merge.yaml`** — dependabot PR の自動マージ:
- non-major の更新のみ `gh pr merge --auto --squash` を有効化する。major を含むグループは手動レビューに残す
- `pull_request_target` は write 権限つきトークンで動くため、PR のコードを checkout も実行もしない。検証は `ci.yaml` の責務
- リポジトリ設定の Allow auto-merge が無効だと `--auto` は失敗するため、素の `gh pr merge` にフォールバックする（`--admin` を付けないので branch protection は効いたまま）。2026-08-30 に `allow_auto_merge` / `delete_branch_on_merge` を有効化済み
- **auto-merge されたコミットは `gh-pages.yaml` を起動しない**。`GITHUB_TOKEN` が起こしたイベントは新しい workflow run を作らないという GitHub の仕様による（例外は `workflow_dispatch` と `repository_dispatch` のみ）。`--auto` で GitHub が後から代行するマージも、有効化したアクターが github-actions[bot] なので同じく抑止される。comic-walker-rss `89f82b8` と manga-one-rss `59fc518` の双方で実測確認済み
- `--auto` 経路（check が pending のうちに auto-merge を有効化し、green になった時点で GitHub が代行マージ）自体は正常に機能する。2026-08-30 に本リポジトリで実測確認済み。**起動しないのは github-actions[bot] 名義でマージされたときだけ**で、人間のトークンで auto-merge を有効化した場合はマージもその人間名義になるため `gh-pages.yaml` は通常どおり起動する
- 上記の遅延は**受容する方針**（2026-08-30 決定）。フィード内容は実行のたびにライブ取得するので鮮度には影響せず、12 時間ごとの schedule が最大 12 時間以内にデプロイを追いつかせる。依存 bump が `gh-pages.yaml` 固有の部分（`uv run main.py` の実フェッチ、`upload-pages-artifact` / `deploy-pages`）を壊した場合も、schedule 実行の失敗を `notify-failure` が Issue として起票する。即時デプロイが必要になったら PAT / GitHub App トークンへの切り替えか、github-actions グループを auto-merge 対象から外す運用に変える

**セットアップ手順の重複について**: uv ピンの読み取りロジックは `.github/scripts/resolve-uv-version.sh` に切り出して `ci.yaml` と `gh-pages.yaml` で共有する（仕様は `tests/test_resolve_uv_version.py` が固定。`grep -P` は GNU 限定で macOS では動かないため POSIX sed で実装してある）。一方 **`uses:` の行（checkout / setup-uv / setup-python）は両ファイルに重複させたまま**にすること。dependabot の github-actions エコシステムは `.github/workflows/` とリポジトリルートの `action.yml` しか走査しないため、composite action へ切り出すとバージョン追跡から外れる（dependabot-core#9788）。`--frozen` ではなく `--locked` を使うのは、lock と pyproject のずれを dependabot PR で検出するため

## 開発フロー

- **変更は原則 PR 経由**。`ci.yaml` の `check` が必須チェックなので、PR を出せば lint / フォーマット / 型検査 / テストが自動で回る。`enforce_admins: false` なのでオーナーは main へ直接 push もできる（ドキュメントや `feed.csv` の 1 行追加程度ならその運用でよい）
- **dependabot PR にローカル検証は不要**。以前は PR で CI が走らなかったため手元で CI 相当を再現していたが、現在は `check` が PR 上で走り、non-major はそのまま自動マージされる。人間が見るのは major を含むグループ PR だけ
- **`pyproject.toml` を編集したら必ず `uv lock` を実行して `uv.lock` も一緒にコミットする**。CI は `uv sync --locked` なので、ロックがずれているとインストール段階で落ちる
- `gh-pages.yaml` 自体を変更する PR は、その変更が実際に動くかを PR 上で検証できない（`ci.yaml` は別ファイル）。マージ後の push 実行を必ず確認する

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
- **`.py` の中の日本語コメント・docstring では全角括弧（）を使わない**。ruff の RUF002 / RUF003 が「紛らわしい Unicode」として弾く。半角 () を使うこと（本ファイルのような Markdown は lint 対象外なので全角のままでよい）
- `uv run pytest` は dev extras（`pytest-cov`）が入っていないと `addopts` の `--cov-fail-under` で失敗する。`uv sync --all-extras` 済みの環境で実行すること
- テストの fixture HTML は `end-of-file-fixer` hook の対象。pre-commit が末尾改行を足すことがあるが、パース結果には影響しない
