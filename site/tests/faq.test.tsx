import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import FaqPage from '@/app/faq/page'
import { SiteFrame } from '@/components/SiteFrame'
import { FAQ_SLUG, loadFaqContent, loadPage, loadPages, loadSiteSettings } from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * The parent FAQ (task v1-e36-t07 acceptance criteria 1 and 2).
 *
 * The page these assertions replace was sixteen questions and about a thousand words in one
 * column. A parent with one question had to read past fifteen others to reach it. So the
 * assertions here are about structure and about reach: that the questions are grouped and
 * indexed, that each one is the browser's own disclosure rather than a scripted imitation, that
 * the two or three most-asked open without a click, and, most importantly, that collapsing an
 * answer never puts it out of reach of find-in-page, a printer or a screen reader's browse mode.
 *
 * The page is rendered through the real SiteFrame, because the landmark and heading rules axe
 * checks only hold for a whole document.
 */

const page = loadPage(FAQ_SLUG)
const content = loadFaqContent()
const settings = loadSiteSettings()
const navigationItems = loadPages().map((item) => ({ href: item.route, label: item.navLabel }))

const allQuestions = content.groups.flatMap((group) => group.questions)

function renderFaq() {
  return render(
    <SiteFrame items={navigationItems} strings={settings}>
      <FaqPage />
    </SiteFrame>,
    { container: document.body },
  )
}

/** next/link settles its internal state a microtask after mount. */
async function flushPendingEffects() {
  await act(async () => {})
}

/** The <details> element whose <summary> carries this question. */
function disclosureFor(question: string): HTMLDetailsElement {
  const heading = screen.getByRole('heading', { name: question })
  const details = heading.closest('details')
  expect(details, `"${question}" is not inside a <details>`).not.toBeNull()
  return details as HTMLDetailsElement
}

describe('the questions are grouped into topics', () => {
  it('has the five topics the page is organised around, each with questions in it', () => {
    expect(content.groups.length).toBeGreaterThanOrEqual(2)
    renderFaq()
    for (const group of content.groups) {
      const section = document.getElementById(group.id)
      expect(section, `no section for the "${group.label}" topic`).not.toBeNull()
      expect(screen.getByRole('heading', { level: 2, name: group.label })).toBeDefined()
      for (const question of group.questions) {
        expect(within(section as HTMLElement).getByRole('heading', { name: question.question }))
          .toBeDefined()
      }
    }
  })

  /**
   * The sixteen questions in the v1-e36-t04 draft Charlie approved. This task regrouped them and
   * later reviews added to them, so a count cannot say whether one was lost on the way: the
   * roster can. A question removed on purpose is removed from this list in the same commit.
   */
  const APPROVED_QUESTIONS = [
    'Will I be expected to judge?',
    'How much time does it take?',
    'What does it cost?',
    'How do students get to tournaments?',
    'What does the first month look like?',
    'Does debate conflict with other activities and sports?',
    'Does my student need to be a strong public speaker before joining?',
    'Is debate mostly about arguing or being confrontational?',
    'How much research will my student need to do?',
    'How will my student know which type of debate is right for them?',
    'What happens at a debate tournament?',
    'Will my student win right away?',
    'How are students evaluated?',
    'What can parents do to support their student?',
    'What should my student bring to a tournament?',
    'How does debate help students outside of competition?',
  ]

  it('keeps every approved question, each in exactly one topic', () => {
    const questions = allQuestions.map((question) => question.question)
    expect(new Set(questions).size, 'a question appears in two topics').toBe(questions.length)
    for (const approved of APPROVED_QUESTIONS) {
      expect(questions, `"${approved}" was lost in the regrouping`).toContain(approved)
    }
  })
})

/**
 * Where the way out of the page sits.
 *
 * "If your question is not here, email Coach Clark" was the first thing a parent read, which put
 * the exit above the content. It belongs at the foot, where someone who has been through the
 * topics without finding their question is actually looking, and the top of the page belongs to
 * saying what the page is.
 */
