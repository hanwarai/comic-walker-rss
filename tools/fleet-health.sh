#!/usr/bin/env bash
# hanwarai の RSS ジェネレーター群 (本リポと同じ構成の姉妹リポ) の稼働状況を 1 画面で出す。
#
# 見るもの: 配信ワークフローの直近 conclusion / dependabot auto-merge の直近 conclusion /
#           open PR 数 / open issue 数。異常が 1 つでもあれば exit 1。
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

# PR と issue はリポごとに問い合わせると往復が増えるので、owner 横断の search で一度に引いて数える
open_prs=$(gh search prs --owner "$OWNER" --state open --limit 100 --json repository \
  --jq 'group_by(.repository.name) | map({(.[0].repository.name): length}) | add // {}')
open_issues=$(gh search issues --owner "$OWNER" --state open --limit 100 --json repository \
  --jq 'group_by(.repository.name) | map({(.[0].repository.name): length}) | add // {}')

problems=0
printf '%-22s %-20s %-20s %6s %6s\n' REPO DEPLOY AUTO-MERGE PR ISSUE

for r in "${REPOS[@]}"; do
  # 配信ワークフローのファイル名はリポによって揺れる (gh-pages.yaml 以外もありうる) ので名前で引く
  deploy_wf=$(gh api "repos/$OWNER/$r/actions/workflows" \
    --jq '.workflows[] | select(.path | test("pages|deploy")) | .path' | head -1)

  if [ -n "$deploy_wf" ]; then
    deploy=$(gh run list --repo "$OWNER/$r" --workflow "${deploy_wf##*/}" --limit 1 \
      --json conclusion,createdAt --jq '.[0] | "\(.conclusion) \(.createdAt[0:10])"')
  else
    deploy="(no workflow)"
  fi

  # skipped は dependabot 以外の PR で if 条件を外した run。判定が出た最後の run を見たい。
  # cancelled も除く: saitama-culture-rss は concurrency に cancel-in-progress を付けており、
  # Dependabot の rebase で古い run が畳まれるのは正常系なので、異常として数えてはいけない
  am=$(gh run list --repo "$OWNER/$r" --workflow dependabot-auto-merge.yaml --limit 20 \
    --json conclusion,createdAt \
    --jq '[.[] | select(.conclusion != "skipped" and .conclusion != "cancelled")][0] // {} | "\(.conclusion // "(none)") \(.createdAt[0:10] // "-")"')

  pr=$(printf '%s' "$open_prs" | jq -r --arg r "$r" '.[$r] // 0')
  issue=$(printf '%s' "$open_issues" | jq -r --arg r "$r" '.[$r] // 0')

  printf '%-22s %-20s %-20s %6s %6s\n' "$r" "$deploy" "$am" "$pr" "$issue"

  case "$deploy $am" in
    *failure* | *cancelled* | *timed_out* | *"(none)"* | *"(no workflow)"*) problems=$((problems + 1)) ;;
  esac
  [ "$pr" -eq 0 ] && [ "$issue" -eq 0 ] || problems=$((problems + 1))
done

echo
if [ "$problems" -eq 0 ]; then
  echo "OK: ${#REPOS[@]} リポすべて正常 (配信 success / auto-merge success / 滞留なし)"
else
  echo "要確認: $problems 件" >&2
  exit 1
fi
