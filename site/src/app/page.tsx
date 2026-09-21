import type { Metadata } from 'next'
import Link from 'next/link'
import { Fragment } from 'react'

import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { CardGrid } from '@/components/CardGrid'
import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import { HOME_SLUG, loadHomeContent, loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

/** Names the October 1 panel for a screen reader moving by region. */
const PARENT_SESSION_ID = 'parent-session'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(HOME_SLUG))
}

/**
 * The home page.
 *
 * Five bands, in the order a parent needs them: the hero, the October 1 parent session, four
 * entry points into the site, what debate actually is, and what a season of it builds. The
 * October 1 panel is the only band on navy, which is what makes it the most prominent thing on
 * the page after the hero without giving it a bigger heading than its neighbours.
 *
 * Not one string below is written here. The title and the prose come from content/pages/home.md
 * and everything else from content/home.yaml, both read through src/lib/content.ts and validated
 * at build time; tests/home.test.tsx fails if a word of that copy appears in this file.
 */
export default function HomePage() {
  const page = loadPage(HOME_SLUG)
  const { hero, parentSession, entryPoints, prose, whatDebateBuilds } = loadHomeContent()

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
        eyebrow={parentSession.eyebrow}
        id={PARENT_SESSION_ID}
        intro={parentSession.intro}
        title={parentSession.title}
        tone="inverse"
      >
        <dl className="parent-session__facts">
          {parentSession.facts.map((fact) => (
            <Fragment key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.value ?? <span className="placeholder">{fact.unsetNote}</span>}
              </dd>
            </Fragment>
          ))}
        </dl>
        <ul className="parent-session__expect">
          {parentSession.whatToExpect.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p>{parentSession.note}</p>
        <Button href={parentSession.action.href} variant="secondary">
          {parentSession.action.label}
        </Button>
      </Section>

      <Section
        contentWidth="wide"
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
    </>
  )
}
