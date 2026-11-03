import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { SiteFrame } from '@/components/SiteFrame'
import { announcementsGuardedContent } from '@/lib/announcements'
import {
  announcementFields,
  buildNavigation,
  loadGuardedContent,
  loadSiteSettings,
} from '@/lib/content'
import { debaterLoginNavigationItem } from '@/lib/feature-flags'
import { consentGuardedContent, loadMediaConsent } from '@/lib/media-consent'
import { enforcePublishingPolicy } from '@/lib/publishing-policy'
import { resultsGuardedContent } from '@/lib/results'
import { scheduleGuardedContent } from '@/lib/tournaments'
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

  // content/home.yaml, content/faq.yaml and content/events.yaml carry copy too, so they are
  // guarded alongside the Markdown pages rather than being the files on the site where an address
  // or a name is not checked. loadGuardedContent() is that list, scheduleGuardedContent() adds
  // content/schedule.yaml and every text field in content/tournaments.yaml, and
  // resultsGuardedContent() every result in content/results.yaml, in the words the page prints.
  // announcementsGuardedContent() is every file in content/announcements/ and the words in
  // content/news.yaml; loading it refuses, in every environment, an announcement that breaks the
  // policy, and a [[TBD]] in one fails a prod build here.
  // consentGuardedContent() carries no copy, only any consent reference still written as [[TBD]].
  // announcementFields() is the facts an announcement panel built from fields promises (none since
  // the October 1 panel was replaced; the Markdown announcements have no such fields). They go through the guard as fields rather than as copy
  // because a fact nobody has supplied leaves no trace in the copy. A prod build fails while one
  // is unset.
  enforcePublishingPolicy({
    pages: [
      ...loadGuardedContent(),
      ...scheduleGuardedContent(),
      ...resultsGuardedContent(),
      ...announcementsGuardedContent(),
      ...consentGuardedContent(),
    ],
    settings,
    consent: loadMediaConsent(),
    announcements: announcementFields(),
  })

  // The header carries the pages content/site.yaml names, in that order; the footer carries
  // everything else published. See buildNavigation in src/lib/content.ts.
  const { primary, utility } = buildNavigation()
  const items = [...primary]
  const debaterLogin = debaterLoginNavigationItem(settings.debaterLoginLabel)
  if (debaterLogin) {
    items.push(debaterLogin)
  }

  return (
    <html lang="en">
      <body>
        <SiteFrame items={items} strings={settings} utilityLinks={utility}>
          {children}
        </SiteFrame>
      </body>
    </html>
  )
}
