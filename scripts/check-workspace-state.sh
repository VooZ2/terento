#!/bin/sh

# Read-only Git/workspace inventory for task handoff and branch hygiene.
# This script deliberately does not fetch, checkout, stash, reset, restore,
# clean, delete, or modify any repository state.

set -eu

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

current_branch=$(git branch --show-current)
head_sha=$(git rev-parse HEAD)
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)

printf '%s\n' '== Repository =='
printf 'root: %s\n' "$repo_root"
printf 'branch: %s\n' "${current_branch:-DETACHED}"
printf 'HEAD: %s\n' "$head_sha"
printf 'canonical ref: %s\n' "$(git rev-parse --verify origin/beta 2>/dev/null || printf '%s' 'MISSING')"

if [ -n "$upstream" ]; then
  printf 'upstream: %s\n' "$upstream"
  printf 'ahead/behind upstream (ahead behind): %s\n' "$(git rev-list --left-right --count HEAD..."$upstream")"
else
  printf '%s\n' 'upstream: NONE'
fi

if git rev-parse --verify origin/beta >/dev/null 2>&1; then
  printf 'ahead/behind origin/beta (ahead behind): %s\n' "$(git rev-list --left-right --count HEAD...origin/beta)"
fi

printf '\n%s\n' '== Working tree =='
status=$(git status --short)
if [ -n "$status" ]; then
  printf '%s\n' "$status"
else
  printf '%s\n' 'clean'
fi
untracked_count=$(printf '%s\n' "$status" | awk 'index($0, "?? ") == 1 {count++} END {print count + 0}')
printf 'untracked count: %s\n' "$untracked_count"
if [ "$untracked_count" -gt 0 ]; then
  printf '%s\n' 'untracked paths:'
  printf '%s\n' "$status" | awk 'index($0, "?? ") == 1 {sub(/^\?\? /, ""); print}'
fi

printf '\n%s\n' '== Stashes =='
stash_count=$(git stash list | wc -l | tr -d ' ')
printf 'count: %s\n' "$stash_count"
if [ "$stash_count" -gt 0 ]; then
  git stash list --date=iso-strict
fi

printf '\n%s\n' '== Worktrees =='
git worktree list --porcelain

printf '\n%s\n' '== Local branches =='
git for-each-ref --format='%(refname:short) %(objectname:short) upstream=%(upstream:short) %(subject)' refs/heads

if git rev-parse --verify origin/beta >/dev/null 2>&1; then
  printf '\n%s\n' '== Local branches ancestrally merged into origin/beta =='
  git for-each-ref --format='%(refname:short)' refs/heads | while IFS= read -r branch; do
    if git merge-base --is-ancestor "$branch" origin/beta; then
      printf '%s\n' "$branch"
    fi
  done

  printf '\n%s\n' '== Local branches not ancestrally merged into origin/beta =='
  git for-each-ref --format='%(refname:short)' refs/heads | while IFS= read -r branch; do
    if ! git merge-base --is-ancestor "$branch" origin/beta; then
      printf '%s\n' "$branch"
    fi
  done
fi
