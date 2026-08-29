#!/usr/bin/env node
// This repo lives under ~/Documents, which macOS's "Desktop & Documents
// Folders" iCloud sync watches — node_modules is thousands of files
// churning during every `npm install`, and racing that against iCloud's
// sync daemon has repeatedly corrupted it (partial installs, "node_modules
// 2" conflict-duplicate directories). Relocating the real directory to
// ~/Library/Caches (never iCloud-synced) and leaving a symlink in its
// place fixes it structurally instead of needing a fragile per-directory
// "ignore this" tag reapplied by hand after every reinstall.
//
// Runs automatically as this package's `postinstall` — npm always installs
// into a real local node_modules (it doesn't write through a pre-existing
// symlink), so this moves it out immediately afterward, every time.
// Idempotent: a no-op once node_modules is already the symlink.

const fs = require("fs");
const os = require("os");
const path = require("path");

const projectNodeModules = path.join(__dirname, "..", "node_modules");
// The real directory's own name must stay literally "node_modules" — Node's
// ESM resolver walks up the *real* (post-symlink) path looking for a
// directory with that exact name to find sibling packages (e.g. vite
// resolving esbuild). Naming it anything else (e.g. "frontend-node_modules")
// silently breaks nested package resolution even though the symlink itself
// still works. Only the *parent* directory ("frontend") distinguishes it
// from any other project's relocated node_modules under the same cache root.
const cacheDir = path.join(os.homedir(), "Library", "Caches", "labpilot", "frontend", "node_modules");

const stat = fs.lstatSync(projectNodeModules);
if (stat.isSymbolicLink()) {
  process.exit(0);
}

fs.mkdirSync(path.dirname(cacheDir), { recursive: true });
fs.rmSync(cacheDir, { recursive: true, force: true });
fs.renameSync(projectNodeModules, cacheDir);
fs.symlinkSync(cacheDir, projectNodeModules);
console.log(`[relocate-node-modules] moved node_modules out of iCloud sync -> ${cacheDir}`);
