#!/usr/bin/env tsx
/**
 * Round-trip debate .docx files through CardMirror's public API.
 *
 * Operator tooling for the CardMirror evaluation spike
 * (plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml). It is never run
 * in CI, is not in the uv workspace, and no Python package depends on it. Its output is
 * read by `scripts/compare_docx_roundtrip.py`, which produces the aggregate summary that
 * goes into docs/architecture/cardmirror-evaluation.md.
 *
 * For each input file it calls `fromDocx` and then `toDocx` at a pinned CardMirror
 * commit, writes the re-exported file next to a manifest, and records import/export
 * timings plus the node and mark counts of the imported ProseMirror document.
 *
 * Usage (see README.md for the full setup):
 *
 *   npm install
 *   npm run roundtrip -- --input ~/debate-files --output ~/cardmirror-roundtrip-out
 *
 * `--input` is a directory whose immediate subdirectories name the file categories
 * (team, caselist, caselist-non-verbatim, caselist-wiki, camp). Files sitting directly
 * in the input directory take `--category` (default "unknown").
 *
 * The harness refuses to write into a git working tree: real team, caselist and camp
 * files and their round-tripped output must never land in the repository.
 */

import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const HERE = path.dirname(new URL(import.meta.url).pathname);

function parseArguments(argv) {
  const options = {
    input: null,
    output: null,
    manifest: null,
    category: 'unknown',
    cardmirror: process.env.CARDMIRROR_DIR ?? path.join(HERE, 'node_modules', 'cardmirror'),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    const value = argv[index + 1];
    switch (flag) {
      case '--input':
      case '--output':
      case '--manifest':
      case '--category':
      case '--cardmirror':
        if (value === undefined) throw new Error(`${flag} needs a value`);
        options[flag.slice(2)] = value;
        index += 1;
        break;
      case '--help':
      case '-h':
        console.log(
          'Usage: npm run roundtrip -- --input <dir> --output <dir> [--manifest <path>] ' +
            '[--category <name>] [--cardmirror <dir>]',
        );
        process.exit(0);
        break;
      default:
        throw new Error(`unknown argument: ${flag}`);
    }
  }
  if (!options.input) throw new Error('--input is required');
  if (!options.output) throw new Error('--output is required');
  options.input = path.resolve(options.input);
  options.output = path.resolve(options.output);
  options.cardmirror = path.resolve(options.cardmirror);
  options.manifest = path.resolve(options.manifest ?? path.join(options.output, 'roundtrip-manifest.json'));
  return options;
}

/** Walk up from `directory` looking for a `.git` entry. */
async function findGitRoot(directory) {
  let current = directory;
  for (;;) {
    try {
      await stat(path.join(current, '.git'));
      return current;
    } catch {
      const parent = path.dirname(current);
      if (parent === current) return null;
      current = parent;
    }
  }
}

async function refuseIfInsideGitRepository(directory) {
  const gitRoot = await findGitRoot(directory);
  if (gitRoot !== null) {
    throw new Error(
      `refusing to write round-tripped debate files into the git working tree at ${gitRoot}. ` +
        'Real team, caselist and camp files and their round-tripped output must stay outside ' +
        'the repository — choose an --output directory somewhere else.',
    );
  }
}

async function collectInputs(inputDirectory, defaultCategory) {
  const entries = await readdir(inputDirectory, { withFileTypes: true });
  const inputs = [];
  for (const entry of entries) {
    const entryPath = path.join(inputDirectory, entry.name);
    if (entry.isDirectory()) {
      for (const nested of await collectDocxFiles(entryPath)) {
        inputs.push({ filePath: nested, fileCategory: entry.name });
      }
    } else if (isDocx(entry.name)) {
      inputs.push({ filePath: entryPath, fileCategory: defaultCategory });
    }
  }
  inputs.sort((left, right) => left.filePath.localeCompare(right.filePath));
  return inputs;
}

async function collectDocxFiles(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...(await collectDocxFiles(entryPath)));
    else if (isDocx(entry.name)) found.push(entryPath);
  }
  return found;
}

function isDocx(name) {
  return name.toLowerCase().endsWith('.docx') && !name.startsWith('~$');
}