describe('the page leads with what it is and closes with how to ask', () => {
  it('opens with a lead that explains the page, not with the email address', () => {
    renderFaq()
    const lead = document.querySelector('.section .prose') as HTMLElement
    expect(lead, 'the FAQ has no lead paragraph').not.toBeNull()
    expect(lead.textContent).not.toContain('@')
  })

  it('closes with the block for a question none of the topics answered', () => {
    renderFaq()
    const closing = document.getElementById('ask-a-question')
    expect(closing, 'no closing block on the FAQ').not.toBeNull()
    expect(screen.getByRole('heading', { level: 2, name: content.closing.title })).toBeDefined()
    expect(within(closing as HTMLElement).getByRole('link', { name: /@/ })).toBeDefined()
  })

  it('puts that block after every topic, not before them', () => {
    const { container } = renderFaq()
    const bands = [...(container.querySelectorAll('main > section') ?? [])]
    expect(bands.at(-1)?.id, 'the closing block is not the last band on the page').toBe(
      'ask-a-question',
    )
    const lastTopic = content.groups.at(-1)!.id
    expect(bands.findIndex((band) => band.id === lastTopic)).toBeLessThan(bands.length - 1)
  })
})

describe('the in-page topic index', () => {
  it('is a named navigation region linking to every topic section', () => {
    renderFaq()
    const index = screen.getByRole('navigation', { name: content.indexTitle })
    const links = within(index).getAllByRole('link')
    expect(links.map((link) => link.getAttribute('href'))).toEqual(
      content.groups.map((group) => `#${group.id}`),
    )
    expect(links.map((link) => link.textContent)).toEqual(
      content.groups.map((group) => group.label),
    )
  })

  it('is one column of equal rows, not a wrapped row of ragged pills', () => {
    const stylesheet = readFileSync(join(process.cwd(), 'src/styles/disclosure.css'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
    const list = /(?:^|\})\s*\.topic-index__list\s*\{([^}]*)\}/m.exec(stylesheet)?.[1] ?? ''
    expect(list, '.topic-index__list is not in disclosure.css').not.toBe('')
    // Five labels of five different lengths wrapped into three and two with ragged edges. A
    // single column is the same shape at 390px as it is on a desktop.
    expect(list).not.toMatch(/flex-wrap/)
    expect(list).toContain('display: grid')
  })

  it('points at a heading that is really on the page, not a dead anchor', () => {
    renderFaq()
    for (const group of content.groups) {
      const target = document.getElementById(group.id)
      expect(target, `#${group.id} is linked from the index but is not on the page`).not.toBeNull()
      expect(target?.getAttribute('aria-labelledby')).toBe(`${group.id}-title`)
      expect(document.getElementById(`${group.id}-title`)?.textContent).toBe(group.label)
    }
  })
})

