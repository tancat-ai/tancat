# TanCat dependency licences

TanCat itself is **Apache-2.0** (see `LICENSE`, Copyright 2026 lacattano). This
file is the licence record for everything TanCat installs, taken from the locked
dependency set (`uv.lock`). It exists so the owner can confirm ownership and
licensing for a store or customer review.

How this was generated (re-run to refresh):

    python scripts/maintenance/licence_record.py --write

That runs the licence metadata collector over the locked set:

    uv run --all-extras --group docs --group dev --with pip-licenses \
        pip-licenses --format=markdown --with-urls --order=license

CI job `licence-freshness` runs `--check`, which renders this document from
`uv.lock` and the committed licence metadata and fails when the two differ.

Scope: that guard holds the names, versions, count and section membership to `uv.lock`; the licence strings are read from this document, so a green check is not a licence audit.

## Verdict

- **Every direct dependency is permissive**: MIT, BSD-2/3-Clause, Apache-2.0,
  ISC or PSF. No AGPL, no SSPL, no proprietary, no commercial-only term.
- **Two transitive items are flagged** and are not strictly permissive:
  `text-unidecode` (GPL-2.0-or-later / Artistic-1.0 dual) and the `MPL-2.0`
  group (`certifi`, `orjson`, `tqdm`, and dev-only `fqdn`, `pathspec`). Details
  below.
- `pypdfium2` carries vague metadata ("dependency licenses"); the bundled
  PDFium is BSD-3-Clause, recorded in `DOCUMENT_READER_LICENSES.md`.

## Direct dependencies

Every package declared in `pyproject.toml`, with the licence it resolved to.
"Flag" is the one-line verdict; the full text is in the next section.

### Runtime (`[project].dependencies`)

| Package | Version | Licence | Flag |
|---|---|---|---|
| playwright | 1.63.0 | Apache-2.0 |  |
| pytest-playwright | 0.10.0 | Apache Software License |  |
| python-dotenv | 1.2.4 | BSD-3-Clause |  |
| streamlit | 1.65.0 | Apache-2.0 |  |
| httpx | 0.28.1 | BSD License |  |
| beautifulsoup4 | 4.15.0 | MIT License |  |
| plotly | 7.1.0 | MIT |  |
| pandas | 3.0.6 | BSD License |  |
| pillow | 12.3.0 | MIT-CMU | Note |
| pyyaml | 6.0.3 | MIT License |  |
| pytest-timeout | 2.4.0 | DFSG approved; MIT License |  |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |  |
| pymilvus | 3.0.0 | Apache Software License |  |
| sentence-transformers | 6.1.0 | Apache-2.0 |  |
| milvus-lite | 3.2.1 | Apache Software License |  |
| langgraph | 1.2.14 | MIT |  |
| torch | 2.14.1+cpu | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT |  |

### PDF extra (`[project.optional-dependencies].pdf`)

| Package | Version | Licence | Flag |
|---|---|---|---|
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licenses | Note |
| pdfplumber | 0.11.10 | MIT License |  |

### OCR extra (`[project.optional-dependencies].ocr`)

| Package | Version | Licence | Flag |
|---|---|---|---|
| rapidocr | 3.10.0 | Apache-2.0 |  |
| opencv-python-headless | 5.0.0.93 | Apache Software License |  |

### Docs group (`[dependency-groups].docs`)

| Package | Version | Licence | Flag |
|---|---|---|---|
| mkdocs-material | 9.7.7 | MIT |  |

### Dev group (`[dependency-groups].dev`)

| Package | Version | Licence | Flag |
|---|---|---|---|
| ruff | 0.17.0 | MIT |  |
| mypy | 2.4.0 | MIT |  |
| pytest | 9.1.1 | MIT |  |
| pytest-cov | 7.1.0 | MIT |  |
| pytest-xdist | 3.8.0 | MIT |  |
| pre-commit | 4.6.2 | MIT |  |
| pandas-stubs | 3.0.5.260914 | BSD-3-Clause |  |
| types-PyYAML | 6.0.12.20260724 | Apache-2.0 |  |
| jupyter | 1.1.1 | BSD License |  |
| ipykernel | 7.4.0 | BSD-3-Clause |  |
| nest-asyncio | 1.6.0 | BSD License |  |
| pytest-asyncio | 1.4.0 | Apache-2.0 |  |
| coverage | 7.16.2 | Apache-2.0 |  |

