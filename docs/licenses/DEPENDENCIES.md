# Bundled dependencies and licences

Third-party material vendored into this repository, with the licence it ships
under. Product dependencies declared in `pyproject.toml` are not listed here;
this file covers files committed under the repo tree.

## Install and licence PDF fonts (SIL OFL 1.1)

`landing/tancat-pro-install-and-licence.pdf` is rendered from
`docs/implementation/tancat-pro-install-and-licence.html`. The document loads its
fonts from `docs/implementation/fonts/` by relative path, so the render needs no
network and never falls back to a font installed on the build machine. The
rebuilt PDF embeds only the fonts below.

| Bundled file | Face | Copyright | Licence |
|--------------|------|-----------|---------|
| `inter-regular.woff2` | Inter Regular (400) | Copyright (c) 2016 The Inter Project Authors | OFL-1.1 |
| `inter-bold.woff2` | Inter Bold (700) | Copyright (c) 2016 The Inter Project Authors | OFL-1.1 |
| `inter-italic.woff2` | Inter Italic (400) | Copyright (c) 2016 The Inter Project Authors | OFL-1.1 |
| `jetbrains-mono-regular.woff2` | JetBrains Mono Regular (400) | Copyright 2020 The JetBrains Mono Project Authors | OFL-1.1 |

All four are unmodified release files:

- Inter: <https://github.com/rsms/inter> (`docs/font-files/`)
- JetBrains Mono: <https://github.com/JetBrains/JetBrainsMono> (`fonts/webfonts/`)

Recorded SHA-256, so a silent swap is visible in review:

| File | SHA-256 |
|------|---------|
| `inter-regular.woff2` | `e06f6b1bc553aaea4e4668023ed0ab0a147129c3107f511bc7d03d361b0ae085` |
| `inter-bold.woff2` | `fa888127b6da015b65569f0351f3b5c391ad928904951f1c20e9f8462a8d95ea` |
| `inter-italic.woff2` | `2d078cb3bc8f934740d53b39dd23b0678f2f97477e49ec785dd9d8acd8b96bfc` |
| `jetbrains-mono-regular.woff2` | `f1a7a03672cdd494ce0d5543fac6e4360fe22403c6de297fdc2e55a815f7baff` |

The full SIL Open Font License, Version 1.1, text and both copyright notices sit
in `docs/implementation/fonts/OFL.txt`, next to the fonts, as OFL requires.

Why these are bundled: the PDF used to be rendered on Windows and embedded the
proprietary Microsoft faces Segoe UI and Consolas, because the source HTML asked
for them (`"Segoe UI", Arial, sans-serif` / `Consolas, "Courier New"`) and
headless Chromium resolved them from the host. The HTML now asks only for the
bundled faces, and `make_landing_assets.py` waits for `document.fonts.ready`
before printing, so the embedded set is the bundled set.

Not bundled: Newsreader. The landing page uses it for serif accents, but the
install and licence document has no serif text, so bundling it would add licence
surface and glyphs the PDF never embeds. Add it here if the document ever gains
a serif face.

To change a font, replace the file in `docs/implementation/fonts/`, update the
table and hash above, then rerun
`python scripts/maintenance/make_landing_assets.py` so the rebuilt PDF and
`landing/asset-sources.json` (which now lists these font files as PDF sources)
move together.