describe('every question is the browser’s own disclosure', () => {
  it('renders one <details> per question, with the question in its <summary>', () => {
    renderFaq()
    const details = [...document.querySelectorAll('details')]
    expect(details).toHaveLength(allQuestions.length)
    for (const question of allQuestions) {
      const summary = disclosureFor(question.question).querySelector('summary')
      expect(summary, `"${question.question}" has no <summary>`).not.toBeNull()
      expect(summary?.textContent).toContain(question.question)
    }
  })

  /**
   * The forbidden shape from the task spec: a div with role="button" and aria-expanded, which has
   * to reimplement keyboard handling, state announcement, find-in-page and printing, and usually
   * gets at least one of them wrong.
   */
  it('builds no disclosure from role="button" and aria-expanded', () => {
    const { container } = renderFaq()
    const main = container.querySelector('main') as HTMLElement
    expect(main.querySelectorAll('[aria-expanded]')).toHaveLength(0)
    expect(main.querySelectorAll('[role="button"]')).toHaveLength(0)
  })

  it('puts the question in a heading, so the outline runs page, topic, question', () => {
    renderFaq()
    for (const question of allQuestions) {
      expect(screen.getByRole('heading', { level: 3, name: question.question })).toBeDefined()
    }
  })

  /**
   * Operability, in the two halves a test can actually separate.
   *
   * This half is activation: focusing a summary and triggering it opens and closes the answer,
   * with no handler of ours in the path. jsdom implements a summary's activation behaviour for a
   * click but not for Enter or Space, which is a gap in jsdom and not in the page: in a browser
   * both keys run that same activation behaviour, and they run it because the element is a real
   * <summary> inside a real <details>. The test below this one pins down exactly that, and the
   * keyboard-only walk of the built site in v1-e36-t08 is where a real browser presses the keys.
   */
  it('opens and closes by activating the summary, with no script of ours involved', async () => {
    const user = userEvent.setup()
    renderFaq()
    const closed = allQuestions.find((question) => !question.openByDefault)
    expect(closed, 'every question is open by default, so there is nothing to operate').toBeDefined()
    const details = disclosureFor(closed!.question)
    const summary = details.querySelector('summary') as HTMLElement

    summary.focus()
    expect(document.activeElement).toBe(summary)
    await user.click(summary)
    expect(details.open).toBe(true)
    await user.click(summary)
    expect(details.open).toBe(false)
  })

  it('leaves every summary natively focusable, which is what makes Enter and Space work', () => {
    renderFaq()
    const summaries = [...document.querySelectorAll('summary')]
    expect(summaries).toHaveLength(allQuestions.length)
    for (const summary of summaries) {
      // A tabindex of any value is the smell of a scripted accordion: a native summary needs
      // none, and setting one is how a hand-rolled widget usually loses Enter and Space.
      expect(summary.getAttribute('tabindex'), 'a summary should need no tabindex').toBeNull()
      expect(summary.parentElement?.tagName).toBe('DETAILS')
    }
  })

  /**
   * Reach: tabbing forward from the top of the questions arrives at every summary in document
   * order. It is not one tab per summary, and should not be: an open answer can contain a link,
   * as the cost answer does, and that link is in the tab order between the two summaries either
   * side of it. What matters is that no summary is skipped and none is reached out of order.
   */
  it('reaches every summary by tabbing, in the order the page reads', async () => {
    const user = userEvent.setup()
    renderFaq()
    const summaries = [...document.querySelectorAll('details > summary')]
    expect(summaries).toHaveLength(allQuestions.length)
    ;(summaries[0] as HTMLElement).focus()

    const reached: Element[] = [summaries[0] as Element]
    // Generous enough for every summary plus the links inside the open answers, and bounded so a
    // focus trap fails the test rather than hanging it.
    for (let step = 0; step < summaries.length * 3; step += 1) {
      await user.tab()
      const active = document.activeElement
      if (active && summaries.includes(active)) {
        reached.push(active)
      }
      if (reached.length === summaries.length) {
        break
      }
    }
    expect(reached).toEqual(summaries)
  })
})

describe('the most-asked questions open without a click', () => {
  const open = allQuestions.filter((question) => question.openByDefault)

  it('names two or three of them, and no more', () => {
    expect(open.length).toBeGreaterThanOrEqual(2)
    expect(open.length).toBeLessThanOrEqual(3)
  })

  it('renders the `open` attribute on exactly those questions', () => {
    renderFaq()
    for (const question of allQuestions) {
      expect(
        disclosureFor(question.question).open,
        `"${question.question}" open state`,
      ).toBe(question.openByDefault)
    }
    expect(document.querySelectorAll('details[open]')).toHaveLength(open.length)
  })
})

/**
 * Acceptance criterion 2, and the reason the task spec insists on native disclosure: a collapsed
 * answer is collapsed, not absent. Find-in-page, a printer and a screen reader's browse mode all
 * read the document, so every word has to be in it whatever the open state is.
 */
