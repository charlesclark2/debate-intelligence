import { Section } from '@/components/Section'
import type { EmailUpdatesContent } from '@/lib/content'
import { EMAIL_UPDATES_ID } from '@/lib/content'

/**
 * The parent email-updates section (v1-e37-t05), on the home and contact pages.
 *
 * The whole mechanism is one link to the mailing service's hosted signup page. There is no form
 * and no input here, so there is nothing on this site that could receive a parent's address: it
 * goes from their browser to the provider after they have left. No provider script, pixel or
 * iframe is loaded, and `rel="noreferrer"` keeps the page they came from out of the request too.
 * The link says visibly that it leaves the team site, as every outbound link must
 * (docs/policies/website-publishing.md, pre-publication checklist 9).
 *
 * It opens in the same tab. Most people arrive from a QR code on a phone, where a second tab is
 * one more thing to lose.
 *
 * Every word comes from content/email-updates.json, with the provider's name filled in by the
 * loader. While the signup page's address is still a [[TBD]] marker, the action shows the gap
 * badge instead of a link, and src/lib/publishing-policy.ts fails a prod build on it.
 */
export function EmailUpdates({ content }: { content: EmailUpdatesContent }) {
  return (
    <Section
      eyebrow={content.eyebrow}
      id={EMAIL_UPDATES_ID}
      intro={content.intro}
      title={content.title}
    >
      <ul className="email-updates__points">
        {content.points.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
      {content.signupUrl ? (
        <a className="button button--primary" href={content.signupUrl} rel="noopener noreferrer">
          {content.action.label}
          <span> ({content.action.externalLinkNote})</span>
        </a>
      ) : (
        <p>
          {content.action.label}: <span className="placeholder">TBD</span>
        </p>
      )}
    </Section>
  )
}
