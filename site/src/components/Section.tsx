import type { ReactNode } from 'react'

/**
 * The surface a section sits on. White is the default; the panel tint gives a band of the page
 * quiet contrast, and the inverse navy is reserved for the one block that has to outrank
 * everything else on the page (on the home page, the October 1 parent session).
 */
export type SectionTone = 'plain' | 'tinted' | 'inverse'

/**
 * One band of a page: full-bleed background, content centred inside it at the site measure, and
 * the same vertical rhythm everywhere (--space-section-block, which grows from 3rem on a phone to
 * 5rem from tablet width up).
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
  eyebrow,
  headingLevel = 2,
  id,
  intro,
  title,
  tone = 'plain',
}: {
  children: ReactNode
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
        {children}
      </div>
    </section>
  )
}