## Flagged: non-permissive or unclear

| Package | Licence (as reported) | Flag |
|---|---|---|
| text-unidecode | Artistic License; GNU General Public License (GPL); GNU General Public License v2 or later (GPLv2+) | FLAG - dual GPL-2.0-or-later / Artistic-1.0. pip-licenses reports the GPL classifiers. The Artistic option is permissive, but the licence choice must be made and recorded; the GPL option alone would conflict with shipping Apache-2.0 TanCat. Pulled in by pytest-playwright -> python-slugify, so it is in the default install. |
| certifi | Mozilla Public License 2.0 (MPL 2.0) | FLAG - MPL-2.0 (weak, file-level copyleft), not permissive. Used unmodified as a library; keep it unmodified and it is compatible. |
| orjson | MPL-2.0 AND (Apache-2.0 OR MIT) | FLAG - MPL-2.0 AND (Apache-2.0 OR MIT). The Apache/MIT option applies, so it is effectively permissive; flagged because the metadata leads with MPL. |
| tqdm | MPL-2.0 AND MIT | FLAG - MPL-2.0 AND MIT. The MIT option applies; flagged because the metadata leads with MPL. |
| fqdn | Mozilla Public License 2.0 (MPL 2.0) | FLAG - MPL-2.0. Dev/Jupyter only (jupyter-events), not in the shipped runtime. |
| pathspec | Mozilla Public License 2.0 (MPL 2.0) | FLAG - MPL-2.0. Dev only (mypy), not in the shipped runtime. |
| pypdfium2 | BSD-3-Clause, Apache-2.0, dependency licenses | Note - metadata reads 'BSD-3-Clause, Apache-2.0, dependency licenses'. The bundled PDFium is BSD-3-Clause. Full record: docs/licenses/DOCUMENT_READER_LICENSES.md. |
| pillow | MIT-CMU | Note - MIT-CMU (permissive; a non-standard name, not a flag). |

MPL-2.0 is a weak, file-level copyleft. Using the packages unmodified as
libraries is fine and does not affect TanCat's Apache-2.0 licence. The flag is
recorded so the position is a decision, not an oversight. For `text-unidecode`,
the permissive Artistic option should be the one relied on.

## Fonts

The landing page (`landing/index.html`, `landing/install.html`) loads three
fonts from Google Fonts:

| Font | Licence | Copyright |
|---|---|---|
| Inter | SIL Open Font License 1.1 | Copyright (c) 2016 The Inter Project Authors |
| JetBrains Mono | SIL Open Font License 1.1 | Copyright 2020 The JetBrains Mono Project Authors |
| Newsreader | SIL Open Font License 1.1 | Copyright 2020 The Newsreader Project Authors |

All three are OFL-1.1, which permits web and print use. They are fetched from
Google's CDN at page load and are **not redistributed** by the landing page.

The Pro install/licence PDF (`landing/tancat-pro-install-and-licence.pdf`) is
different: it **redistributes** four font files, bundled in
`docs/implementation/fonts/`, so the render cannot fall back to a font installed
on the build machine (it used to embed Segoe UI and Consolas from the host). They
are unmodified release files, all OFL-1.1:

