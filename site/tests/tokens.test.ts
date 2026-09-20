import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { AA_LARGE_TEXT, AA_NORMAL_TEXT, contrastRatio } from './contrast'

/**
 * The design tokens are the single source of the site's colour, so these assertions read the
 * real file rather than a copy of the values. They cover WCAG 2.1 success criterion 1.4.3
 * (contrast, minimum) for text and 1.4.11 (non-text contrast) for the focus ring.
 *
 * axe-core cannot check contrast in jsdom, which has no layout engine, so this is where the
 * contrast requirement in the task spec is actually enforced.
 */

const STYLES_DIRECTORY = join(process.cwd(), 'src/styles')
const TOKENS_PATH = join(STYLES_DIRECTORY, 'tokens.css')
const tokensSource = readFileSync(TOKENS_PATH, 'utf8')

/** Every stylesheet the site ships, so a new one cannot escape the rules below by existing. */
const stylesheets = readdirSync(STYLES_DIRECTORY)
  .filter((entry) => entry.endsWith('.css'))
  .sort()
  .map((entry) => [entry, readFileSync(join(STYLES_DIRECTORY, entry), 'utf8')] as const)

/** Resolves a custom property from tokens.css, following one level of `var(--other)` aliasing. */
function token(name: string, depth = 0): string {
  const match = new RegExp(`^\\s*--${name}:\\s*([^;]+);`, 'm').exec(tokensSource)
  if (!match?.[1]) {
    throw new Error(`Token --${name} is not defined in src/styles/tokens.css`)
  }
  const value = match[1].trim()
  const alias = /^var\(--([\w-]+)\)$/.exec(value)
  if (alias?.[1]) {
    if (depth > 5) {
      throw new Error(`Token --${name} aliases in a loop`)
    }
    return token(alias[1], depth + 1)
  }
  return value
}

