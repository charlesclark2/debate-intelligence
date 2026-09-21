'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

export interface NavigationItem {
  href: string
  label: string
}

/**
 * Compares two site paths without caring about the trailing slash.
 *
 * next.config.ts sets trailingSlash, so a route is written "/join/", but the pathname a browser
 * reports and the one next/link normalises to are not reliably in the same form. Comparing the
 * trimmed paths is what keeps the current page marked in the export, in the browser, and in a
 * test, rather than in two of the three.
 */
function isSamePath(left: string, right: string): boolean {
  const trim = (path: string) => path.replace(/\/+$/, '')
  return trim(left) === trim(right) && left.startsWith('/')
}

/**
 * The site's main navigation.
 *
 * On a narrow screen the list collapses behind a disclosure button; from the `--breakpoint-nav`
 * width up, the button is hidden and the list is always shown. The button is a real <button>
 * with aria-expanded and aria-controls, so it works with Enter, Space and a screen reader, and
 * Escape closes the menu and returns focus to the button. No JavaScript is required to read the
 * page: the list is plain markup, and the collapsing is done in CSS.
 *
 * Links opt out of prefetching. The whole site is a static export of a handful of pages,
 * so prefetching every route would cost the visitor requests for no gain.
 *
 * The link to the page you are on carries aria-current="page", which is what tells a screen
 * reader user where they are in a list of seven links that otherwise all sound alike. It is also
 * marked visually, because that information is no less useful to someone who can see the nav.
 */
export function SiteNav({ items, label }: { items: NavigationItem[]; label: string }) {
  const pathname = usePathname()
  const [isOpen, setIsOpen] = useState(false)
  const menuId = useId()
  const toggleRef = useRef<HTMLButtonElement>(null)

  const close = useCallback(() => {
    setIsOpen(false)
    toggleRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!isOpen) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        close()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [isOpen, close])

  return (
    <nav aria-label={label} className="site-nav">
      <button
        aria-controls={menuId}
        aria-expanded={isOpen}
        className="site-nav__toggle"
        onClick={() => setIsOpen((open) => !open)}
        ref={toggleRef}
        type="button"
      >
        <span aria-hidden="true" className="site-nav__toggle-icon" />
        {isOpen ? 'Close menu' : 'Menu'}
      </button>
      <ul
        className={isOpen ? 'site-nav__list site-nav__list--open' : 'site-nav__list'}
        id={menuId}
      >
        {items.map((item) => {
          const isCurrent = pathname ? isSamePath(pathname, item.href) : false
          return (
            <li key={item.href}>
              <Link
                aria-current={isCurrent ? 'page' : undefined}
                className={isCurrent ? 'site-nav__link site-nav__link--current' : 'site-nav__link'}
                href={item.href}
                onClick={() => setIsOpen(false)}
                prefetch={false}
              >
                {item.label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
