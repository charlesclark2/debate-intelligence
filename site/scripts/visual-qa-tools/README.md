# visual-qa-tools

The headless browser and the scoring tool that `site/scripts/visual-qa.mjs` drives.

They are a package of their own, not devDependencies of `site/`, for one reason: `pnpm --dir site
lint|test|build` has to install and run offline in seconds to stay inside the CI budget in
[`docs/process/working-agreements.md`](../../../docs/process/working-agreements.md), and a browser
binary is several hundred megabytes fetched over the network. Nothing in here is imported by the
site, reaches the bundle, or runs in CI.

**Operator setup, once per clone:**

```bash
pnpm --dir site/scripts/visual-qa-tools install
pnpm --dir site/scripts/visual-qa-tools exec playwright install chromium
```

Then, from the repository root:

```bash
pnpm --dir site build
pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
```

`node_modules/` and the lockfile here are gitignored. The lockfile is ignored rather than
committed because a prod deploy refuses a checkout that is not clean
([`docs/runbooks/team-website.md`](../../../docs/runbooks/team-website.md)), and an operator
installing a review tool should not have to commit anything to deploy afterwards. The versions
that produced a given set of scores are recorded in the report the run writes, which is what makes
the numbers reproducible.
