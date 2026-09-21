import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from '@/components/Button'
import { Section } from '@/components/Section'
import { SiteFooter } from '@/components/SiteFooter'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * The design system's rules, asserted from the stylesheets themselves.
 *
 * jsdom has no cascade and no layout engine, so rendering a button here tells you nothing about
 * what it looks like. What can be checked without a browser is the source: that both action
 * variants really do have four distinct states, that the 44px target survived the padding the
 * design pass gave them, that every transition is inside the 200ms cap the task spec sets, and
 * that the prefers-reduced-motion block covers all of them. The visual confirmation is the
 * screenshot and Lighthouse sweep in v1-e36-t08.
 */

const STYLES_DIRECTORY = join(process.cwd(), 'src/styles')

/**
 * These files are heavily commented, and a comment sitting between two rules would otherwise be
 * read as part of the next rule's selector. Stripping comments before matching keeps the
 * assertions about CSS rather than about prose.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '')
}

function readStylesheet(name: string): string {
  return withoutComments(readFileSync(join(STYLES_DIRECTORY, name), 'utf8'))
}

const stylesheets = readdirSync(STYLES_DIRECTORY)
  .filter((entry) => entry.endsWith('.css'))
  .sort()
  .map((entry) => [entry, readStylesheet(entry)] as const)

const allStyles = stylesheets.map(([, source]) => source).join('\n')
const components = readStylesheet('components.css')
const globals = readStylesheet('globals.css')
const tokens = readStylesheet('tokens.css')

/** The declarations of the first rule whose selector list matches exactly. */
function ruleBody(source: string, selector: string): string | null {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm').exec(source)?.[1] ?? null
}

function declaration(body: string, property: string): string | null {
  return new RegExp(`(?:^|;)\\s*${property}:\\s*([^;]+)`, 'm').exec(body)?.[1]?.trim() ?? null
}

describe('the action variants have four distinct states', () => {
  const variants = ['primary', 'secondary'] as const

  it.each(variants)('%s has a rest, hover and active treatment', (variant) => {
    const rest = ruleBody(components, `.button--${variant}`)
    const hover = ruleBody(components, `.button--${variant}:hover`)
    const active = ruleBody(components, `.button--${variant}:active`)

    expect(rest, `.button--${variant} has no rest state`).not.toBeNull()
    expect(hover, `.button--${variant} has no hover state`).not.toBeNull()
    expect(active, `.button--${variant} has no active state`).not.toBeNull()

    // Hover has to change the fill, not merely exist: a hover rule that repeats the rest state
    // is the failure this assertion is for.
    expect(declaration(hover!, 'background-color')).not.toBe(
      declaration(rest!, 'background-color'),
    )
  })

  it('presses on :active, and does not animate the press', () => {
    const press = ruleBody(components, '.button:active')
    expect(press).not.toBeNull()
    expect(press).toContain('translateY(1px)')
    expect(declaration(press!, 'transition')).toBeNull()
  })

  it('inverts both variants on navy, where the navy fill would vanish', () => {
    const primaryOnNavy = ruleBody(components, '.section--inverse .button--primary')
    const secondaryOnNavy = ruleBody(components, '.section--inverse .button--secondary')
    expect(primaryOnNavy).not.toBeNull()
    expect(secondaryOnNavy).not.toBeNull()
    expect(declaration(primaryOnNavy!, 'background-color')).toBe('var(--color-surface)')
    expect(declaration(primaryOnNavy!, 'color')).toBe('var(--color-brand-navy)')
  })
})

describe('the focus ring', () => {
  /** v1-e36-t06 acceptance criterion 3: the design pass may add surfaces, not move the ring. */
  it('is still the one v1-e36-t03 set, declared once for the whole site', () => {
    const focusVisible = ruleBody(globals, ':focus-visible')
    expect(focusVisible).not.toBeNull()
    expect(declaration(focusVisible!, 'outline')).toBe('3px solid var(--color-focus-ring)')
    expect(declaration(focusVisible!, 'outline-offset')).toBe('2px')
  })

  it('switches to its inverse form on every navy surface', () => {
    const sections = readStylesheet('sections.css')
    const layout = readStylesheet('layout.css')
    for (const [name, source, selector] of [
      ['sections.css', sections, '.section--inverse :focus-visible'],
      ['layout.css', layout, '.site-footer :focus-visible'],
    ] as const) {
      const body = ruleBody(source, selector)
      expect(body, `${name} does not invert the ring for ${selector}`).not.toBeNull()
      expect(declaration(body!, 'outline-color')).toBe('var(--color-focus-ring-inverse)')
    }
  })

  it('is never removed without a replacement', () => {
    // `outline: none` is only legitimate on the two elements that opt out of a mouse-click ring
    // and re-declare a :focus-visible ring of their own.
    const removals = [...allStyles.matchAll(/([^}{]+)\{[^}]*outline:\s*none[^}]*\}/g)].map(
      (match) => match[1]?.trim(),
    )
    expect(removals.sort()).toEqual([':focus:not(:focus-visible)', '.site-main:focus'].sort())
  })
})

describe('touch targets stay at 44px', () => {
  const targets = [
    ['.button', 'components.css'],
    ['.link-cta', 'components.css'],
  ] as const

  it.each(targets)('%s keeps a 44px minimum', (selector) => {
    const body = ruleBody(components, selector)
    expect(body, `${selector} is not in components.css`).not.toBeNull()
    expect(declaration(body!, 'min-height')).toBe('44px')
  })

  it('gives the button a 44px minimum on both axes', () => {
    expect(declaration(ruleBody(components, '.button')!, 'min-width')).toBe('44px')
  })

  it('does not shrink the target when the hero action grows', () => {
    const large = ruleBody(components, '.button--large')
    expect(Number.parseInt(declaration(large!, 'min-height') ?? '0', 10)).toBeGreaterThanOrEqual(44)
  })
})

