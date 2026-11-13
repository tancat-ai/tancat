# Fonts served by the landing pages

The landing pages load three families from `landing/fonts.css`, and the files in
this directory are served from this site. Nothing is requested from Google at page
load, so a visitor's IP address no longer reaches a third party before the page
renders.

| Family | Files | Licence |
|---|---|---|
| Inter | `inter-normal-latin.woff2`, `inter-normal-latin-ext.woff2` | SIL Open Font License 1.1 |
| JetBrains Mono | `jetbrains-mono-normal-latin.woff2`, `jetbrains-mono-normal-latin-ext.woff2` | SIL Open Font License 1.1 |
| Newsreader | `newsreader-italic-latin.woff2`, `newsreader-italic-latin-ext.woff2` | SIL Open Font License 1.1 |

They are the unmodified woff2 files Google Fonts serves for these families - the
variable Inter (weights 300-800), variable JetBrains Mono (400-600) and variable
Newsreader italic - reduced to the Latin and Latin-Ext subsets, with the same
`unicode-range` values, so the rendering is unchanged. The full licence text is in
`OFL-1.1.md`, copied from `docs/implementation/fonts/OFL-1.1.md` rather than
fetched again.

## Copyright

- Inter: Copyright (c) 2016 The Inter Project Authors (https://github.com/rsms/inter)
- JetBrains Mono: Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)
- Newsreader: Copyright 2020 The Newsreader Project Authors (https://github.com/productiontype/Newsreader)

Each family is licensed under the SIL Open Font License, Version 1.1, which permits
use, modification and redistribution, including web embedding and self-hosting. The
files here are unmodified.

## Changing them

If a page needs another weight or subset, fetch that subset from Google Fonts once,
add the file here and the matching `@font-face` to `landing/fonts.css`. Do not put
an `@import` back: `tests/test_website_site_health.py` fails if a page requests a
font from a third-party host.