| File | Face | Licence | Copyright | SHA-256 |
|---|---|---|---|---|
| `inter-regular.woff2` | Inter Regular (400) | OFL-1.1 | Copyright (c) 2016 The Inter Project Authors | `e06f6b1bc553aaea4e4668023ed0ab0a147129c3107f511bc7d03d361b0ae085` |
| `inter-bold.woff2` | Inter Bold (700) | OFL-1.1 | Copyright (c) 2016 The Inter Project Authors | `fa888127b6da015b65569f0351f3b5c391ad928904951f1c20e9f8462a8d95ea` |
| `inter-italic.woff2` | Inter Italic (400) | OFL-1.1 | Copyright (c) 2016 The Inter Project Authors | `2d078cb3bc8f934740d53b39dd23b0678f2f97477e49ec785dd9d8acd8b96bfc` |
| `jetbrains-mono-regular.woff2` | JetBrains Mono Regular (400) | OFL-1.1 | Copyright 2020 The JetBrains Mono Project Authors | `f1a7a03672cdd494ce0d5543fac6e4360fe22403c6de297fdc2e55a815f7baff` |

The source repositories are Inter (`docs/font-files/`, github.com/rsms/inter)
and JetBrains Mono (`fonts/webfonts/`, github.com/JetBrains/JetBrainsMono).
Newsreader is **not bundled**: the install/licence document has no serif text, so
the PDF never embeds it. The full OFL-1.1 text and both copyright notices are in
`docs/implementation/fonts/OFL-1.1.md`, next to the fonts as the licence requires,
and the four files are listed as PDF sources in `landing/asset-sources.json` so
the landing asset guard fails if a font changes without a re-render. Verified by
inspecting the rebuilt PDF: it embeds only `Inter-Regular`, `Inter-Bold`,
`Inter-Italic` and `JetBrainsMono-Regular` (Type0 subsets), no Microsoft face.

Rule: only `landing/tancat-pro-install-and-licence.pdf` is rendered to a shipped
document. Any other page that is ever printed must use the bundled open faces
under `docs/implementation/fonts/`, never a font the host happens to have -
because `docs/launch/lemon-squeezy-checklist.html` and `docs/walkthrough.md`
still declare host fonts in their CSS, and a headless render resolves those
against the build machine.

## Original TanCat assets

- `landing/logo_transparent.png` (the TanCat logo) and the icon set derived from
  it (`favicon.ico`, `icon-192.png`, `icon-512.png`, `apple-touch-icon.png`) are
  **original TanCat work**, created for this project. They are not third-party
  stock.
- `landing/noir_art.jpg` is **original TanCat artwork**, created for this
  project.
- `landing/streamlit_real_1280x820.png` is a real screenshot of the TanCat UI.

`landing/asset-sources.json` is generated by
`scripts/maintenance/make_landing_assets.py` (which rewrites it on every run and
therefore cannot carry a hand-written note), so this originality record lives
here instead.

## Appendix: full locked set (224 entries)

The complete resolved environment, including transitive dependencies, for
completeness. TanCat itself is described at the top of this file. Sorted by name.

