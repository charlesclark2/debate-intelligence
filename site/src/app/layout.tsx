import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { SiteFrame } from '@/components/SiteFrame'
import { loadPages, loadSiteSettings } from '@/lib/content'
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
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  const settings = loadSiteSettings()
  const items = loadPages().map((page) => ({ href: page.route, label: page.navLabel }))

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
