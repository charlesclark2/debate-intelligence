import type { ReactNode } from 'react'

import { MAIN_CONTENT_ID } from './landmark-ids'
import type { NavigationItem } from './SiteNav'
import { SiteFooter } from './SiteFooter'
import { SiteHeader } from './SiteHeader'
import { SkipLink } from './SkipLink'

export interface SiteFrameStrings {
  shortName: string
  skipLinkLabel: string
  navigationLabel: string
  logoAlternativeText: string
  footerNote: string
}

/**
 * Everything inside <body>: the skip link, the banner, the main landmark and the contentinfo
 * landmark, in that order. It lives apart from app/layout.tsx so the accessibility tests can
 * render the real frame into a jsdom document instead of a copy of it.
 *
 * <main> carries tabIndex={-1} so that following the skip link moves keyboard focus into the
 * content rather than only scrolling the page.
 */
export function SiteFrame({
  children,
  items,
  strings,
}: {
  children: ReactNode
  items: NavigationItem[]
  strings: SiteFrameStrings
}) {
  return (
    <>
      <SkipLink label={strings.skipLinkLabel} />
      <SiteHeader
        homeHref="/"
        items={items}
        logoAlternativeText={strings.logoAlternativeText}
        navigationLabel={strings.navigationLabel}
      />
      <main className="site-main" id={MAIN_CONTENT_ID} tabIndex={-1}>
        {children}
      </main>
      <SiteFooter note={strings.footerNote} wordmark={strings.shortName} />
    </>
  )
}
