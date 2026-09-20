/**
 * WCAG 2.1 contrast maths, used by tests/tokens.test.ts.
 * Relative luminance and contrast ratio as defined in WCAG 2.1 (sRGB).
 */

export function parseHexColor(value: string): [number, number, number] {
  const hex = value.trim().replace(/^#/, '')
  const full =
    hex.length === 3
      ? hex
          .split('')
          .map((character) => character + character)
          .join('')
      : hex
  if (!/^[0-9a-fA-F]{6}$/.test(full)) {
    throw new Error(`Not a hex colour: ${value}`)
  }
  const channels = [0, 2, 4].map((offset) => Number.parseInt(full.slice(offset, offset + 2), 16))
  return [channels[0] as number, channels[1] as number, channels[2] as number]
}

function channelLuminance(channel: number): number {
  const proportion = channel / 255
  return proportion <= 0.03928
    ? proportion / 12.92
    : Math.pow((proportion + 0.055) / 1.055, 2.4)
}

export function relativeLuminance(color: string): number {
  const [red, green, blue] = parseHexColor(color)
  return (
    0.2126 * channelLuminance(red) +
    0.7152 * channelLuminance(green) +
    0.0722 * channelLuminance(blue)
  )
}

export function contrastRatio(foreground: string, background: string): number {
  const first = relativeLuminance(foreground)
  const second = relativeLuminance(background)
  const lighter = Math.max(first, second)
  const darker = Math.min(first, second)
  return (lighter + 0.05) / (darker + 0.05)
}

/** WCAG 2.1 AA: 4.5:1 for normal text, 3:1 for large text and for non-text indicators. */
export const AA_NORMAL_TEXT = 4.5
export const AA_LARGE_TEXT = 3
