# The landing pages' fonts - provenance and how to change them

This note is internal. It lives here, in `docs/implementation/`, because `landing/` is
deployed: `pages-deploy.yml` runs `cp -r landing/. _site/`, so anything left in
`landing/` is published at tancat.dev. The font files themselves are in
`landing/fonts/`, and the licence (`OFL-1.1.md`) travels beside them there, because
the OFL requires the licence to accompany the fonts and a reader of the site may want
to see it.

The landing pages load two families from `landing/fonts.css`, from files served by
this site. Nothing is requested from Google at page load, so a visitor's IP address
does not reach a third party before the page renders.

| Family | File in `landing/fonts/` | Licence |
|---|---|---|
| Inter | `inter-normal-latin.woff2` | SIL Open Font License 1.1 |
| JetBrains Mono | `jetbrains-mono-normal-latin.woff2` | SIL Open Font License 1.1 |

## Where the files came from

They are the unmodified woff2 files **Google Fonts** serves for these families - the
variable Inter (weights 300-800) and the variable JetBrains Mono (400-600) - reduced
to the Latin subset, with the same `unicode-range` and `font-display: swap` values the
Google stylesheet used, so the rendering is unchanged. They were fetched once, when
the `@import` was removed (t-1419); the wider subsets were dropped in t-1421 because
no page ever fetched them.

Only the Latin subset is bundled: the pages and the docs are English, and no page
sets serif text. Characters outside Latin fall back to the system font. The docs site
uses the same two files through `docs/user/assets/fonts.css`.

## Licence and copyright

The full licence text is `landing/fonts/OFL-1.1.md`, copied from the copy already
bundled here (`docs/implementation/fonts/OFL-1.1.md`) rather than fetched again.

- Inter: Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)
- JetBrains Mono: Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)

Both are licensed under the SIL Open Font License, Version 1.1, which permits use,
modification and redistribution, including web embedding and self-hosting. The files
are unmodified. The copyright lines are copied from each family's metadata in the
Google Fonts repository (`ofl/inter/METADATA.pb`, `ofl/jetbrainsmono/METADATA.pb`).

## Changing them

If a page needs another weight or subset, fetch that subset from Google Fonts once,
add the file to `landing/fonts/`, add the matching `@font-face` to
`landing/fonts.css`, and update `landing/fonts/OFL-1.1.md` if a family is added or
removed.

**Do not put an `@import` back.** `tests/test_website_site_health.py` fails if any
page loads a resource from another host, and it also refuses a font file that
`fonts.css` never references, so nothing dead or third-party can creep back in.
