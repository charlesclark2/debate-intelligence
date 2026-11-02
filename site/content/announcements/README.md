# Announcements

One file here is one announcement on the website. The build turns each into a summary on the home
page (pinned ones first, then the three newest), a line on the news page, `/news/`, and a page of
its own. How to add, change, pin, expire and remove one, and what may never be written:
`docs/guides/coach-website-editing.md`, section "Announcements".

This file is the only one here that is not an announcement. Every other file must be a Markdown
file whose name ends in `.md`, and its name is its web address: name it for the day and what it
announces, in lower case with hyphens, such as `2026-11-03-novice-orientation.md`. Never put a
student's name in a file name.

```markdown
---
title: Novice orientation on Tuesday
date: 2026-11-03
expires: 2026-11-10
pinned: true
---

New debaters and their families: come to the library after school on Tuesday. We'll walk through
the season and answer your questions.
```

| Field | Needed | What it does |
|---|---|---|
| `title` | yes | The headline |
| `date` | yes | The day it first appears, written 2026-11-03. A later date keeps it off the site until a deploy on or after that day |
| `expires` | no | The last day it appears. It comes off at the first deploy after that day, not on the day itself |
| `pinned` | no | `true` keeps it at the top of the home page, above newer ones |
| `image` | no | A picture from the site's own `public/` folder, such as `/photos/novice-orientation.jpg`, and only with its entry in `content/media-consent.yaml` |
| `alt` | with `image` | What the picture shows, for someone who cannot see it. It names nobody unless their consent allows it |

The body is Markdown: paragraphs, **bold**, *italic*, lists and [links](/schedule/). No HTML: the
build refuses it, along with any email address, phone number or name it has not been told about.
