/** Types for export-fingerprint.mjs, which stays plain JavaScript so node runs it with no build step. */

export declare const SITE_DIRECTORY: string
export declare const EXPORT_DIRECTORY: string
export declare const BUILD_RECORD_PATH: string
export declare const BUILD_COMMAND: string

export declare class ExportFreshnessError extends Error {}

export interface SourceFingerprint {
  digest: string
  files: Record<string, string>
  variables: Record<string, string>
}

export interface ExportFingerprint {
  digest: string
  fileCount: number
}

export declare function sourceFingerprint(
  environment?: Record<string, string | undefined>,
  siteDirectory?: string,
): SourceFingerprint

export declare function exportFingerprint(exportDirectory?: string): ExportFingerprint

export declare function differences(
  before: Record<string, string>,
  after: Record<string, string>,
): string[]

export declare function assertFreshExport(options?: {
  environment?: Record<string, string | undefined>
  siteDirectory?: string
  exportDirectory?: string
  recordPath?: string
}): { builtAt: string; fileCount: number }