describe('a collapsed answer is still in the document', () => {
  it('holds the full text of every answer, open or closed', () => {
    renderFaq()
    for (const question of allQuestions) {
      const details = disclosureFor(question.question)
      const panel = details.querySelector('.disclosure__panel')
      expect(panel, `"${question.question}" has no answer panel`).not.toBeNull()
      // The first sentence of the answer, which is enough to prove the panel was rendered rather
      // than swapped for a placeholder.
      const firstSentence = question.answer.split('\n\n')[0]!.replace(/\s+/g, ' ').trim()
      const rendered = (panel as HTMLElement).textContent?.replace(/\s+/g, ' ').trim() ?? ''
      const plain = firstSentence.replace(/\*\*/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      expect(rendered.length, `"${question.question}" has an empty panel`).toBeGreaterThan(0)
      expect(plain.length).toBeGreaterThan(0)
      expect(rendered.includes(plain.slice(0, 40)), `"${question.question}" answer is missing`)
        .toBe(true)
    }
  })

  it('removes nothing from the DOM and hides nothing from a screen reader', () => {
    renderFaq()
    for (const details of document.querySelectorAll('details')) {
      expect(details.querySelector('[hidden]')).toBeNull()
      expect(details.querySelector('[aria-hidden="true"]')).toBeNull()
    }
  })
})

describe('the print stylesheet opens every disclosure', () => {
  const stylesheet = readFileSync(join(process.cwd(), 'src/styles/disclosure.css'), 'utf8')
  // This file is heavily commented, and a comment between two rules would otherwise be read as
  // part of the next rule's selector. tests/design-system.test.tsx strips them for the same reason.
  const withoutComments = stylesheet.replace(/\/\*[\s\S]*?\*\//g, '')
  const printBlock = /@media print \{([\s\S]*)\n\}/.exec(withoutComments)?.[1] ?? ''

  it('has a print block at all', () => {
    expect(printBlock.length, 'disclosure.css has no @media print block').toBeGreaterThan(0)
  })

  /**
   * Browsers hide a closed panel in two different ways, and a print rule that only handles one
   * of them prints sixteen questions and no answers in the other. Firefox and older Safari hide
   * the children of the <details>; Chrome and Edge apply content-visibility to the
   * ::details-content pseudo-element. Both are overridden.
   */
  it('reveals the panel in both the ways a browser hides it', () => {
    expect(printBlock).toContain('.disclosure > *:not(summary)')
    expect(printBlock).toContain('display: block !important')
    expect(printBlock).toContain('::details-content')
    expect(printBlock).toContain('content-visibility: visible !important')
  })

  it('hides nothing but the marker and the in-page index, which do nothing on paper', () => {
    const hidden = [...printBlock.matchAll(/([^{}]+)\{[^}]*display:\s*none[^}]*\}/g)].map((match) =>
      (match[1] ?? '').trim(),
    )
    expect(hidden.sort()).toEqual(['.disclosure__summary::before', '.topic-index'].sort())
  })

  it('never hides an answer anywhere in the stylesheet', () => {
    const panelRules = [...stylesheet.matchAll(/\.disclosure__panel[^{]*\{([^}]*)\}/g)].map(
      (match) => match[1] ?? '',
    )
    for (const body of panelRules) {
      expect(body).not.toMatch(/display:\s*none/)
      expect(body).not.toMatch(/visibility:\s*hidden/)
    }
  })
})

