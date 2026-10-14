import { cp, mkdir, rm, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const webDir = resolve(projectRoot, 'www');
const requiredFiles = ['index.html', 'config.js'];

for (const file of requiredFiles) {
  try {
    await stat(resolve(projectRoot, file));
  } catch {
    console.error(`Build stopped: required app file is missing: ${file}`);
    process.exit(1);
  }
}

// Copy only the browser app into Capacitor's web directory. Server-side
// pipeline files, Supabase admin credentials, and GitHub secrets are not bundled.
await rm(webDir, { recursive: true, force: true });
await mkdir(webDir, { recursive: true });
for (const file of requiredFiles) {
  await cp(resolve(projectRoot, file), resolve(webDir, file));
}

console.log('Android web bundle ready: www/index.html and www/config.js');
console.log('Only the Supabase URL and publishable key are client-side; do not add server secrets here.');
