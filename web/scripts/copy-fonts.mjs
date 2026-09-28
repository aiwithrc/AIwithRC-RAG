// Copies the Geist variable fonts from the `geist` npm package into public/fonts,
// so the app never loads fonts from Google at runtime. Run with `npm run fonts`.
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'node_modules', 'geist');
const out = join(root, 'public', 'fonts');
mkdirSync(out, { recursive: true });

for (const [from, to] of [
  ['dist/fonts/geist-sans/Geist-Variable.woff2', 'Geist-Variable.woff2'],
  ['dist/fonts/geist-mono/GeistMono-Variable.woff2', 'GeistMono-Variable.woff2'],
  ['LICENSE.txt', 'OFL-LICENSE.txt'],
]) {
  copyFileSync(join(src, from), join(out, to));
  console.log('copied', to);
}
