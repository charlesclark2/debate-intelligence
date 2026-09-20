import Link from 'next/link'
import type { ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary'

/**
 * A call to action. With `href` it renders a link (the usual case on a static site); without one
 * it renders a real <button>. Both share the site's focus ring, and both meet the 44px target
 * size that WCAG 2.1 AA recommends for touch.
 */
export function Button({
  children,
  href,
  variant = 'primary',
  onClick,
}: {
  children: ReactNode
  href?: string
  variant?: ButtonVariant
  onClick?: () => void
}) {
  const className = `button button--${variant}`
  if (href) {
    return (
      <Link className={className} href={href} prefetch={false}>
        {children}
      </Link>
    )
  }
  return (
    <button className={className} onClick={onClick} type="button">
      {children}
    </button>
  )
}
