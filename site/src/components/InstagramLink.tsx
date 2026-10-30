import type { InstagramLinkSettings } from '@/lib/content'

/**
 * The link to the team's Instagram account (v1-e37-t07), in the footer of every page and on the
 * contact page.
 *
 * It is an ordinary anchor and nothing else. Charlie asked for the Instagram to be added or
 * embedded; the publishing policy allows a plain text link out to a social account and forbids
 * the vendor's code: no embed, feed, follow button, script, iframe or image from Instagram or Meta
 * (docs/policies/website-publishing.md, Analytics and third parties 4). There is no icon, so there
 * is nothing to fetch and nothing for a screen reader to announce twice. tests/export/
 * no-third-party-scripts.export-test.ts pins that the built site holds this anchor and no other
 * trace of Instagram.
 *
 * The visible text says it opens Instagram's site, as every link leaving the team site must
 * (pre-publication checklist 9), and is one run of text so the accessible name is exactly what a
 * sighted visitor reads. It opens in the same tab, like the email-updates link; `noreferrer` keeps
 * the page a visitor came from out of the request to Instagram.
 *
 * The address and every word come from content/site.yaml.
 */
export function InstagramLink({
  className,
  instagram,
}: {
  className?: string
  instagram: InstagramLinkSettings
}) {
  return (
    <a className={className} href={instagram.address} rel="noopener noreferrer">
      {`${instagram.label} (${instagram.externalLinkNote})`}
    </a>
  )
}
