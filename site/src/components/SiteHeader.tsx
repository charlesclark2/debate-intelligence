import Image from 'next/image'
import Link from 'next/link'

import type { NavigationItem } from './SiteNav'
import { SiteNav } from './SiteNav'

/**
 * The banner landmark: the Blue Dukes lockup linking home, and the main navigation.
 *
 * The lockup PNG has an opaque white background (it was recovered from a JPEG), so it is only
 * ever placed on the white header. See site/README.md for the asset limitations.
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
            height={384}
            priority
            src="/brand/wfb-blue-dukes-lockup.png"
            width={476}
          />
        </Link>
        <SiteNav items={items} label={navigationLabel} />
      </div>
    </header>
  )
}
