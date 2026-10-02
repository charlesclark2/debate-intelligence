import type { Metadata } from 'next'
import { Fragment } from 'react'

import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import { SCHEDULE_SLUG, loadPage } from '@/lib/content'
import { calendarHttpsUrl, calendarWebcalUrl } from '@/lib/icalendar'
import { buildPageMetadata } from '@/lib/page-metadata'
import { readSiteUrl } from '@/lib/site-settings'
import { formatDate, formatDateRange, loadScheduleView } from '@/lib/tournaments'
import type { ScheduleView, Tournament } from '@/lib/tournaments'

/** The band with the subscribe links. Section ids carry no year, so no tournament id can match. */
const SUBSCRIBE_ID = 'subscribe'
const SEASON_ID = 'season'
const NATIONALS_ID = 'nationals'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(SCHEDULE_SLUG))
}

/**
 * One tournament. Everything a parent decides on is on the face of the entry: the dates, how it
 * is held (which decides whether a student needs a ride), the events, overnight, and the status
 * with its condition written out. An entry that shares any day with another says so at the top
 * and links to the other one; both stay on the page, in date order.
 */
function TournamentEntry({ tournament, view }: { tournament: Tournament; view: ScheduleView }) {
  const { labels } = view.content
  const others = view.overlaps.get(tournament.id) ?? []
  const modifiers = [
    others.length > 0 ? 'schedule-entry--overlap' : '',
    tournament.status === 'confirmed' ? '' : `schedule-entry--${tournament.status}`,
  ].filter(Boolean)

  return (
    <li className={['schedule-entry', ...modifiers].join(' ')} id={tournament.id}>
      <article aria-labelledby={`${tournament.id}-name`}>
        <h3 className="schedule-entry__name" id={`${tournament.id}-name`}>
          {tournament.name}
        </h3>
        <p className="schedule-entry__dates">{formatDateRange(tournament)}</p>
        {others.length > 0 ? (
          <p className="schedule-entry__overlap">
            <strong>{labels.overlap}:</strong>{' '}
            {others.map((other, index) => (
              <Fragment key={other.id}>
                {index > 0 ? '; ' : ''}
                <a href={`#${other.id}`}>{other.name}</a> ({formatDateRange(other)})
              </Fragment>
            ))}
          </p>
        ) : null}
        <dl className="schedule-entry__facts">
          {view.facts(tournament).map((fact, index) => (
            <Fragment key={`${fact.key}-${index}`}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.key === 'status' ? (
                  <>
                    <span className={`status-badge status-badge--${tournament.status}`}>
                      {fact.value}
                    </span>
                    {fact.detail ? (
                      <span className="schedule-entry__condition">{fact.detail}</span>
                    ) : null}
                  </>
                ) : (
                  fact.value
                )}
              </dd>
            </Fragment>
          ))}
        </dl>
      </article>
    </li>
  )
}

function TournamentList({ tournaments, view }: { tournaments: Tournament[]; view: ScheduleView }) {
  return (
    <ol className="schedule-list">
      {tournaments.map((tournament) => (
        <TournamentEntry key={tournament.id} tournament={tournament} view={view} />
      ))}
    </ol>
  )
}

/**
 * The tournament schedule (v1-e37-t02).
 *
 * The whole season in date order, then nationals in a section of their own. Nothing is hidden
 * or reordered by the date the site was built: deploys are manual, so a page that dropped
 * "past" tournaments would be right on the day it was built and wrong for every day after. A
 * tournament that has happened stays where it was.
 *
 * Not one string below is written here. The title and the opening come from
 * content/pages/schedule.md, the headings and labels from content/schedule.yaml, and the
 * tournaments from content/tournaments.yaml, all validated at build time;
 * tests/schedule.test.tsx fails if a word of that copy appears in this file.
 */
export default function SchedulePage() {
  const page = loadPage(SCHEDULE_SLUG)
  const view = loadScheduleView()
  const { content } = view
  const siteUrl = readSiteUrl()

  return (
    <>
      <Section headingLevel={1} title={page.title}>
        <Prose html={page.html} />
        <p className="schedule-revised">
          {content.labels.revised}: {formatDate(view.revised)}
        </p>
      </Section>

      <Section
        id={SUBSCRIBE_ID}
        intro={content.subscribe.intro}
        title={content.subscribe.title}
        tone="tinted"
      >
        <p>
          <a className="button button--primary" href={calendarWebcalUrl(siteUrl)}>
            {content.subscribe.subscribeLabel}
          </a>
        </p>
        <p className="schedule-subscribe__address">
          <span className="schedule-subscribe__label">{content.subscribe.linkLabel}</span>
          <a href={calendarHttpsUrl(siteUrl)}>{calendarHttpsUrl(siteUrl)}</a>
        </p>
        <ul className="schedule-subscribe__steps">
          {content.subscribe.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ul>
      </Section>

      <Section
        contentWidth="wide"
        headerAlign="wide"
        id={SEASON_ID}
        intro={content.seasonIntro}
        title={view.seasonTitle}
      >
        <TournamentList tournaments={view.seasonTournaments} view={view} />
      </Section>

      <Section
        contentWidth="wide"
        headerAlign="wide"
        id={NATIONALS_ID}
        intro={content.nationalsIntro}
        title={content.nationalsTitle}
        tone="tinted"
      >
        <TournamentList tournaments={view.nationals} view={view} />
      </Section>
    </>
  )
}
