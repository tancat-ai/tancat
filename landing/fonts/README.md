# Fonts served by the landing pages

The landing pages load two families from `landing/fonts.css`, and the files in this
directory are served from this site. Nothing is requested from Google at page load,
so a visitor's IP address no longer reaches a third party before the page renders.

| Family | File | Licence |
|---|---|---|
| Inter | `inter-normal-latin.woff2` | SIL Open Font License 1.1 |
| JetBrains Mono | `jetbrains-mono-normal-latin.woff2` | SIL Open Font License 1.1 |

They are the unmodified woff2 files Google Fonts serves for these families - the
variable Inter (weights 300-800) and the variable JetBrains Mono (400-600) - reduced
to the Latin subset, with the same `unicode-range` values, so the rendering is
unchanged.

Only the Latin subset is bundled: the pages are English, and the wider subsets were
declared but never fetched. Characters outside Latin fall back to the system font.
The docs site uses the same two files; see `docs/user/assets/fonts.css`.

The full licence text is in `OFL-1.1.md`, copied from
`docs/implementation/fonts/OFL-1.1.md` rather than fetched again.

## Copyright

- Inter: Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)
- JetBrains Mono: Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)

Both are licensed under the SIL Open Font License, Version 1.1, which permits use,
modification and redistribution, including web embedding and self-hosting. The files
here are unmodified.

## Changing them

If a page needs another weight or subset, fetch that subset from Google Fonts once,
add the file here and the matching `@font-face` to `landing/fonts.css`. Do not put an
`@import` back: `tests/test_website_site_health.py` fails if a page loads a resource
from another host.
