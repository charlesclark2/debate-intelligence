import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import matter from 'gray-matter'
import { z } from 'zod'

import { ContentValidationError, defaultContentDirectory } from './content'

/**
 * The media-consent manifest: who the site may name, and which images it may publish.
 *
 * It implements the consent rules in docs/policies/website-publishing.md (Students 1-2, Photos
 * and media consent 4, Consent renewal and the start-of-season check). Consent expires at the end
 * of each season, so every entry carries the season it was granted for and the date a coach last
 * confirmed it with the activities office. Nothing here identifies a student beyond the name the
 * site already prints: `consentReference` is opaque and the mapping lives with the activities
 * office, never in this repository.
 */

export const MEDIA_CONSENT_FILE = 'content/media-consent.yaml'

/** A season runs 1 August to 31 July and is written `2026-27`. */
export const SEASON_PATTERN = /^\d{4}-\d{2}$/

const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, 'must be an ISO date, for example 2026-09-18')

const season = z.string().regex(SEASON_PATTERN, 'must look like 2026-27')

export const consentedStudentSchema = z.object({
  publishedName: z.string().min(1),
  publishedForm: z.enum(['full-name-and-class-year', 'first-name-only']),
  graduationYear: z.number().int().optional(),
  consentReference: z.string().min(1),
  season,
  dateChecked: isoDate,
})

export const consentedImageSchema = z.object({
  path: z.string().min(1),
  consentReference: z.string().min(1),
  depicts: z.string().min(1),
  season,
  dateChecked: isoDate,
})

export const nonPersonImageSchema = z.object({
  path: z.string().min(1),
  reason: z.string().min(1),
})

export const mediaConsentSchema = z.object({
  season,
  students: z.array(consentedStudentSchema),
  images: z.array(consentedImageSchema),
  nonPersonImages: z.array(nonPersonImageSchema),
  /**
   * Capitalised phrases the site is allowed to print: school names, organisations, places and the
   * ordinary words that sit beside them. Phrases, not words, so that reviewing "Blue Valley West
   * High School" does not leave Blue, Valley and West permitted on their own for ever
   * (the v1-e36-t07 review). See `unreviewedNames` in src/lib/publishing-policy.ts.
   */
  permittedNamePhrases: z.array(z.string().min(1)),
})

export type ConsentedStudent = z.infer<typeof consentedStudentSchema>
export type ConsentedImage = z.infer<typeof consentedImageSchema>
export type MediaConsent = z.infer<typeof mediaConsentSchema>

/** 1 August of the first year in the label, the day the season's consent forms start. */
export function seasonStart(label: string): Date {
  const startYear = Number.parseInt(label.slice(0, 4), 10)
  return new Date(Date.UTC(startYear, 7, 1))
}

/**
 * True when a coach last confirmed the entry before the current season began, which means the
 * start-of-season check has not been run on it yet. A warning rather than a failure: the entry
 * may well still be good, but nobody has looked.
 */
export function isStale(entry: { season: string; dateChecked: string }, currentSeason: string): boolean {
  return entry.season !== currentSeason || new Date(entry.dateChecked) < seasonStart(currentSeason)
}

export function loadMediaConsent(contentDirectory: string = defaultContentDirectory()): MediaConsent {
  const absolutePath = join(contentDirectory, 'media-consent.yaml')
  if (!existsSync(absolutePath)) {
    throw new ContentValidationError(MEDIA_CONSENT_FILE, 'file is missing')
  }
  // Read through gray-matter's YAML parser, the same one the pages and site.yaml use.
  const parsed = matter(`---\n${readFileSync(absolutePath, 'utf8')}\n---\n`)
  const result = mediaConsentSchema.safeParse(parsed.data)
  if (!result.success) {
    const detail = result.error.issues
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('; ')
    throw new ContentValidationError(MEDIA_CONSENT_FILE, `invalid manifest (${detail})`)
  }
  return result.data
}
