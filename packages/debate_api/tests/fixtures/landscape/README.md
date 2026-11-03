<!-- docs-index: Synthetic landscape bundles for the search pilot's landscape page tests -->
# Synthetic landscape bundles

Hand-written `report.md` and `schools.md` files in the shape `v1-e32-t20` and `v1-e32-t18` write,
for `v1-e39-t17`'s tests of the pilot's landscape pages. Every caselist, school, team code and
position here is invented (no real debate file is in the repository). The tests' expectations of
how they render are written by hand from these files (working agreement 6).

* `synthpolicy26/2026-10-20/`: the newest bundle. Two schools whose headings share an anchor
  (`Birch Hollow` and `Birch-Hollow`), a display name with no team page, two team pages, in both
  the by-school and the by-position tables (`v1-e32-t23`), and a `### Counterplan texts` under
  `## Counterplan texts`, so a page repeats an anchor.
* `synthpolicy26/2026-10-13/`: an older bundle, whose school `Oldfield` must never be shown. Its
  by-school table keeps the shape before `v1-e32-t23`, with no team page column.
* `synthld26/2026-10-19/`: a report with no school view.