describe('the summary is a real target on a phone', () => {
  const stylesheet = readFileSync(join(process.cwd(), 'src/styles/disclosure.css'), 'utf8')

  function ruleBody(selector: string): string {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const match = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm').exec(
      stylesheet.replace(/\/\*[\s\S]*?\*\//g, ''),
    )
    return match?.[1] ?? ''
  }

  it('gives the summary the 44px minimum WCAG 2.1 asks for', () => {
    expect(ruleBody('.disclosure__summary')).toContain('min-height: 44px')
  })

  it('gives the topic index links the same minimum', () => {
    expect(ruleBody('.topic-index__link')).toContain('min-height: 44px')
  })

  it('leaves the site focus ring alone on the summary', () => {
    expect(stylesheet).not.toMatch(/outline:\s*none/)
  })
})

describe('the FAQ page as a whole', () => {
  it('has one h1, which is the page title from the content file', () => {
    renderFaq()
    const headings = document.querySelectorAll('h1')
    expect(headings).toHaveLength(1)
    expect(headings[0]?.textContent).toBe(page.title)
  })

  it('skips no heading level', () => {
    renderFaq()
    const levels = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
      Number.parseInt(heading.tagName.slice(1), 10),
    )
    for (const [index, level] of levels.entries()) {
      if (index > 0) {
        expect(level, `jumps from h${levels[index - 1]} to h${level}`).toBeLessThanOrEqual(
          (levels[index - 1] as number) + 1,
        )
      }
    }
  })

  it('has no WCAG 2.1 AA violation with the most-asked questions open', async () => {
    renderFaq()
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })

  it('has no WCAG 2.1 AA violation with every question open', async () => {
    const user = userEvent.setup()
    renderFaq()
    for (const summary of document.querySelectorAll('details:not([open]) > summary')) {
      await user.click(summary as HTMLElement)
    }
    expect(document.querySelectorAll('details:not([open])')).toHaveLength(0)
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

describe('the page holds no copy of its own', () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(join(process.cwd(), directory)).flatMap((entry) => {
      const path = join(directory, entry)
      if (statSync(join(process.cwd(), path)).isDirectory()) {
        return sourceFiles(path)
      }
      return entry.endsWith('.tsx') || entry.endsWith('.ts') ? [path] : []
    })
  }

  const sources = [...sourceFiles('src/app'), ...sourceFiles('src/components')].map(
    (path) => [path, readFileSync(join(process.cwd(), path), 'utf8')] as const,
  )

  const copy = [
    content.indexTitle,
    ...content.groups.flatMap((group) => [
      group.label,
      ...group.questions.flatMap((question) => [question.question, question.answer]),
    ]),
    content.closing.title,
    content.closing.body,
  ]

  it('shows more than a handful of strings, so this test is checking something', () => {
    expect(copy.length).toBeGreaterThan(20)
  })

  it.each(copy.map((text) => [text.slice(0, 48).replace(/\s+/g, ' '), text] as const))(
    '"%s..." is not written into a component',
    (_label, text) => {
      if (text.length < 12) {
        return
      }
      for (const [path, source] of sources) {
        expect(source.includes(text.trim()), `${path} contains FAQ copy`).toBe(false)
      }
    },
  )
})

/**
 * The export, which is the artefact CloudFront serves and therefore the one acceptance criterion
 * 2 is really about: "the full text of every answer is present in the built HTML whether or not
 * its disclosure is open".
 *
 * A component test can only say that React rendered the panel. This says that the panel survived
 * the static export and is sitting in the file a browser downloads, which is what makes
 * find-in-page, printing and a screen reader's browse mode work on the real page.
 *
 * It runs only when a build has produced site/out/, the same `describe.runIf` pattern the rest of
 * the suite uses: `pnpm --dir site test` comes before `pnpm --dir site build` in CI, and building
 * here would blow the CI budget in docs/process/working-agreements.md.
 */
const exportedFaq = join(process.cwd(), 'out', 'faq', 'index.html')
const hasExport = existsSync(exportedFaq)

describe.runIf(hasExport)('the exported FAQ page', () => {
  const html = hasExport ? readFileSync(exportedFaq, 'utf8') : ''
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
   * "wfbschools.org." into "wfbschools.org ." in the extracted text. That is a difference in the
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
