import type { Metadata } from 'next'
import Link from 'next/link'

import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { CardGrid } from '@/components/CardGrid'
import { EmailUpdates } from '@/components/EmailUpdates'
import { Prose } from '@/components/Prose'
import { ResultLine } from '@/components/ResultLine'
import { Section } from '@/components/Section'
import { SourceLine } from '@/components/SourceLine'
import { HOME_SLUG, loadEmailUpdatesContent, loadHomeContent, loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'
import { loadResults, newestResults } from '@/lib/results'
import { formatDateRange } from '@/lib/tournaments'

/** Names the season-schedule panel for a screen reader moving by region. */
const SEASON_SCHEDULE_ID = 'season-schedule'

/** Names the newest-results band, and is where its link from elsewhere would point. */
const RECENT_RESULTS_ID = 'recent-results'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(HOME_SLUG))
}

/**
 * The home page.
 *
 * Eight bands, in the order a parent needs them: the hero, the pointer to the season's
 * tournament schedule, the signup for parent email updates (v1-e37-t05), the season's three
 * newest results (v1-e37-t06, left out until the season has one), four entry points into the
 * site, what debate actually is, what a season of it builds, and what the research says about it
 * academically. The schedule panel is the only band on navy, which is what makes it the most
 * prominent thing on the page after the hero without giving it a bigger heading than its
 * neighbours. It names no date of its own (v1-e37-t02): the site is deployed by hand, so a dated
 * announcement here goes stale the day after it happens, as the October 1 panel it replaced did.
 *
 * Not one string below is written here. The title and the prose come from content/pages/home.md
 * and everything else from content/home.yaml (the email-updates band from
 * content/email-updates.json, the results from content/results.yaml), all validated
 * at build time; tests/home.test.tsx fails if a word of that copy appears in this file.
 */
export default function HomePage() {
  const page = loadPage(HOME_SLUG)
  const { hero, seasonSchedule, recentResults, entryPoints, prose, whatDebateBuilds, academicCase } =
    loadHomeContent()
  const emailUpdates = loadEmailUpdatesContent()
  const newest = newestResults(loadResults())

  return (
    <>
      <section className="section hero">
        <div className="section__inner">
          <div className="hero__content">
            <hr className="hero__rule" />
            <h1 className="hero__title">{page.title}</h1>
            <p className="hero__lead">{hero.lead}</p>
            <Button href={hero.action.href} size="large">
              {hero.action.label}
            </Button>
          </div>
        </div>
      </section>

      <Section
        eyebrow={seasonSchedule.eyebrow}
        id={SEASON_SCHEDULE_ID}
        intro={seasonSchedule.intro}
        title={seasonSchedule.title}
        tone="inverse"
      >
        <Button href={seasonSchedule.action.href} variant="secondary">
          {seasonSchedule.action.label}
        </Button>
      </Section>

      <EmailUpdates content={emailUpdates} />

      {newest.length > 0 ? (
        <Section
          eyebrow={recentResults.eyebrow}
          id={RECENT_RESULTS_ID}
          intro={recentResults.intro}
          title={recentResults.title}
        >
          <ul className="recent-results">
            {newest.map((result) => (
              <li className="recent-results__item" key={result.position}>
                <span className="recent-results__line">
                  <ResultLine result={result} />
                </span>
                <span className="recent-results__where">
                  {result.tournament.name}, {formatDateRange(result.tournament)}
                </span>
              </li>
            ))}
          </ul>
          <Button href={recentResults.action.href} variant="secondary">
            {recentResults.action.label}
          </Button>
        </Section>
      ) : null}

      <Section
        contentWidth="wide"
        headerAlign="wide"
        eyebrow={entryPoints.eyebrow}
        id="start-here"
        intro={entryPoints.intro}
        title={entryPoints.title}
        tone="tinted"
      >
        <CardGrid columns={2}>
          {entryPoints.cards.map((card) => (
            <Card headingLevel={3} key={card.href} title={card.title}>
              <p>{card.body}</p>
              <Link className="link-cta" href={card.href} prefetch={false}>
                {card.actionLabel}
              </Link>
            </Card>
          ))}
        </CardGrid>
      </Section>

      <Section eyebrow={prose.eyebrow} id="what-debate-is" title={prose.title}>
        <Prose html={page.html} />
      </Section>

      <Section
        contentWidth="wide"
        headerAlign="wide"
        eyebrow={whatDebateBuilds.eyebrow}
        id="what-debate-builds"
        intro={whatDebateBuilds.intro}
        title={whatDebateBuilds.title}
      >
        <ul className="claim-list">
          {whatDebateBuilds.claims.map((claim) => (
            <li className="claim-list__item" key={claim.title}>
              <h3 className="claim-list__title">{claim.title}</h3>
              <p className="claim-list__body">{claim.body}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        contentWidth="wide"
        headerAlign="wide"
        eyebrow={academicCase.eyebrow}
        id="academic-case"
        intro={academicCase.intro}
        title={academicCase.title}
      >
        <CardGrid columns={2}>
          {academicCase.claims.map((claim) => (
            <Card headingLevel={3} key={claim.title} title={claim.title}>
              <p>{claim.body}</p>
              <SourceLine
                label={academicCase.sourceLabel}
                source={claim.source}
                {...(academicCase.externalLinkNote
                  ? { externalLinkNote: academicCase.externalLinkNote }
                  : {})}
              />
            </Card>
          ))}
        </CardGrid>
      </Section>
    </>
  )
}
