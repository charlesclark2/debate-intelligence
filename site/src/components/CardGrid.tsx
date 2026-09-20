import { Children, type ReactNode } from 'react'

/**
 * Lays Cards out in a grid: one up on a phone, then two or three up from 48rem.
 *
 * Each child is wrapped in a list item, so the set is announced as a list of N and a screen
 * reader user is told how many entry points there are before reading them. That is why the
 * component wraps rather than expecting the caller to: a <ul> may contain only <li>, and a Card
 * renders an <article>.
 */
export function CardGrid({ children, columns = 2 }: { children: ReactNode; columns?: 2 | 3 }) {
  return (
    <ul className={`card-grid card-grid--${columns}-up`}>
      {Children.map(children, (child, index) => (
        // The children of a grid are a fixed list written out in the page source, never
        // reordered or filtered, so the index is a stable identity here.
        <li className="card-grid__item" key={index}>
          {child}
        </li>
      ))}
    </ul>
  )
}
