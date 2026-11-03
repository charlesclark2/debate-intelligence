Synthetic HTTP fixtures for `HttpArticleFetcher`'s tests (`v1-e04-t02-http-fetcher`). Every file
here was written by hand for the tests; none was downloaded from a real site. The tests serve them
through respx, so nothing reaches the network.

| File | What it stands for |
|---|---|
| `article.html` | an ordinary news article page |
| `paper.pdf` | the first bytes of an open-access PDF, served without a useful content type |
| `robots_disallow_private.txt` | a site that keeps every crawler out of `/private/` |
| `robots_named_group.txt` | a site with its own group for `debate-research` |
| `robots_longest_match.txt` | rules that `urllib.robotparser` and RFC 9309 read differently |
