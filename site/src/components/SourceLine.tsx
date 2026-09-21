import type { AcademicCaseClaim } from '@/lib/content'

/**
 * The line under a research claim saying what it rests on: who, where, when, and what they
 * measured (v1-e36-t09). Small text, so it is painted body grey rather than the muted grey or the
 * warm accent, which are large-text and non-text only (sections.css, and the contrast table in
 * tokens.css).
 *
 * Every word comes from content/home.yaml: the source itself, the label in front of it and the
 * note read out beside a link that leaves the team site. A claim whose source is still the
 * [[TBD: source]] marker shows the gap badge in its place, so a dev preview shows the hole and
 * src/lib/publishing-policy.ts fails a prod build on it.
 */
export function SourceLine({
  externalLinkNote,
  label,
  source,
}: {
  externalLinkNote?: string
  label: string
  source: AcademicCaseClaim['source']
}) {
  if (typeof source === 'string') {
    return (
      <p className="source-line">
        {label}: <span className="placeholder">TBD</span>
      </p>
    )
  }
  const publication = source.href ? (
    <a className="source-line__link" href={source.href} rel="noopener noreferrer">
      <cite>{source.publication}</cite>
      {externalLinkNote ? <span> ({externalLinkNote})</span> : null}
    </a>
  ) : (
    <cite>{source.publication}</cite>
  )
  return (
    <p className="source-line">
      {label}: {source.authors}, {publication}, {source.year}. {source.measured}
    </p>
  )
}