/**
 * Motion (v1-e36-t06 acceptance criterion 5). Restrained means three things here, and each is
 * checked rather than asserted in a comment: nothing longer than 200ms, nothing running on load,
 * and nothing that ignores prefers-reduced-motion.
 */
describe('motion is restrained', () => {
  const durationToken = /^\s*--duration-transition:\s*(\d+)ms;/m.exec(tokens)?.[1]

  /** Every duration in a transition declaration, with the motion token resolved. */
  const durations = stylesheets.flatMap(([name, source]) =>
    [...source.matchAll(/transition(?:-duration)?:\s*([^;]+);/g)].flatMap((match) =>
      [...(match[1] ?? '').matchAll(/var\(--duration-transition\)|(\d+(?:\.\d+)?)(ms|s)\b/g)].map(
        (value) => ({
          name,
          milliseconds: value[0].startsWith('var(')
            ? Number.parseInt(durationToken ?? 'NaN', 10)
            : Number.parseFloat(value[1] as string) * (value[2] === 's' ? 1000 : 1),
        }),
      ),
    ),
  )

  it('defines one duration token and uses it', () => {
    expect(durationToken).toBeDefined()
    expect(durations.length).toBeGreaterThan(0)
  })

  it.each(durations.map((entry) => [`${entry.name}: ${entry.milliseconds}ms`, entry] as const))(
    '%s is inside the 200ms cap',
    (_label, entry) => {
      expect(entry.milliseconds).toBeLessThanOrEqual(200)
    },
  )

  it('runs no animation at all, so nothing plays on page load', () => {
    for (const [name, source] of stylesheets) {
      expect(source, `${name} declares @keyframes`).not.toMatch(/@keyframes/)
      // The reduced-motion block names animation-duration and animation-iteration-count to
      // neutralise anything a future rule adds; a real `animation:` shorthand is what would
      // start something playing.
      expect(source, `${name} starts an animation`).not.toMatch(/(?:^|;|\{)\s*animation:/m)
    }
  })

  it('switches every transition off under prefers-reduced-motion', () => {
    const block = /@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n\}/.exec(globals)?.[1]
    expect(block, 'globals.css has no prefers-reduced-motion block').toBeDefined()
    // The universal selector with its pseudo-elements is what makes this cover every transition
    // in every stylesheet, including the chevron on .link-cta::after.
    expect(block).toContain('*,')
    expect(block).toContain('*::before')
    expect(block).toContain('*::after')
    expect(block).toContain('transition-duration: 0.01ms !important')
    expect(block).toContain('animation-duration: 0.01ms !important')
    expect(block).toContain('scroll-behavior: auto !important')
  })
})

/**
 * The page is centred on one axis (the defect this replaced: a text column pinned to the left of
 * a much wider band, with every pixel of slack on its right).
 */
describe('the text column is centred, not pinned left', () => {
  const sections = readStylesheet('sections.css')

  it('centres the text column, the section header and the hero on the same measure', () => {
    const body = ruleBody(sections, '.section__column,\n.section__header,\n.hero__content')
    expect(body, 'the centred text column rule is missing from sections.css').not.toBeNull()
    expect(declaration(body!, 'max-width')).toBe('var(--layout-prose-width)')
    expect(declaration(body!, 'margin-inline')).toBe('auto')
  })

  it('keeps the wide band close enough to the text column to look deliberate', () => {
    const wide = Number.parseFloat(/--layout-max-width:\s*([\d.]+)rem/.exec(tokens)?.[1] ?? 'NaN')
    const text = Number.parseFloat(/--layout-prose-width:\s*([\d.]+)rem/.exec(tokens)?.[1] ?? 'NaN')
    expect(wide).toBeGreaterThan(text)
    // The band a card grid breaks out to is at most 20rem wider than the text column. At 68rem
    // against a 36rem column the page read as though it had slipped sideways.
    expect(wide - text).toBeLessThanOrEqual(20)
  })
})

describe('the footer carries the white knockout mark', () => {
  it('renders the knockout artwork on navy, decoratively', async () => {
    const { container } = render(
      <SiteFooter
        navigationLabel="About this site"
        note="A site run by the team's coaches."
        utilityLinks={[]}
        wordmark="WFB Debate"
      />,
      { container: document.body },
    )
    const footer = screen.getByRole('contentinfo')
    const mark = footer.querySelector('img')

    expect(mark?.getAttribute('src')).toContain('wfb-mark-white-knockout')
    // Decorative: it repeats the header's link home, so a screen reader skips it and the team
    // name is carried by the wordmark text beside it.
    expect(mark?.getAttribute('alt')).toBe('')
    expect(within(footer).getByText('WFB Debate')).toBeDefined()

    const violations = await findAccessibilityViolations(container)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })
})

describe('an action inside an inverse section', () => {
  it('renders and has no WCAG 2.1 AA violation', async () => {
    const { container } = render(
      <main>
        <Section id="session" title="Parent information session" tone="inverse">
          <p>One line of copy.</p>
          <Button href="/faq/" variant="secondary">
            Read the questions parents ask
          </Button>
        </Section>
      </main>,
    )
    expect(screen.getByRole('link', { name: 'Read the questions parents ask' })).toBeDefined()
    const violations = await findAccessibilityViolations(container)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })
})
