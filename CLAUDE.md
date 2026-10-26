# CLAUDE.md

This vault is the single source of truth for Sunil's tasks, priorities and notes. Every Claude session working here follows these rules. If something is not in the vault, it is not tracked.

## Files

| Path | Purpose |
|---|---|
| inbox.md | Raw capture. Anything goes here first. Emptied by "process inbox". |
| today.md | Regenerated every morning by the morning brief. Never edited by hand except ticking boxes. |
| waiting.md | Things pending on other people. One line each with date asked and who. |
| someday.md | Parked ideas. No action this month. |
| projects/ | One file per ongoing project or client thread, named `<project-slug>.md`, built from templates/project.md. |
| daily/ | One file per day, `YYYY-MM-DD.md`, auto created from templates/daily.md. |
| reviews/ | Weekly review output, `YYYY-Www.md` (ISO week, e.g. 2026-W44.md). |
| templates/ | project.md and daily.md templates. Copy, never edit in place for a specific use. |
| CLAUDE.md | This file. |

## Task line format (use everywhere)

```
- [ ] Task text  @due:2026-10-30  @p:1  @proj:project-slug  @who:Name
```

- `@p` is 1 (must do), 2 (should do), 3 (nice).
- `@who` only when the action is on someone else.
- `@due` and `@proj` are optional when not known, but add `@proj` whenever the task belongs to a project file.
- Lines in waiting.md also carry `@asked:YYYY-MM-DD` (date the ask was made) and always carry `@who`.
- Completed tasks become `- [x]` with `  @done:YYYY-MM-DD` appended.
- Never delete completed tasks. Move them to the bottom of the file under a `## Done` heading.

## Hard rules

- Never create a second copy of a task. Search the whole vault (grep the task text and key words) before adding anything.
- Every project file must always have exactly one Next action. If a project has no open tasks left, ask Sunil whether to mark it `status: done` or add a new Next action.
- Update the `updated:` frontmatter field of a project file whenever you change it.
- Dates are absolute, YYYY-MM-DD. Convert "tomorrow", "Friday" etc. using today's date.

## Commands

### "process inbox"
1. Read inbox.md.
2. For each line decide where it belongs: an existing project file, waiting.md, someday.md, or a new project file (created from templates/project.md).
3. Search first so nothing is duplicated, then write it there in the task line format. Inbox text is often pasted from OneNote, sticky notes or task apps, so expect messy text and repeats. When two lines, or a line and an existing task, describe the same work, merge them into one task with the earliest due date, the higher priority and any extra detail added. Never keep both. List every merge in the report so Sunil can check it.
4. Empty inbox.md, leaving only the comment line `<!-- paste raw items here -->`.
5. Report in one short line per item where it went.

### "done with X"
1. Find the task matching X (search all files). If more than one match, ask which.
2. Mark it `[x]` and append `@done:YYYY-MM-DD`.
3. Move it under `## Done` at the bottom of that file.
4. If it was a project's Next action, promote the next open task (highest priority, then earliest due) to Next action.

### "add task ..."
Write it to the right project file in the task line format. If the project is unclear, write it to inbox.md. Search before adding.

### Linked Google Docs
A project file can have a `doc:` field in its frontmatter holding a Google Doc URL. When Sunil says "update <requirement> to <project>" (e.g. "update this feature requirement to yaake development"):
1. Find the project file. Read its `doc:` link. If there is none, search Google Drive by project name, confirm the doc with Sunil, then save the link in `doc:`.
2. Read the doc and add the change in the right section. Keep its existing structure. Edit, don't replace.
3. Add a dated note to the project file's Notes: `YYYY-MM-DD: updated doc, <one line summary>`.

## Morning brief

Build today.md from templates/daily.md (also save the same content to `daily/YYYY-MM-DD.md` if it does not exist). Inputs:

