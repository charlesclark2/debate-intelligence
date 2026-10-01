import { describe, expect, it } from 'vitest'

import { loadFaqContent } from '@/lib/content'

import { readExported } from './built-export'

/**
 * The exported FAQ page, which is the artefact CloudFront serves and therefore the one
 * v1-e36-t07 acceptance criterion 2 is really about: "the full text of every answer is present in
 * the built HTML whether or not its disclosure is open". tests/faq.test.tsx renders the page; this
 * reads what the build wrote.
 *
 * A component test can only say that React rendered the panel. This says that the panel survived
 * the static export and is sitting in the file a browser downloads, which is what makes
 * find-in-page, printing and a screen reader's browse mode work on the real page.
 */
const content = loadFaqContent()
const allQuestions = content.groups.flatMap((group) => group.questions)

describe('the exported FAQ page', () => {
  const html = readExported('faq/index.html')
  /** The React payload repeats the copy as escaped JSON inside <script>; ignore it. */
  const markup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
  /** The visible words: tags stripped and the entities Next escapes decoded back. */
  const text = markup
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#(\d+);/g, (_match, code: string) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_match, code: string) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')

  /**
   * Whitespace is dropped from both sides of the comparison rather than merely collapsed.
   * Stripping a tag leaves a space where the tag was, so the mailto link in the cost answer turns
   * "wfbschools.com." into "wfbschools.com ." in the extracted text. That is a difference in the
   * markup, not a missing sentence, and matching on the characters rather than the spacing is
   * what keeps this assertion about whether the answer shipped.
   */
  const condense = (value: string) => value.replace(/\s+/g, '')
  const condensedText = condense(text)

  it('exports one <details> per question', () => {
    expect([...markup.matchAll(/<details\b/g)]).toHaveLength(allQuestions.length)
  })

  it('carries the `open` attribute on the two or three most-asked questions and no others', () => {
    const open = allQuestions.filter((question) => question.openByDefault)
    expect(open.length).toBeGreaterThanOrEqual(2)
    expect(open.length).toBeLessThanOrEqual(3)
    expect([...markup.matchAll(/<details\b[^>]*\bopen\b/g)]).toHaveLength(open.length)
  })

  it('holds the full text of every answer, including the collapsed ones', () => {
    for (const question of allQuestions) {
      // Every sentence of every answer, with the Markdown emphasis and link syntax removed, in
      // the order it was written.
      const sentences = question.answer
        .replace(/\*\*/g, '')
        .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
        .replace(/<([^>@\s]+@[^>\s]+)>/g, '$1')
        .split(/(?<=\.)\s+/)
        .map((sentence) => sentence.replace(/\s+/g, ' ').trim())
        .filter((sentence) => sentence.length > 24)
      expect(sentences.length, `${question.question} produced no sentences to check`)
        .toBeGreaterThan(0)
      for (const sentence of sentences) {
        expect(
          condensedText.includes(condense(sentence)),
          `${question.question}: "${sentence}" is not in the export`,
        ).toBe(true)
      }
    }
  })

  it('builds no disclosure from role="button" and aria-expanded', () => {
    const main = /<main\b[\s\S]*?<\/main>/.exec(markup)?.[0] ?? ''
    expect(main.length, 'no <main> in the exported FAQ page').toBeGreaterThan(0)
    expect(main).not.toMatch(/aria-expanded/)
    expect(main).not.toMatch(/role="button"/)
  })

  it('links the topic index at every topic section that is really in the file', () => {
    for (const group of content.groups) {
      expect(markup, `the index links #${group.id}`).toContain(`href="#${group.id}"`)
      expect(markup, `#${group.id} is not in the export`).toContain(`id="${group.id}"`)
    }
  })
})
