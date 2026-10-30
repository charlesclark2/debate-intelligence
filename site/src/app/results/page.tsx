import type { Metadata } from 'next'

import { Prose } from '@/components/Prose'
import { ResultLine } from '@/components/ResultLine'
import { Section } from '@/components/Section'
import { RESULTS_SLUG, loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'
import { loadResultsView } from '@/lib/results'
import type { ResultGroup } from '@/lib/results'
import { formatDate, formatDateRange } from '@/lib/tournaments'

/** The band holding the results. No tournament key can match it: every key ends in a year. */
const SEASON_RESULTS_ID = 'season-results'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(RESULTS_SLUG))
}

/**
 * One tournament and every placing won at it, in the order content/results.yaml lists them.
 * Grouped by tournament and never by student: a list of one student's placings across the
 * season would be the record the policy rules out (Results and awards 3).
 */
function TournamentResults({ group }: { group: ResultGroup }) {
  const { tournament } = group
  return (
    <li className="results-group" id={tournament.key}>
      <article aria-labelledby={`${tournament.key}-name`}>
        <h3 className="results-group__name" id={`${tournament.key}-name`}>
          {tournament.name}
        </h3>
        <p className="results-group__dates">{formatDateRange(tournament)}</p>
        <ul className="results-group__list">
          {group.results.map((result) => (
            <li className="results-group__result" key={result.position}>
              <ResultLine result={result} />
            </li>
          ))}
        </ul>
      </article>
    </li>
  )
}

/**
 * The season's results (v1-e37-t06).
 *
 * Newest tournament first, each one with its date and its placings. A tournament comes off the
 * schedule once it is over, so a result names its tournament either by schedule id or by its
 * own name and date, and the page shows both the same way.
 *
 * Not one string below is written here. The title and the opening come from
 * content/pages/results.md, and the labels and the results from content/results.yaml, validated
 * at build time; tests/results.test.tsx fails if a word of that copy appears in this file.
 */
export default function ResultsPage() {
  const page = loadPage(RESULTS_SLUG)
  const view = loadResultsView()
  const { labels } = view

  return (
    <>
      <Section headingLevel={1} title={page.title}>
        <Prose html={page.html} />
        <p className="results-revised">
          {labels.revised}: {formatDate(view.revised)}
        </p>
      </Section>

      <Section
        contentWidth="wide"
        headerAlign="wide"
        id={SEASON_RESULTS_ID}
        title={view.seasonTitle}
        tone="tinted"
      >
        {view.groups.length === 0 ? (
          <p className="results-empty">{labels.empty}</p>
        ) : (
          <ol className="results-list">
            {view.groups.map((group) => (
              <TournamentResults group={group} key={group.tournament.key} />
            ))}
          </ol>
        )}
      </Section>
    </>
  )
}
