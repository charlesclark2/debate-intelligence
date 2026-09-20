import { MAIN_CONTENT_ID } from './landmark-ids'

/**
 * The first focusable element on every page. It is positioned off-screen until it takes focus,
 * so a keyboard or screen-reader user can jump straight past the header navigation.
 */
export function SkipLink({ label }: { label: string }) {
  return (
    <a className="skip-link" href={`#${MAIN_CONTENT_ID}`}>
      {label}
    </a>
  )
}