/** The CardMirror commit npm actually installed, read from the lockfile it writes. */
async function resolveCardMirrorCommit(cardmirrorDirectory) {
  const lockPath = path.join(HERE, 'node_modules', '.package-lock.json');
  try {
    const lock = JSON.parse(await readFile(lockPath, 'utf8'));
    const resolved = lock.packages?.['node_modules/cardmirror']?.resolved ?? '';
    const commit = resolved.split('#')[1];
    if (commit) return commit;
  } catch {
    // Falls through: a --cardmirror checkout has no lockfile entry here.
  }
  try {
    const head = await readFile(path.join(cardmirrorDirectory, '.git', 'HEAD'), 'utf8');
    return head.trim();
  } catch {
    return null;
  }
}

function summarizeDocument(doc) {
  const nodeCounts = {};
  const markCounts = {};
  let textLength = 0;
  doc.descendants((node) => {
    nodeCounts[node.type.name] = (nodeCounts[node.type.name] ?? 0) + 1;
    if (node.isText) {
      textLength += node.text?.length ?? 0;
      for (const mark of node.marks) {
        markCounts[mark.type.name] = (markCounts[mark.type.name] ?? 0) + 1;
      }
    }
    return true;
  });
  return { nodeCounts, markCounts, textLength };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  await refuseIfInsideGitRepository(options.output);

  const entryPoint = pathToFileURL(path.join(options.cardmirror, 'src', 'index.ts')).href;
  const { fromDocx, toDocx } = await import(entryPoint);
  const cardmirrorCommit = await resolveCardMirrorCommit(options.cardmirror);
  const cardmirrorVersion = JSON.parse(
    await readFile(path.join(options.cardmirror, 'package.json'), 'utf8'),
  ).version;

  const inputs = await collectInputs(options.input, options.category);
  if (inputs.length === 0) throw new Error(`no .docx files found under ${options.input}`);
  console.error(`CardMirror ${cardmirrorVersion} (${cardmirrorCommit ?? 'unknown commit'})`);
  console.error(`Round-tripping ${inputs.length} file(s) from ${options.input}`);

  const files = [];
  for (const { filePath, fileCategory } of inputs) {
    const originalBytes = await readFile(filePath);
    const sha256Prefix = createHash('sha256').update(originalBytes).digest('hex').slice(0, 8);
    const outputDirectory = path.join(options.output, fileCategory);
    await mkdir(outputDirectory, { recursive: true });
    const roundtrippedPath = path.join(outputDirectory, `${sha256Prefix}.roundtripped.docx`);

    try {
      const importStarted = Date.now();
      const doc = await fromDocx(
        new Uint8Array(originalBytes.buffer, originalBytes.byteOffset, originalBytes.byteLength),
      );
      const importMs = Date.now() - importStarted;
      const exportStarted = Date.now();
      const exportedBytes = await toDocx(doc);
      const exportMs = Date.now() - exportStarted;
      await writeFile(roundtrippedPath, exportedBytes);
      files.push({
        status: 'ok',
        fileCategory,
        sha256Prefix,
        originalPath: filePath,
        roundtrippedPath,
        bytesIn: originalBytes.byteLength,
        bytesOut: exportedBytes.length,
        importMs,
        exportMs,
        ...summarizeDocument(doc),
      });
      console.error(`  ok       ${fileCategory}/${sha256Prefix} (${importMs}ms in, ${exportMs}ms out)`);
    } catch (error) {
      files.push({
        status: 'failed',
        fileCategory,
        sha256Prefix,
        originalPath: filePath,
        error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      });
      console.error(`  FAILED   ${fileCategory}/${sha256Prefix}: ${error}`);
    }
  }

  const manifest = {
    generatedAt: new Date().toISOString(),
    cardmirrorVersion,
    cardmirrorCommit,
    inputDirectory: options.input,
    totals: {
      files: files.length,
      ok: files.filter((file) => file.status === 'ok').length,
      failed: files.filter((file) => file.status === 'failed').length,
    },
    files,
  };
  await mkdir(path.dirname(options.manifest), { recursive: true });
  await writeFile(options.manifest, `${JSON.stringify(manifest, null, 2)}\n`);
  console.error(
    `${manifest.totals.ok} ok, ${manifest.totals.failed} failed. Manifest: ${options.manifest}`,
  );
  return manifest.totals.failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(`roundtrip.mjs: ${error instanceof Error ? error.message : error}`);
    process.exit(2);
  },
);
