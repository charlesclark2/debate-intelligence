import type { PublishedResult } from '@/lib/results'

/**
 * One placing as a line: the placing first, because it is what a parent scans for, then the
 * division and event, then who placed. The same words as resultLine() in src/lib/results.ts,
 * which is what the publishing-policy guard reads, so the guard checks exactly what is printed.
 *
 * A team-level result is printed the same way as a named one, in the same type and the same
 * place: the policy's team-level form is never shown as a lesser outcome (Results and awards 2).
 */
export function ResultLine({ result }: { result: PublishedResult }) {
  return (
    <>
      <strong className="result-line__placing">{result.placingLabel}</strong>,{' '}
      {result.divisionLabel} {result.eventName}:{' '}
      <span className="result-line__who">{result.who}</span>
    </>
  )
}