1. Gmail threads, using the search string and triage rules below.
2. Today's calendar, into `## Calendar`.
3. Every project's Next action.
4. waiting.md. Items with `@asked` older than 48h go under `## Waiting past 48h`.
5. Any lines in inbox.md go under `## Inbox to process`.

Prioritisation:
- Cap Must do at 3. If more qualify, say so and list the overflow under Should do.
- Priority is inferred from due date, who is waiting, and client or revenue impact.
- Put a short reason after each item in brackets, e.g. `[client waiting since Thu, renewal at risk]`.

### Gmail exclusion string

Default lookback is 30 days: start every search with `newer_than:30d`. If Sunil asks for a longer or shorter scan ("morning brief 90 days", "scan emails since 1 Aug"), use `newer_than:90d` or `after:YYYY/MM/DD` instead. For mails sent to shared addresses he receives (e.g. partnerships@5cnetwork.com), add a separate search with `to:<address>`.

Multiple mailboxes: run `python -I tools/mail.py brief --days 30` (change --days for a longer or shorter scan). It covers every mailbox with a token in .secrets/ (currently sunil.kumar@, support@, communication@, insights@; see `python -I tools/mail.py accounts`), applies the exclusion string to Sunil's inbox, pre filters with the rules below, and prints one tab separated row per thread with account, thread ID, reason, age in hours and subject. Treat its output as candidates and still apply the triage rules. For ad hoc searches use `python -I tools/mail.py search "<query>"`. Use the Gmail connector only as a fallback for Sunil's own inbox.

Shared mailboxes (anything other than sunil.kumar@): ignore general mail. Surface only threads where the last message is from outside 5C (not @5cnetwork.com, @5cnetwork.in or @ask5c.in), nobody from 5C has replied since, and it is not bulk, an auto reply or a transactional alert. support@ is handled by finance_reply_bot: show its payment threads only when the bot has not replied in 48h, and group them as one line with a count plus the oldest few. Non payment threads on support@ (security reports, complaints, report errors, login issues, bank detail changes) are listed individually. Job applications and vendor pitches go to a single "low priority" line with a count. Label every flagged email with its mailbox and thread ID, because thread IDs only work within their own mailbox. For support@5cnetwork.com apply the support triage rule below. A new mailbox is added with `python tools/mail.py add <email>`, which opens a browser login that Sunil must complete himself. Never print or commit anything from .secrets/.

Append this verbatim to every Gmail search:

```
-from:analytics@5cnetwork.com -from:insights@5cnetwork.com -from:support@5cnetwork.com -from:partnerships@5cnetwork.com -from:insights@ask5c.in -from:proradinsights@5cnetwork.com -subject:"Invitation:*" -from:do-not-reply@cloud.sophos.com -subject:" Assessment link and submission Instruction" -from:noreply@airindia.com -from:mailer-daemon@googlemail.com -from:policy.noreply@service.uiic.co.in
```

### Email triage rules

- Surface only threads where Sunil hasn't replied, needs to follow up, or an action is pending on him.
- Ignore FYA and general updates.
- Skip support@5cnetwork.com and ai.teleradiology@5cnetwork.com mails not addressed to him, unless unanswered for 48h.
- Flag his own outgoing asks only if there has been no reply for 48h.
- Skip threads that are closed, being worked by the team, or pending on someone else.
- Always include the Gmail thread ID next to each flagged email, e.g. `(thread 18f2a...)`.
- Also surface older outbound BD mails with zero reply so they don't go dark (search `in:sent` with no reply in the thread).

## Weekly review

Write output to `reviews/YYYY-Www.md`. List:
- projects with no change in 14 days (by `updated:` and git history),
- waiting items older than 7 days,
- tasks with past due dates.

For each item ask Sunil: kill, defer or reactivate. Apply the answers, then commit.

## Writing style

Short direct sentences. No em dashes. No bullets in prose. No bold. No headers beyond the templates. Indian English is fine.
