# Terento repository instructions

These are the repository-wide instructions for Codex and contributors. Keep
changes narrow, evidence-based, and consistent with the canonical product,
scope, architecture, security, and release documents under `internal/` and
with the public component READMEs. When descriptive facts change, update the
relevant canonical document in the same change. Private operator documentation
under ignored `internal/` may not be available to external contributors, so
scoped instructions must still state their durable working rules.

## Mandatory reading for user-facing work

Before changing user-facing UI, public copy, CSS, admin UI, icons,
illustrations, screenshots, marketing documentation, or visual assets, read:

- `brand/BRAND_GUIDELINES.md`
- `brand/DESIGN_TOKENS.json`
- the nearest scoped `AGENTS.md`

Also inspect the current implementation before editing. Preserve current
layout and runtime behavior unless the task explicitly requests a change.

## Brand source precedence

Use this order when sources disagree:

1. `brand/logo/logo.svg` — canonical, immutable logo geometry.
2. `brand/DESIGN_TOKENS.json` — canonical numeric token values.
3. `brand/BRAND_GUIDELINES.md` — canonical usage, accessibility, voice, and
   product-truth rules.
4. Generated or platform-specific implementation files — implementations of
   the canonical sources; they must not redefine the brand.
5. Screenshots, mockups, boards, PDFs, and presentations — editorial
   references only, never implementation sources.

## Locked brand and product rules

- Never modify the canonical logo geometry or reinterpret its paths.
- Do not introduce new brand colors, fonts, or visual directions inside a
  feature task. Use approved semantic tokens instead of inventing raw colors.
- `Interactive Primary` is the only primary action family. `Warm Stone` is
  never a primary CTA.
- Instrument Sans is for brand, marketing, hero, and expressive headings;
  Inter is for UI, body text, labels, buttons, and information; JetBrains
  Mono is for diagnostics and technical identifiers only.
- Normal product UI describes outcomes, not MTP, IMG, USB object handles, or
  filesystem mechanics.
- Every status has explicit text and an icon; color is supporting information,
  never the only status signal.
- Public claims must match functionality available in the current release.
  Beta limitations must remain truthful.
- Internal compatibility classifications must not be turned into a broad public
  support claim. Public Compatibility presentation is owned by `site/AGENTS.md`
  and the generated site contract; backend/admin evidence and status rules stay
  in their scoped contracts.
- Do not reduce accessibility or keyboard focus behavior.
- Do not alter unrelated working behavior during visual or documentation
  work.

## Source locations

The production native core and its regression harness live in `app/TerentoCore/`.
The application shell is `app/Terento/`; keep `Terento.xcodeproj/` at the root.
Shared public payload schemas and fixtures live in `contracts/`; read fixtures
there directly from each language's tests. Do not add runtime schema validation
or change application/API behavior as a side effect of contract documentation.

## Change discipline

- Prefer small, focused diffs and avoid opportunistic cleanup.
- Update tests when user-facing behavior changes.
- Preserve repository safety, privacy, licensing, device-ownership, and
  provider boundaries documented by the applicable canonical documents.
- Report intentional exceptions and unresolved limitations explicitly.
- Keep local machine or operator-specific instructions in the ignored
  `AGENTS.override.md`; never copy private infrastructure, credentials,
  secrets, or personal working instructions into tracked files.

### Same-change documentation and ownership

Any change to durable product behavior, user/admin workflow, public semantics,
API behavior, configuration, safety boundary, statistics interpretation,
release behavior, or supported operational workflow must update the owning
canonical documentation in the same change. Remove or rewrite superseded
guidance instead of appending conflicting prose. Do not create documentation
for transient implementation details that are self-evident from code and are
not durable contracts or user/operator behavior.

## Admin and diagnostic workflow contract

For Admin, diagnostic, statistics, or app/API payload work, read the scoped
`backend/catalog-api/AGENTS.md` plus the canonical Admin, API, statistics, and
app/API release contracts named there. Keep diagnostic evidence, counting,
identity-review, privacy, and device-safety invariants intact; a green deploy or
one visible row is not proof that the full workflow works. Do not duplicate
scoped Admin implementation rules here.

## Git and workspace hygiene

- When the repository and workflows confirm it, `origin/beta` is the canonical
  integrated Terento source state. Do not treat a local task branch as canonical
  merely because its SHA is different.
- Before substantial work, run `scripts/check-workspace-state.sh` and inspect
  the current branch, upstream, `origin/beta`, working tree, worktrees, stashes,
  and local branches. Fetch/prune remote refs when the task requires fresh
  remote state; the checker itself is read-only.
- Create a new task branch or worktree only for independently reviewable work.
  Reuse the existing task branch for a continuation. Do not create `v2`, `v3`,
  `final`, `deploy`, or replacement branches for the same work; commit history
  records iterations.
- Do not create deployment-only branches when deployment workflows use the
  integration branch.
- If an unexpected dirty worktree is found, audit staged, unstaged, untracked,
  and ignored state before any checkout, stash, reset, restore, clean, branch
  deletion, or worktree removal. Never auto-stash or discard it.
- A task branch is temporary. After its work is integrated into `origin/beta`,
  remote state is verified, and semantic review finds no unique local content,
  remove its linked clean worktree, delete the local branch, and prune stale
  worktree metadata/remote refs as appropriate. Use `git branch -D` only when
  explicit semantic-equivalence evidence explains why ancestry is insufficient;
  prefer `git branch -d` whenever it can prove the same result.
- Stashes are temporary recovery mechanisms, not a backlog. Audit their content
  before dropping them; preserve any unique, uncertain, or recovery material.
- At task handoff report current branch, HEAD, upstream and ahead/behind,
  working-tree state, remaining relevant branches, worktrees, stashes, tests,
  and cleanup status.
