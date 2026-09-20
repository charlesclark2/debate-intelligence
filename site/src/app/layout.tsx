import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { SiteFrame } from '@/components/SiteFrame'
import { loadPages, loadSiteSettings } from '@/lib/content'
import { debaterLoginNavigationItem } from '@/lib/feature-flags'
import { loadMediaConsent } from '@/lib/media-consent'
import { enforcePublishingPolicy } from '@/lib/publishing-policy'
import { isIndexable, readSiteUrl } from '@/lib/site-settings'
import '@/styles/globals.css'

export function generateMetadata(): Metadata {
  const settings = loadSiteSettings()
  const indexable = isIndexable()
  return {
    metadataBase: new URL(readSiteUrl()),
    title: {
      default: settings.name,
      template: `%s | ${settings.shortName}`,
    },
    description: settings.tagline,
    applicationName: settings.name,
    robots: { index: indexable, follow: indexable },
  }
}

/**
 * The page frame. Every string comes from site/content/site.yaml and every navigation entry from
 * site/content/pages/; the layout holds no copy of its own.
 *
 * It is also where the publishing-policy guard runs, because the layout is built for every route:
 * a prod build throws here rather than exporting a page with an unfilled placeholder, a
 * non-allowlisted email address or a student named without current-season consent. A dev build
 * prints the same findings and carries on, so Charlie can review the copy with the gaps visible.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  const settings = loadSiteSettings()
  const pages = loadPages()

  enforcePublishingPolicy({ pages, settings, consent: loadMediaConsent() })

  const items = pages.map((page) => ({ href: page.route, label: page.navLabel }))
  const debaterLogin = debaterLoginNavigationItem(settings.debaterLoginLabel)
  if (debaterLogin) {
    items.push(debaterLogin)
  }

  return (
    <html lang="en">
      <body>
        <SiteFrame items={items} strings={settings}>
          {children}
        </SiteFrame>
      </body>
    </html>
  )
}
