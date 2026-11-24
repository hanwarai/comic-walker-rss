#!/usr/bin/env bash
# hanwarai の RSS ジェネレーター群 (本リポと同じ構成の姉妹リポ) の稼働状況を 1 画面で出す。
#
# 見るもの: 配信ワークフローの直近 conclusion / dependabot auto-merge の直近 conclusion /
#           配信物に購読できる中身があるか / open PR 数 / open issue 数。異常が 1 つでもあれば exit 1。
#
# 対象リポを決め打ちせず gh repo list から引くのは、リポが増減しても台本が腐らないようにするため。
# archived を除くのは urasunday-rss が意図的にアーカイブ済みで fleet 外だから。
set -euo pipefail

OWNER=${OWNER:-hanwarai}

# mapfile は bash 4 以降で、macOS 標準の bash は 3.2 なので while read で詰める
# (.github/scripts/resolve-uv-version.sh を POSIX sed で書いているのと同じ理由)
REPOS=()
while IFS= read -r name; do
  REPOS+=("$name")
done < <(
  gh repo list "$OWNER" --limit 200 --json name,isArchived \
    --jq '.[] | select(.isArchived == false) | select(.name | endswith("-rss")) | .name' | sort
)

if [ ${#REPOS[@]} -eq 0 ]; then
  echo "対象リポが 0 件。gh auth status を確認すること" >&2
  exit 1
fi

count() { # grep がヒット 0 で exit 1 を返すのを set -e に拾わせない
  { grep -o "$1" "$2" || true; } | wc -l | tr -d ' '
}

# 配信されている成果物を直接見る。run の conclusion は success でも中身が空になりうる
# (2026-10-23 に bigcomics-rss の上流が Actions の IP を 403 で弾き始めたが、main.py が
#  警告だけ出して exit 0 したため、空の index が 1 か月配信され、この台本は緑を出し続けた)
probe_feed() {
  local r="$1" body n p
  body=$(mktemp)
  get() { curl -sfS --retry 3 --retry-delay 2 --retry-all-errors --max-time 40 -o "$body" "$1" 2>/dev/null; }

  # 単一フィード型を先に見る。free-only-rss の index.html は rss.xml への静的リンクを
  # 1 本持つだけなので、index から数えると中身が空でも link=1 で緑に見える
  for p in feed.xml rss.xml; do
    if get "https://$OWNER.github.io/$r/$p"; then
      n=$(count '<entry' "$body")
      rm -f "$body"
      [ "$n" -gt 0 ] && printf 'entry=%s' "$n" || printf '空'
      return
    fi
  done
  # 本リポは公開中のフィードを seed するので、全件取得失敗でも link 数は落ちない。
  # ここは他 10 リポ用の網で、本リポの取得断は run のログ側で見ること
  if get "https://$OWNER.github.io/$r/index.html"; then
    n=$(count '\.xml' "$body")
    rm -f "$body"
    [ "$n" -gt 0 ] && printf 'link=%s' "$n" || printf '空'
    return
  fi
  rm -f "$body"
  printf '空'
}

problems=0
printf '%-22s %-20s %-20s %-10s %6s %6s\n' REPO DEPLOY AUTO-MERGE FEED PR ISSUE

for r in "${REPOS[@]}"; do
  # 配信ワークフローのファイル名はリポによって揺れる (gh-pages.yaml 以外もありうる) ので名前で引く
  deploy_wf=$(gh api "repos/$OWNER/$r/actions/workflows" \
    --jq '.workflows[] | select(.path | test("pages|deploy")) | .path' | head -1)

  if [ -n "$deploy_wf" ]; then
    # 実行中の run は conclusion が空で返る。そのまま出すと success と見分けが付かず
    # 「異常なし」に混ざるので、明示的に running と出して判定からも外す
    deploy=$(gh run list --repo "$OWNER/$r" --workflow "${deploy_wf##*/}" --limit 1 \
      --json conclusion,createdAt,status \
      --jq '.[0] | "\(if .conclusion == "" or .conclusion == null then "running(\(.status))" else .conclusion end) \(.createdAt[0:10])"')
  else
    deploy="(no workflow)"
  fi

  # skipped は dependabot 以外の PR で if 条件を外した run。判定が出た最後の run を見たい。
  # cancelled も除く: saitama-culture-rss は concurrency に cancel-in-progress を付けており、
  # Dependabot の rebase で古い run が畳まれるのは正常系なので、異常として数えてはいけない
  am=$(gh run list --repo "$OWNER/$r" --workflow dependabot-auto-merge.yaml --limit 20 \
    --json conclusion,createdAt \
    --jq '[.[] | select(.conclusion != "skipped" and .conclusion != "cancelled")][0] // {} | "\(.conclusion // "(none)") \(.createdAt[0:10] // "-")"')

  feed=$(probe_feed "$r")

  # owner 横断の gh search は 100 件で打ち切られる。fleet 外のリポに滞留が溜まると
  # fleet の PR が押し出されて 0 件に見えるので、リポごとに数える
  pr=$(gh pr list --repo "$OWNER/$r" --state open --json number --jq 'length')
  issue=$(gh issue list --repo "$OWNER/$r" --state open --json number --jq 'length')

  printf '%-22s %-20s %-20s %-10s %6s %6s\n' "$r" "$deploy" "$am" "$feed" "$pr" "$issue"

  case "$deploy $am" in
    *failure* | *cancelled* | *timed_out* | *"(none)"* | *"(no workflow)"*) problems=$((problems + 1)) ;;
  esac
  [ "$feed" != "空" ] || problems=$((problems + 1))
  [ "$pr" -eq 0 ] && [ "$issue" -eq 0 ] || problems=$((problems + 1))
done

echo
if [ "$problems" -eq 0 ]; then
  echo "OK: ${#REPOS[@]} リポすべて正常 (配信 success / auto-merge success / フィード非空 / 滞留なし)"
else
  echo "要確認: $problems 件" >&2
  exit 1
fi
