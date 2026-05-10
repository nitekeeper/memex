# Lesson Format

Lessons are markdown files with YAML frontmatter. They live in `lessons/inbox/` (AI-captured suggestions) or `lessons/feedback/` (user-direct feedback).

## Frontmatter

```yaml
---
id: <project>:lesson:<slug>
title: <title>
stream: inbox | feedback
status: draft | promoted | discarded
tags: [...]
created: YYYY-MM-DD
---
```

_Note: `tags` is optional._

## Body

```markdown
## Observation

What happened or was noticed. For feedback stream: the user's stated direction verbatim or close to it.

## Why it matters

The non-obvious implication. What would go wrong without this lesson.

## How to apply

Concrete guidance for next time.
```

## Filename

`lessons/<stream>/<slug>.md` — slug is kebab-case, derived from title.

The optional `slug` frontmatter field overrides the filename stem when it would differ from the title-derived default. Use the bare slug only (e.g. `my-lesson`, not `memex:lesson:my-lesson`).

## Lifecycle

| Status | Meaning |
|---|---|
| `draft` | Awaiting review. All new lessons start here. |
| `promoted` | Substance promoted into a wiki entry, methodology, or skill update. File moved to `lessons/promoted/`. |
| `discarded` | Reviewed and rejected. Default action: delete. Set `discard-reason` if reason needs logging. |

## Streams

| Stream | Path | When used |
|---|---|---|
| `inbox` | `lessons/inbox/<slug>.md` | AI-captured suggestions — require review before acting on |
| `feedback` | `lessons/feedback/<slug>.md` | User-direct feedback — treated as direction, higher priority than inbox |
