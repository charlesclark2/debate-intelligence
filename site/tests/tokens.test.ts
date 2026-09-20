import { readFileSync } from 'node:fs'
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

const TOKENS_PATH = join(process.cwd(), 'src/styles/tokens.css')
const tokensSource = readFileSync(TOKENS_PATH, 'utf8')

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

  it('is visible on navy', () => {
    expect(
      contrastRatio(token('color-focus-ring-inverse'), token('color-surface-inverse')),
    ).toBeGreaterThanOrEqual(AA_LARGE_TEXT)
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

  it('is used only at the large-text size or as a border in the stylesheets', () => {
    const layout = readFileSync(join(process.cwd(), 'src/styles/layout.css'), 'utf8')
    const components = readFileSync(join(process.cwd(), 'src/styles/components.css'), 'utf8')
    const globals = readFileSync(join(process.cwd(), 'src/styles/globals.css'), 'utf8')

    for (const [name, source] of [
      ['layout.css', layout],
      ['components.css', components],
      ['globals.css', globals],
    ] as const) {
      // `color:` is the property that paints text; `border`, `box-shadow` and friends are
      // non-text and only need 3:1.
      const textUses = source.match(/(?<!-)color:\s*var\(--color-(?:text-muted|brand-warm)\)/g)
      expect(textUses, `${name} paints small text with a restricted brand colour`).toBeNull()
    }
  })
})
