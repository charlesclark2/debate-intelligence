import type { ReactNode } from 'react'

/**
 * The surface a section sits on. White is the default; the panel tint gives a band of the page
 * quiet contrast, and the inverse navy is reserved for the one block that has to outrank
 * everything else on the page (on the home page, the October 1 parent session).
 */
export type SectionTone = 'plain' | 'tinted' | 'inverse'

/**
 * How wide the band's content is allowed to be. `text` is the centred text column that almost
 * everything uses; `wide` lets a grid of cards break out to the full band, centred on the same
 * axis, which is the one thing on a page wide enough to need it.
 */
export type SectionContentWidth = 'text' | 'wide'

/**
 * One band of a page: full-bleed background, content centred inside it, and the same vertical
 * rhythm everywhere (--space-section-block, which grows from 3rem on a phone to 5rem from tablet
 * width up).
 *
 * The heading and the content sit in the same centred text column by default, so they share a
 * left edge and the band reads as centred rather than as having slipped sideways. A band whose
 * content is a card grid passes contentWidth="wide" to break out of that column.
 *
 * A section with a `title` is given `aria-labelledby`, which names it for a screen reader moving
 * by region. That needs a stable id, so the caller passes one rather than the component inventing
 * one: an id generated at render time would differ between the server render and the browser,
 * and these are anchor targets on the home page besides.
 *
 * The heading level is the caller's choice for the same reason Card takes one: a page keeps a
 * single unbroken outline rather than every band claiming <h2>.
 */
export function Section({
  children,
  contentWidth = 'text',
  eyebrow,
  headingLevel = 2,
  id,
  intro,
  title,
  tone = 'plain',
}: {
  children: ReactNode
  contentWidth?: SectionContentWidth
  eyebrow?: string
  headingLevel?: 2 | 3
  id?: string
  intro?: string
  title?: string
  tone?: SectionTone
}) {
  const Heading = `h${headingLevel}` as const
  const headingId = id ? `${id}-title` : undefined
  const hasHeader = Boolean(eyebrow || title || intro)

  return (
    <section
      className={`section section--${tone}`}
      {...(id ? { id } : {})}
      {...(title && headingId ? { 'aria-labelledby': headingId } : {})}
    >
      <div className="section__inner">
        {hasHeader ? (
          <div className="section__header">
            {eyebrow ? <p className="section__eyebrow">{eyebrow}</p> : null}
            {title ? (
              <Heading className="section__title" {...(headingId ? { id: headingId } : {})}>
                {title}
              </Heading>
            ) : null}
            {intro ? <p className="section__intro">{intro}</p> : null}
          </div>
        ) : null}
        {contentWidth === 'text' ? <div className="section__column">{children}</div> : children}
      </div>
    </section>
  )
}
