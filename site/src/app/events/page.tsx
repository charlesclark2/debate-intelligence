import type { Metadata } from 'next'
import Link from 'next/link'
import { Fragment } from 'react'

import { Card } from '@/components/Card'
import { CardGrid } from '@/components/CardGrid'
import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import { EVENTS_SLUG, EVENT_COMPARISON_FIELDS, loadEventsContent, loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

/** The band holding the three comparison cards. */
const COMPARISON_ID = 'compare-the-events'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(EVENTS_SLUG))
}

/**
 * The page that explains the three events to a parent who has never seen a round.
 *
 * The question it has to answer in about five seconds is "how are these three different?",
 * and twelve hundred words of prose under three headings never answered it: the facts that tell
 * one event from another were scattered through the paragraphs explaining each one.
 *
 * So the page is now read twice over. First the comparison: three cards, side by side above 48rem
 * and stacked on a phone, each carrying the same four fields in the same order, which is what
 * turns them into a comparison rather than three summaries. Reading across one row answers one
 * question about all three events at once. Then the detail: one band per event, in the same order,
 * each linked from its card, holding the full explanation unchanged.
 *
 * Not one string below is written here. The title and the lead come from content/pages/events.md
 * and everything else from content/events.yaml, both validated at build time;
 * tests/events.test.tsx fails if a word of that copy appears in this file.
 */
export default function EventsPage() {
  const page = loadPage(EVENTS_SLUG)
  const {
    comparisonLabels,
    currentTopicLabel,
    sharedTruths,
    comparisonTitle,
    comparisonIntro,
    events,
    closingSections,
  } = loadEventsContent()

  return (
    <>
      <Section headingLevel={1} title={page.title}>
        <Prose html={page.html} />
      </Section>

      {/* What a parent does not have to check event by event, so the comparison below only has to
          carry what actually differs. */}
      <Section
        contentWidth="wide"
        headerAlign="center"
        id="true-of-all-three"
        title={sharedTruths.title}
        tone="tinted"
      >
        <ul className="claim-list claim-list--three-across">
          {sharedTruths.items.map((item) => (
            <li className="claim-list__item" key={item.title}>
              <h3 className="claim-list__title">{item.title}</h3>
              <p className="claim-list__body">{item.body}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        contentWidth="wide"
        id={COMPARISON_ID}
        intro={comparisonIntro}
        title={comparisonTitle}
      >
        <CardGrid columns={3}>
          {events.map((event) => (
            <Card headingLevel={3} key={event.id} title={event.name}>
              <p className="event-card__summary">{event.summary}</p>
              {/* Apart from the four comparison fields below, because it is the one thing on
                  the card that changes during the season. */}
              <div className="event-topic">
                <p className="event-topic__label">{currentTopicLabel}</p>
                <div className="event-topic__value">
                  <Prose html={event.currentTopicHtml} />
                </div>
              </div>
              {/* The four fields, in one order, in all three cards. A definition list is what
                  this is: a label and the value of that label for this event. */}
              <dl className="event-comparison">
                {EVENT_COMPARISON_FIELDS.map((field) => (
                  <Fragment key={field}>
                    <dt className="event-comparison__label">{comparisonLabels[field]}</dt>
                    <dd className="event-comparison__value">{event.comparison[field]}</dd>
                  </Fragment>
                ))}
              </dl>
              <Link className="link-cta" href={`#${event.id}`} prefetch={false}>
                {event.detailActionLabel}
              </Link>
            </Card>
          ))}
        </CardGrid>
      </Section>

      {events.map((event) => (
        <Section id={event.id} key={event.id} title={event.name}>
          <Prose html={event.detailHtml} />
        </Section>
      ))}

      {closingSections.map((section) => (
        <Section id={section.id} key={section.id} title={section.title}>
          <Prose html={section.bodyHtml} />
        </Section>
      ))}
    </>
  )
}