| Package | Version | Licence | URL |
|---|---|---|---|
| altair | 6.2.2 | BSD License | https://github.com/vega/altair |
| annotated-doc | 0.0.5 | MIT | https://github.com/fastapi/annotated-doc |
| annotated-types | 0.8.0 | MIT | https://github.com/annotated-types/annotated-types |
| anyio | 4.14.2 | MIT | https://anyio.readthedocs.io/en/stable/versionhistory.html |
| appnope | 0.1.4 | BSD License | https://github.com/minrk/appnope |
| argon2-cffi | 25.1.0 | MIT | https://github.com/hynek/argon2-cffi/blob/main/CHANGELOG.md |
| argon2-cffi-bindings | 25.1.0 | MIT | https://github.com/hynek/argon2-cffi-bindings/blob/main/CHANGELOG.md |
| arrow | 1.4.0 | Apache Software License | https://github.com/arrow-py/arrow |
| ast-serialize | 0.12.1 | MIT | https://github.com/mypyc/ast_serialize |
| asttokens | 3.0.2 | Apache 2.0 | https://github.com/gristlabs/asttokens |
| async-lru | 2.3.0 | MIT License | https://github.com/aio-libs/async-lru |
| attrs | 26.1.0 | MIT | https://www.attrs.org/en/stable/changelog.html |
| babel | 2.18.0 | BSD License | https://babel.pocoo.org/ |
| backrefs | 8.0 | MIT | https://github.com/facelessuser/backrefs |
| beautifulsoup4 | 4.15.0 | MIT License | https://www.crummy.com/software/BeautifulSoup/bs4/ |
| bleach | 6.4.0 | Apache Software License | https://github.com/mozilla/bleach |
| cachetools | 7.1.6 | MIT | https://github.com/tkem/cachetools/ |
| certifi | 2026.10.18 | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi |
| cffi | 2.1.0 | MIT-0 | https://cffi.readthedocs.io/en/latest/whatsnew.html |
| cfgv | 3.5.0 | MIT | https://github.com/asottile/cfgv |
| charset-normalizer | 3.4.9 | MIT | https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md |
| click | 8.4.2 | BSD-3-Clause | https://github.com/pallets/click/ |
| colorama | 0.4.6 | BSD License | https://github.com/tartley/colorama |
| colorlog | 6.12.0 | MIT License | https://github.com/borntyping/python-colorlog |
| comm | 0.2.3 | BSD License | https://github.com/ipython/comm |
| coverage | 7.16.2 | Apache-2.0 | https://github.com/coveragepy/coveragepy |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| debugpy | 1.8.21 | MIT License | https://aka.ms/debugpy |
| decorator | 5.3.1 | BSD-2-Clause | UNKNOWN |
| defusedxml | 0.7.1 | Python Software Foundation License | https://github.com/tiran/defusedxml |
| distlib | 0.4.3 | Python Software Foundation License | https://github.com/pypa/distlib |
| distro | 1.9.0 | Apache Software License | https://github.com/python-distro/distro |
| execnet | 2.1.2 | MIT | https://execnet.readthedocs.io/en/latest/ |
| executing | 2.2.1 | MIT License | https://github.com/alexmojaki/executing |
| faiss-cpu | 1.14.3 | MIT | https://github.com/facebookresearch/faiss |
| fastjsonschema | 2.22.1 | BSD License | https://github.com/horejsek/python-fastjsonschema |
| filelock | 3.32.0 | MIT | https://github.com/tox-dev/py-filelock |
| fqdn | 1.5.1 | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/ypcrts/fqdn |
| fsspec | 2026.7.0 | BSD-3-Clause | https://github.com/fsspec/filesystem_spec |
| ghp-import | 2.1.0 | Apache Software License | https://github.com/c-w/ghp-import |
| greenlet | 3.5.4 | MIT AND PSF-2.0 | https://greenlet.readthedocs.io |
| grpcio | 1.83.0 | Apache-2.0 | https://grpc.io |
| h11 | 0.16.0 | MIT License | https://github.com/python-hyper/h11 |
| hf-xet | 1.5.2 | Apache-2.0 | https://github.com/huggingface/xet-core |
| httpcore | 1.0.9 | BSD-3-Clause | https://www.encode.io/httpcore/ |
| httptools | 0.8.0 | MIT | https://github.com/MagicStack/httptools |
| httpx | 0.28.1 | BSD License | https://github.com/encode/httpx |
| huggingface-hub | 1.25.1 | Apache Software License | https://github.com/huggingface/huggingface_hub |
| identify | 2.6.19 | MIT | https://github.com/pre-commit/identify |
| idna | 3.18 | BSD-3-Clause | https://github.com/kjd/idna |
| iniconfig | 2.3.0 | MIT | https://github.com/pytest-dev/iniconfig |
| ipykernel | 7.4.0 | BSD-3-Clause | https://ipython.org |
| ipython | 9.15.0 | BSD-3-Clause | https://ipython.org |
| ipython-pygments-lexers | 1.1.1 | BSD License | https://github.com/ipython/ipython-pygments-lexers |
| ipywidgets | 8.1.8 | BSD License | http://jupyter.org |
| isoduration | 20.11.0 | ISC License (ISCL) | https://github.com/bolsote/isoduration |
| itsdangerous | 2.2.0 | BSD License | https://github.com/pallets/itsdangerous/ |
| jedi | 0.20.0 | MIT License | https://github.com/davidhalter/jedi |
| jinja2 | 3.1.6 | BSD License | https://github.com/pallets/jinja/ |
| joblib | 1.5.3 | BSD-3-Clause | https://joblib.readthedocs.io |
| json5 | 0.15.0 | Apache Software License | https://github.com/dpranke/pyjson5 |
| jsonpatch | 1.33 | BSD License | https://github.com/stefankoegl/python-json-patch |
| jsonpointer | 3.1.1 | BSD License | https://github.com/stefankoegl/python-json-pointer |
| jsonschema | 4.26.0 | MIT | https://github.com/python-jsonschema/jsonschema |
| jsonschema-specifications | 2025.9.1 | MIT | https://github.com/python-jsonschema/jsonschema-specifications |
| jupyter | 1.1.1 | BSD License | https://jupyter.org |
| jupyter-builder | 1.1.1 | BSD-3-Clause AND MIT AND ISC | https://jupyter.org |
| jupyter-client | 8.9.1 | BSD License | https://jupyter.org |
| jupyter-console | 6.6.3 | BSD License | https://jupyter.org |
| jupyter-core | 5.9.1 | BSD-3-Clause | https://jupyter.org |
| jupyter-events | 0.12.1 | BSD License | http://jupyter.org |
| jupyter-lsp | 2.3.1 | BSD License | https://jupyterlab-lsp.readthedocs.io/ |
| jupyter-server | 2.20.0 | BSD License | https://jupyter-server.readthedocs.io |
| jupyter-server-terminals | 0.5.4 | BSD License | https://jupyter.org |
| jupyterlab | 4.6.2 | BSD License | https://jupyter.org |
| jupyterlab-pygments | 0.3.0 | BSD License | https://github.com/jupyterlab/jupyterlab_pygments |
| jupyterlab-server | 2.28.0 | BSD License | https://jupyterlab-server.readthedocs.io |
| jupyterlab-widgets | 3.0.16 | BSD License | https://github.com/jupyter-widgets/ipywidgets |
| langchain-core | 1.5.2 | MIT License | https://docs.langchain.com/ |
| langchain-protocol | 0.0.18 | MIT License | https://github.com/langchain-ai/agent-protocol/tree/main/streaming |
| langgraph | 1.2.14 | MIT | https://docs.langchain.com/oss/python/langgraph/overview |
| langgraph-checkpoint | 4.1.1 | MIT | https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint |
| langgraph-prebuilt | 1.1.0 | MIT | https://github.com/langchain-ai/langgraph/tree/main/libs/prebuilt |
| langgraph-sdk | 0.4.6 | MIT | https://github.com/langchain-ai/langgraph/tree/main/libs/sdk-py |
| langsmith | 0.10.12 | MIT | https://smith.langchain.com/ |
| lark | 1.3.1 | MIT License | https://github.com/lark-parser/lark |
| librt | 0.16.0 | MIT | https://github.com/mypyc/librt |
| markdown | 3.11 | BSD-3-Clause | https://Python-Markdown.github.io/ |
| markdown-it-py | 4.2.0 | MIT License | https://github.com/executablebooks/markdown-it-py |
| markupsafe | 3.0.3 | BSD-3-Clause | https://github.com/pallets/markupsafe/ |
| matplotlib-inline | 0.2.2 | BSD-3-Clause | https://github.com/ipython/matplotlib-inline |
| mdurl | 0.1.2 | MIT License | https://github.com/executablebooks/mdurl |
| mergedeep | 1.3.4 | MIT License | https://github.com/clarketm/mergedeep |
| milvus-lite | 3.2.1 | Apache Software License | https://github.com/milvus-io/milvus-lite |
| mistune | 3.3.4 | BSD License | https://github.com/lepture/mistune |
| mkdocs | 1.6.1 | BSD-2-Clause | https://github.com/mkdocs/mkdocs |
| mkdocs-get-deps | 0.2.2 | MIT | https://github.com/mkdocs/get-deps |
| mkdocs-material | 9.7.7 | MIT | https://github.com/squidfunk/mkdocs-material |
| mkdocs-material-extensions | 1.3.1 | MIT | https://github.com/facelessuser/mkdocs-material-extensions |
| mpmath | 1.3.0 | BSD License | http://mpmath.org/ |
| mypy | 2.4.0 | MIT | https://www.mypy-lang.org/ |
| mypy-extensions | 1.1.0 | MIT | https://github.com/python/mypy_extensions |
| narwhals | 2.24.0 | MIT | https://github.com/narwhals-dev/narwhals |
| nbclient | 0.11.0 | BSD License | https://jupyter.org |
| nbconvert | 7.17.1 | BSD License | https://jupyter.org |
| nbformat | 5.10.4 | BSD License | https://jupyter.org |
| nest-asyncio | 1.6.0 | BSD License | https://github.com/erdewit/nest_asyncio |
| nest-asyncio2 | 1.7.2 | BSD License | https://github.com/Chaoses-Ib/nest-asyncio2 |
| networkx | 3.6.1 | BSD-3-Clause | https://networkx.org/ |
| nodeenv | 1.10.0 | BSD License | https://github.com/ekalinin/nodeenv |
| notebook | 7.6.1 | BSD License | https://github.com/jupyter/notebook |
| notebook-shim | 0.2.4 | BSD License | UNKNOWN |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org |
| omegaconf | 2.4.0 | BSD License | https://github.com/hydra-ecosystem/omegaconf |
| opencv-python-headless | 5.0.0.93 | Apache Software License | https://github.com/opencv/opencv-python |
| orjson | 3.11.9 | MPL-2.0 AND (Apache-2.0 OR MIT) | https://github.com/ijl/orjson |
| ormsgpack | 1.12.2 | Apache-2.0 OR MIT | https://github.com/ormsgpack/ormsgpack |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| paginate | 0.5.7 | MIT License | https://github.com/Signum/paginate |
| pandas | 3.0.6 | BSD License | https://pandas.pydata.org |
| pandas-stubs | 3.0.5.260914 | BSD-3-Clause | https://pandas.pydata.org |
| pandocfilters | 1.5.1 | BSD License | http://github.com/jgm/pandocfilters |
| parso | 0.8.7 | MIT License | https://github.com/davidhalter/parso |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | https://python-path-specification.readthedocs.io/en/latest/index.html |
| pdfminer-six | 20260107 | MIT | https://github.com/pdfminer/pdfminer.six |
| pdfplumber | 0.11.10 | MIT License | https://github.com/jsvine/pdfplumber |
| pexpect | 4.9.0 | ISC License (ISCL) | https://pexpect.readthedocs.io/ |
| pillow | 12.3.0 | MIT-CMU | https://python-pillow.github.io |
| platformdirs | 4.11.0 | MIT | https://github.com/tox-dev/platformdirs |
| playwright | 1.63.0 | Apache-2.0 | https://github.com/Microsoft/playwright-python |
| plotly | 7.1.0 | MIT | https://plotly.com/python/ |
| pluggy | 1.6.0 | MIT License | UNKNOWN |
| pre-commit | 4.6.2 | MIT | https://github.com/pre-commit/pre-commit |
| prometheus-client | 0.26.0 | Apache-2.0 AND BSD-2-Clause | https://github.com/prometheus/client_python |
| prompt-toolkit | 3.0.53 | BSD License | https://github.com/prompt-toolkit/python-prompt-toolkit |
| protobuf | 7.35.1 | 3-Clause BSD License | https://developers.google.com/protocol-buffers/ |
| psutil | 7.2.2 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| ptyprocess | 0.7.0 | ISC License (ISCL) | https://github.com/pexpect/ptyprocess |
| pure-eval | 0.2.3 | MIT License | http://github.com/alexmojaki/pure_eval |
| pyarrow | 24.0.0 | Apache-2.0 | https://arrow.apache.org/ |
| pyclipper | 1.4.0 | MIT License | https://github.com/fonttools/pyclipper |
| pycparser | 3.0 | BSD-3-Clause | https://github.com/eliben/pycparser |
| pydantic | 2.13.5 | MIT | https://github.com/pydantic/pydantic |
| pydantic-core | 2.46.5 | MIT | https://github.com/pydantic |
| pydeck | 0.9.3 | Apache License 2.0 | https://github.com/visgl/deck.gl/tree/master/bindings/pydeck |
| pyee | 13.0.1 | MIT License | https://github.com/jfhbrook/pyee |
| pygments | 2.20.0 | BSD-2-Clause | https://pygments.org |
| pymdown-extensions | 12.1 | MIT | https://github.com/facelessuser/pymdown-extensions |
| pymilvus | 3.0.0 | Apache Software License | https://github.com/milvus-io/pymilvus |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licenses | https://github.com/pypdfium2-team/pypdfium2 |
| pytest | 9.1.1 | MIT | https://docs.pytest.org/en/latest/ |
| pytest-asyncio | 1.4.0 | Apache-2.0 | https://github.com/pytest-dev/pytest-asyncio |
| pytest-cov | 7.1.0 | MIT | https://pytest-cov.readthedocs.io/en/latest/changelog.html |
| pytest-playwright | 0.10.0 | Apache Software License | https://github.com/microsoft/playwright-pytest |
| pytest-timeout | 2.4.0 | DFSG approved; MIT License | https://github.com/pytest-dev/pytest-timeout |
| pytest-xdist | 3.8.0 | MIT | https://github.com/pytest-dev/pytest-xdist |
| python-dateutil | 2.9.0.post0 | Apache Software License; BSD License | https://github.com/dateutil/dateutil |
| python-discovery | 1.5.0 | MIT License | https://github.com/tox-dev/python-discovery |
| python-dotenv | 1.2.4 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| python-json-logger | 4.1.0 | BSD-2-Clause | https://nhairs.github.io/python-json-logger |
| python-multipart | 0.0.32 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| python-slugify | 8.0.4 | MIT License | https://github.com/un33k/python-slugify |
| pywinpty | 3.0.5 | MIT License | https://github.com/andfoy/pywinpty |
| pyyaml | 6.0.3 | MIT License | https://pyyaml.org/ |
| pyyaml-env-tag | 1.1 | MIT | https://github.com/waylan/pyyaml-env-tag |
| pyzmq | 27.1.0 | BSD License | https://pyzmq.readthedocs.org |
| rapidocr | 3.10.0 | Apache-2.0 | https://github.com/RapidAI/RapidOCR/releases |
| referencing | 0.37.0 | MIT | https://github.com/python-jsonschema/referencing |
| regex | 2026.7.19 | Apache-2.0 AND CNRI-Python | https://github.com/mrabarnett/mrab-regex |
| requests | 2.34.2 | Apache Software License | https://github.com/psf/requests |
| requests-toolbelt | 1.0.0 | Apache Software License | https://toolbelt.readthedocs.io/ |
| rfc3339-validator | 0.1.4 | MIT License | https://github.com/naimetti/rfc3339-validator |
| rfc3986-validator | 0.1.1 | MIT License | https://github.com/naimetti/rfc3986-validator |
| rfc3987-syntax | 1.1.0 | MIT | https://github.com/willynilly/rfc3987-syntax |
| rich | 15.0.0 | MIT License | https://github.com/Textualize/rich |
| rpds-py | 2026.6.3 | MIT | https://github.com/crate-py/rpds |
| ruff | 0.17.0 | MIT | https://docs.astral.sh/ruff |
| safetensors | 0.8.0 | Apache Software License | https://github.com/huggingface/safetensors |
| scikit-learn | 1.9.0 | BSD-3-Clause | https://scikit-learn.org |
| scipy | 1.18.0 | BSD License | https://scipy.org/ |
| send2trash | 2.1.0 | BSD-3-Clause | https://github.com/arsenetar/send2trash |
| sentence-transformers | 6.1.0 | Apache-2.0 | https://www.SBERT.net |
| setuptools | 83.0.0 | MIT | https://github.com/pypa/setuptools |
| shapely | 2.1.2 | BSD License | https://github.com/shapely/shapely |
| shellingham | 1.5.4 | ISC License (ISCL) | https://github.com/sarugaku/shellingham |
| six | 1.17.0 | MIT License | https://github.com/benjaminp/six |
| sniffio | 1.3.1 | Apache Software License; MIT License | https://github.com/python-trio/sniffio |
| soupsieve | 2.9.1 | MIT | https://github.com/facelessuser/soupsieve |
| stack-data | 0.6.3 | MIT License | http://github.com/alexmojaki/stack_data |
| starlette | 1.3.1 | BSD-3-Clause | https://github.com/Kludex/starlette |
| streamlit | 1.65.0 | Apache-2.0 | https://streamlit.io |
| sympy | 1.14.0 | BSD License | https://sympy.org |
| tenacity | 9.1.4 | Apache Software License | https://github.com/jd/tenacity |
| terminado | 0.18.1 | BSD License | https://github.com/jupyter/terminado |
| text-unidecode | 1.3 | Artistic License; GNU General Public License (GPL); GNU General Public License v2 or later (GPLv2+) | https://github.com/kmike/text-unidecode/ |
| threadpoolctl | 3.6.0 | BSD License | https://github.com/joblib/threadpoolctl |
| tinycss2 | 1.5.1 | BSD License | https://www.courtbouillon.org/tinycss2 |
| tokenizers | 0.23.2 | Apache Software License | https://github.com/huggingface/tokenizers |
| toml | 0.10.2 | MIT License | https://github.com/uiri/toml |
| torch | 2.14.1 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | https://pytorch.org |
| torch | 2.14.1+cpu | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | https://pytorch.org |
| tornado | 6.5.7 | Apache Software License | http://www.tornadoweb.org/ |
| tqdm | 4.70.0 | MPL-2.0 AND MIT | https://tqdm.github.io |
| traitlets | 5.15.1 | BSD License | https://github.com/ipython/traitlets |
| transformers | 5.17.0 | Apache 2.0 License | https://github.com/huggingface/transformers |
| typer | 0.27.2 | MIT | https://github.com/fastapi/typer |
| types-pyyaml | 6.0.12.20260724 | Apache-2.0 | https://github.com/python/typeshed |
| typing-extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| typing-inspection | 0.4.2 | MIT | https://github.com/pydantic/typing-inspection |
| tzdata | 2026.3 | Apache-2.0 | https://github.com/python/tzdata |
| uri-template | 1.3.0 | MIT License | https://gitlab.linss.com/open-source/python/uri-template |
| urllib3 | 2.7.0 | MIT | https://github.com/urllib3/urllib3/blob/main/CHANGES.rst |
| uuid-utils | 0.17.0 | BSD-3-Clause | https://github.com/aminalaee/uuid-utils |
| uvicorn | 0.52.0 | BSD-3-Clause | https://uvicorn.dev/ |
| virtualenv | 21.7.0 | MIT | https://github.com/pypa/virtualenv |
| watchdog | 6.0.0 | Apache Software License | https://github.com/gorakhargosh/watchdog |
| wcwidth | 0.8.2 | MIT License | https://github.com/jquast/wcwidth |
| webcolors | 25.10.0 | BSD License | https://webcolors.readthedocs.io |
| webencodings | 0.5.1 | BSD License | https://github.com/SimonSapin/python-webencodings |
| websocket-client | 1.9.0 | Apache Software License | https://github.com/websocket-client/websocket-client.git |
| websockets | 15.0.1 | BSD License | https://github.com/python-websockets/websockets |
| widgetsnbextension | 4.0.15 | BSD License | http://jupyter.org |
| xxhash | 3.8.1 | BSD-2-Clause | https://github.com/ifduyue/python-xxhash |
| zstandard | 0.25.0 | BSD-3-Clause | https://github.com/indygreg/python-zstandard |
