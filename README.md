# comic-walker-rss

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

## 作品の追加

対象ページ `https://comic-walker.com/detail/KC_XXXXXX_S/...` の `KC_XXXXXX_S` 部分を `feed.csv` に 1 行追記して push するだけ。次のデプロイからフィードが生える。

## 開発

```bash
uv sync --all-extras          # 依存インストール
uv run main.py                # フィード生成 (feeds/ 配下に出力)
uv run pytest                 # テスト (カバレッジ 80% 未満で失敗)
uv run ruff check .           # lint
uv run ruff format .          # フォーマット
uv run mypy                   # 型検査
uv run pre-commit install     # コミット時に上記を自動実行
```

Python 3.13 / パッケージマネージャーは [uv](https://docs.astral.sh/uv/)。
