/** Tailwind config for landing/index.html.
 *
 * The page used the Play CDN (cdn.tailwindcss.com), which compiles Tailwind in
 * the browser, makes a third-party request on every visit, and prints a
 * production warning. This config lets the CSS be built once and self-hosted.
 *
 * Rebuild from the repo root:
 *   npx tailwindcss@3.4.17 -c landing/tailwind.config.js \
 *       -i landing/tailwind.input.css -o landing/tailwind.css --minify
 * The two CDN plugins in the old URL (forms, container-queries) are unused by
 * the page, so they are not included (verified: no @container or form elements).
 */
module.exports = {
  darkMode: 'class',
  content: ['landing/index.html'],
  theme: { extend: {
    colors: { midnight:'#070b10',darkslate:'#0d131b',cardbg:'#111823',amberGlow:'#f59e0b',amberBright:'#fbbf24',cyberBlue:'#38bdf8',neonViolet:'#818cf8',accentPink:'#f43f5e' },
    fontFamily: { sans:['Inter','system-ui','-apple-system','BlinkMacSystemFont','Segoe UI','Roboto','sans-serif'], mono:['JetBrains Mono','Fira Code','SFMono-Regular','Menlo','Monaco','Consolas','monospace'], serif:['Newsreader','Playfair Display','Georgia','serif'] },
    boxShadow: { 'amber-glow':'0 0 45px -10px rgba(245,158,11,0.35)','cyber-glow':'0 0 50px -12px rgba(56,189,248,0.25)','neon-glow':'0 0 35px -8px rgba(129,140,248,0.3)' }
  } },
};
