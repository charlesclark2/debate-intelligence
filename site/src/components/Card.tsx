import type { ReactNode } from 'react'

/**
 * A panel on the tinted surface. The heading level is passed in so a page keeps one unbroken
 * heading outline rather than every card claiming <h2>.
 */
export function Card({
  children,
  headingLevel = 2,
  title,
}: {
  children: ReactNode
  headingLevel?: 2 | 3 | 4
  title: string
}) {
  const Heading = `h${headingLevel}` as const
  return (
    <article className="card">
      <Heading className="card__title">{title}</Heading>
      <div className="card__body">{children}</div>
    </article>
  )
}
