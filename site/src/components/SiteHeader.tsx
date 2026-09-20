import Image from 'next/image'
import Link from 'next/link'

import type { NavigationItem } from './SiteNav'
import { SiteNav } from './SiteNav'

/**
 * The banner landmark: the "W BAY" mark linking home, and the main navigation.
 *
 * The mark is a transparent PNG, so it sits on the white header without a white box around it.
 * The footer uses the white knockout version of the same artwork on brand navy.
 */
export function SiteHeader({
  homeHref,
  logoAlternativeText,
  navigationLabel,
  items,
}: {
  homeHref: string
  logoAlternativeText: string
  navigationLabel: string
  items: NavigationItem[]
}) {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <Link className="site-header__brand" href={homeHref} prefetch={false}>
          <Image
            alt={logoAlternativeText}
            className="site-header__logo"
            height={264}
            priority
            src="/brand/wfb-mark-navy-transparent.png"
            width={441}
          />
        </Link>
        <SiteNav items={items} label={navigationLabel} />
      </div>
    </header>
  )
}
