import Link from 'next/link'
import type { ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary'
/** `large` is the hero action; everything else on the site uses `medium`. */
export type ButtonSize = 'medium' | 'large'

/**
 * A call to action. With `href` it renders a link (the usual case on a static site); without one
 * it renders a real <button>. Both share the site's focus ring, and both meet the 44px target
 * size that WCAG 2.1 AA recommends for touch.
 *
 * Inside a Section with the inverse tone the same variants invert automatically, in CSS: the
 * primary action becomes a white button with a navy label rather than navy on navy. Nothing at
 * the call site changes, so a component cannot be placed on navy and forgotten about.
 */
export function Button({
  children,
  href,
  size = 'medium',
  variant = 'primary',
  onClick,
}: {
  children: ReactNode
  href?: string
  size?: ButtonSize
  variant?: ButtonVariant
  onClick?: () => void
}) {
  const className = `button button--${variant}${size === 'large' ? ' button--large' : ''}`
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
