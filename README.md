# comic-walker-rss

[![ci](https://github.com/hanwarai/comic-walker-rss/actions/workflows/ci.yaml/badge.svg)](https://github.com/hanwarai/comic-walker-rss/actions/workflows/ci.yaml)
[![github pages publish](https://github.com/hanwarai/comic-walker-rss/actions/workflows/gh-pages.yaml/badge.svg)](https://github.com/hanwarai/comic-walker-rss/actions/workflows/gh-pages.yaml)

[ComicWalker](https://comic-walker.com) の**無料公開中**エピソードだけを Atom フィードとして配信するジェネレーター。GitHub Actions が 12 時間ごとに実行し、GitHub Pages へ公開する。

- 一覧: https://hanwarai.github.io/comic-walker-rss/
- 各フィード: `https://hanwarai.github.io/comic-walker-rss/{作品コード}.xml`

## 仕組み

```
feed.csv → main.py → feeds/*.xml + feeds/index.html → GitHub Pages
```

1. `feed.csv` の作品コード (`KC_XXXXXX_S`) を読む
2. `https://comic-walker.com/detail/{作品コード}/` を取得し `<script id="__NEXT_DATA__">` の JSON をパースする
3. `isActive == true` のエピソード (無料公開期間内) だけを新しい順に Atom フィードへ入れる
4. Jinja2 テンプレートで一覧ページ `feeds/index.html` を生成する

## フィードに載るもの・消えるもの

収録対象は**その時点で無料で読めるエピソードだけ**。ComicWalker の無料公開は期間制のため、公開期間が終わったエピソードは次回の生成でフィードから外れる。逆に新しく無料化されたエピソードは自動的に入る。つまりフィードは「いま読める話の一覧」であって、既読管理用の恒久的なアーカイブではない。

## 作品の追加

対象ページ `https://comic-walker.com/detail/KC_XXXXXX_S/...` の `KC_XXXXXX_S` 部分を `feed.csv` に 1 行追記して push するだけ。次のデプロイからフィードが生える。不正な形式の行と重複は生成時に警告付きで読み飛ばされる。

## 構成

| パス | 役割 |
|---|---|
| `main.py` | 取得・パース・フィード生成の全ロジック |
| `feed.csv` | 追跡対象の作品コード一覧 (1 列) |
| `templates/index.html` | 一覧ページの Jinja2 テンプレート (Bootstrap 5) |
| `tests/` | pytest。HTTP は `requests-mock`、実ページのスナップショットは `tests/fixtures/` |
| `feeds/` | 生成物の出力先 (git 管理外) |

## 開発

```bash
uv sync --all-extras          # 依存インストール (テストには dev extras が必須)
uv run main.py                # フィード生成 (feeds/ 配下に出力)
uv run pytest                 # テスト (カバレッジ 80% 未満で失敗)
uv run ruff check .           # lint
uv run ruff format .          # フォーマット
uv run mypy                   # 型検査
uv run pre-commit install     # コミット時に上記を自動実行
```

PR を出すと `ci.yaml` が lint / フォーマット / 型検査 / テストを実行する。main はこのチェックの通過を必須とする branch protection 下にある。依存関係の更新は Dependabot が週次で PR を作り、non-major はチェック通過後に自動マージされる。

Python 3.13 / パッケージマネージャーは [uv](https://docs.astral.sh/uv/)。