describe('brand palette', () => {
  it('holds the colours sampled from the team deck template, unchanged', () => {
    expect(token('color-brand-navy')).toBe('#2e2578')
    expect(token('color-brand-accent')).toBe('#4a41a8')
    expect(token('color-brand-light')).toBe('#b9b4e8')
    expect(token('color-brand-warm')).toBe('#b36b00')
    expect(token('color-text-body')).toBe('#55596b')
    expect(token('color-text-muted')).toBe('#74798e')
    expect(token('color-surface-panel')).toBe('#eeeef7')
  })

  it('loads no remote font', () => {
    expect(tokensSource).not.toMatch(/@import\s+url\(/)
    expect(token('font-family-base')).toMatch(/^Arial,/)
  })
})

/**
 * The contrast table in the header comment of tokens.css, recomputed row by row.
 *
 * The table is the documentation a reviewer reads, so it is also the thing the test checks:
 * every row names two tokens, a measured ratio and the threshold the pair is allowed to be used
 * at. A pair added to the design without being measured, a number left behind after a colour
 * changed, or a large-text-only pair quietly relabelled AA all fail here.
 */
const TABLE_ROW =
  /^\s*\*\s+(\d+\.\d{2})\s+(AA|AA-large)\s+--([\w-]+)\s+on\s+--([\w-]+)\s*$/gm

interface ContrastRow {
  stated: number
  verdict: 'AA' | 'AA-large'
  foreground: string
  background: string
}

const contrastTable: ContrastRow[] = [...tokensSource.matchAll(TABLE_ROW)].map((match) => ({
  stated: Number.parseFloat(match[1] as string),
  verdict: match[2] as 'AA' | 'AA-large',
  foreground: match[3] as string,
  background: match[4] as string,
}))

describe('the contrast table in tokens.css', () => {
  it('has a row for every pair the site paints', () => {
    // A floor rather than an exact count: adding a measured pair should not fail the suite,
    // deleting the table wholesale should.
    expect(contrastTable.length).toBeGreaterThanOrEqual(18)
  })

  it.each(contrastTable.map((row) => [`${row.foreground} on ${row.background}`, row] as const))(
    '%s is measured correctly',
    (_name, row) => {
      const measured = contrastRatio(token(row.foreground), token(row.background))
      expect(
        Number.parseFloat(measured.toFixed(2)),
        `the table says ${row.stated}, the tokens measure ${measured.toFixed(2)}`,
      ).toBe(row.stated)
    },
  )

  it.each(contrastTable.map((row) => [`${row.foreground} on ${row.background}`, row] as const))(
    '%s meets the threshold its verdict claims',
    (_name, row) => {
      const measured = contrastRatio(token(row.foreground), token(row.background))
      if (row.verdict === 'AA') {
        expect(measured).toBeGreaterThanOrEqual(AA_NORMAL_TEXT)
      } else {
        expect(measured).toBeGreaterThanOrEqual(AA_LARGE_TEXT)
        expect(measured, 'a pair that clears 4.5:1 should not be labelled AA-large').toBeLessThan(
          AA_NORMAL_TEXT,
        )
      }
    },
  )
})

describe('normal text meets WCAG 2.1 AA (4.5:1)', () => {
  const surface = () => token('color-surface')
  const panel = () => token('color-surface-panel')
  const navy = () => token('color-surface-inverse')

  const pairs: Array<[string, () => string, () => string]> = [
    ['body text on white', () => token('color-text-body'), surface],
    ['body text on the panel tint', () => token('color-text-body'), panel],
    ['headings on white', () => token('color-text-heading'), surface],
    ['headings on the panel tint', () => token('color-text-heading'), panel],
    ['links on white', () => token('color-link'), surface],
    ['links on the panel tint', () => token('color-link'), panel],
    ['hovered links on white', () => token('color-link-hover'), surface],
    ['inverse text on navy', () => token('color-text-inverse'), navy],
    ['inverse links on navy', () => token('color-link-inverse'), navy],
    // The design pass puts a white action button inside the navy October 1 panel; its label is
    // navy on white, and the panel tint is used there as a rule and as a card surface.
    ['the navy label of a white button', () => token('color-brand-navy'), surface],
    ['the panel tint used on navy', () => token('color-surface-panel'), navy],
  ]

  it.each(pairs)('%s', (_name, foreground, background) => {
    expect(contrastRatio(foreground(), background())).toBeGreaterThanOrEqual(AA_NORMAL_TEXT)
  })
})

describe('the focus ring meets WCAG 2.1 AA non-text contrast (3:1)', () => {
  it('is visible on white', () => {
    expect(contrastRatio(token('color-focus-ring'), token('color-surface'))).toBeGreaterThanOrEqual(
      AA_LARGE_TEXT,
    )
  })

  it('is visible on the panel tint', () => {
    expect(
      contrastRatio(token('color-focus-ring'), token('color-surface-panel')),
    ).toBeGreaterThanOrEqual(AA_LARGE_TEXT)
  })

  it('is visible on navy', () => {
    expect(
      contrastRatio(token('color-focus-ring-inverse'), token('color-surface-inverse')),
    ).toBeGreaterThanOrEqual(AA_LARGE_TEXT)
  })

  /**
   * v1-e36-t06 acceptance criterion 3: the design pass may add surfaces, but not move the ring.
   * These are the values v1-e36-t03 set.
   */
  it('is the ring v1-e36-t03 set, not a new one', () => {
    expect(token('color-focus-ring')).toBe(token('color-brand-navy'))
    expect(token('color-focus-ring-inverse')).toBe(token('color-brand-light'))
    const globals = readFileSync(join(STYLES_DIRECTORY, 'globals.css'), 'utf8')
    expect(globals).toContain('outline: 3px solid var(--color-focus-ring)')
    expect(globals).toContain('outline-offset: 2px')
  })
})

/**
 * Two brand colours fall short of 4.5:1. The team keeps them rather than adjusting the brand, so
 * these assertions pin down the restriction the tokens file documents: they clear the 3:1 that
 * large text and non-text indicators need, and they do not clear 4.5:1, which is why no rule in
 * the stylesheets may use them for small text.
 */
describe('muted grey and the warm accent are restricted to large text and non-text use', () => {
  const restricted: Array<[string, () => string, () => string]> = [
    ['muted grey on white', () => token('color-text-muted'), () => token('color-surface')],
    ['muted grey on the panel tint', () => token('color-text-muted'), () => token('color-surface-panel')],
    ['warm accent on white', () => token('color-brand-warm'), () => token('color-surface')],
    ['warm accent on the panel tint', () => token('color-brand-warm'), () => token('color-surface-panel')],
  ]

  it.each(restricted)('%s clears 3:1 but not 4.5:1', (_name, foreground, background) => {
    const ratio = contrastRatio(foreground(), background())
    expect(ratio).toBeGreaterThanOrEqual(AA_LARGE_TEXT)
    expect(ratio).toBeLessThan(AA_NORMAL_TEXT)
  })

  it.each(stylesheets)(
    '%s uses them only at the large-text size or as a border',
    (name, source) => {
      // `color:` is the property that paints text; `border`, `box-shadow` and friends are
      // non-text and only need 3:1.
      const textUses = source.match(/(?<!-)color:\s*var\(--color-(?:text-muted|brand-warm)\)/g)
      expect(textUses, `${name} paints small text with a restricted brand colour`).toBeNull()
    },
  )

  /**
   * The warm accent misses the non-text threshold on navy by too little to trust (3.04:1), so
   * the pass keeps it off navy entirely. Asserted because a rule that fails only on one
   * background is exactly the kind of thing a later edit reintroduces by accident.
   */
  it('keeps the warm accent off navy, where it measures only 3.04:1', () => {
    expect(
      contrastRatio(token('color-brand-warm'), token('color-surface-inverse')),
    ).toBeLessThan(3.1)
    for (const [name, source] of stylesheets) {
      const insideInverse = source.match(/--inverse\b[^{]*\{[^}]*--color-brand-warm[^}]*\}/g)
      expect(insideInverse, `${name} uses the warm accent on an inverse surface`).toBeNull()
    }
  })
})

/**
 * The layout kit v1-e36-t06 added: the scale above the heading sizes, the rhythm tokens that
 * control how much air the page has, and the measure body copy is set to.
 */
describe('the layout kit', () => {
  it('has a display size above heading 1 and a hero lead above the body lead', () => {
    expect(token('font-size-display')).toMatch(/^clamp\(/)
    expect(token('font-size-lead-hero')).toMatch(/^clamp\(/)
    // The floor of the fluid display size is already larger than heading 1 on a phone.
    expect(token('font-size-display')).toContain('2.25rem')
    expect(token('font-size-heading-1')).toBe('2.25rem')
  })

  it('sets section padding for a phone and again from tablet width up', () => {
    expect(token('space-section-block')).toBe(token('space-7'))
    const desktopBlock = /@media \(min-width: 48rem\)[\s\S]*--space-section-block:\s*var\(--space-9\)/
    expect(tokensSource).toMatch(desktopBlock)
  })

  it('sets the measure at 60 to 75 characters of Arial at the body size', () => {
    const measureRem = Number.parseFloat(token('layout-prose-width'))
    // Arial averages about 0.5em per character in English prose, so characters = rem * 2.
    const characters = measureRem * 2
    expect(characters).toBeGreaterThanOrEqual(60)
    expect(characters).toBeLessThanOrEqual(75)
  })

  it('caps the one motion duration at the 200ms the task spec allows', () => {
    expect(Number.parseInt(token('duration-transition'), 10)).toBeLessThanOrEqual(200)
  })
})
