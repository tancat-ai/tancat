# Publishing TanCat to PyPI - the owner's guide

**Short version: your one action is to say "go".** The front door pushes the tag; the workflow does
everything else. Nothing to install, nothing to type.

## The version policy: nothing is published under 1.0 before launch

- **While developing, releases are 0.x** (`0.1.0`, `0.2.0`, ...). The version in `pyproject.toml`
  IS the release version - the tag must equal it, or the guards refuse the publish.
- **No 1.0 tag until launch day.** Launching on a 1.4 looks careless, so the first number a customer
  sees as 1.0 is the launch itself.
- **On launch day** the version is set to `1.0.0` in `pyproject.toml`, merged to main, then tagged
  `v1.0.0`. That tag is the launch.
- **The floating `v1` tag** (what `uses: tancat-ai/tancat@v1` resolves to for the Action) is created
  by the launch release, not before: `move-v1` only runs for `v1.*`, so a 0.x release leaves it
  alone.

## What a first release does

Pushing a tag like `v0.1.0` to `main` runs `.github/workflows/release.yml`, which:

1. runs the normal gates and the six-mode action self-test;
2. builds the wheel and the source package (`uv build`);
3. runs four guards - the tag must match `pyproject.toml`, no file may be 100 MB or more (the sizes
   are printed), the licence record must match `uv.lock`, and the commit must be on `main`;
4. publishes to PyPI with **trusted publishing** - GitHub mints a short-lived token, PyPI verifies
   it. No API token is stored anywhere;
5. creates the GitHub Release with both files attached, and moves the floating `v1` tag.

The first upload is what claims the name `tancat` on PyPI. Until it happens, anyone could register
it - so it is worth doing soon, and the product's update check refuses a name that is not ours
either way.

## If the pending publisher is missing

You said it is already added (`tancat` / `tancat-ai` / `tancat` / `release.yml` / `pypi`). If PyPI
shows no pending publisher, add it in the browser, no terminal needed:

1. Sign in at <https://pypi.org> (two-factor on).
2. Open **Publishing** in your account menu -> **Add a pending publisher**.
3. Choose **GitHub**, then fill in exactly:
   - **PyPI Project Name**: `tancat`
   - **Owner**: `tancat-ai`
   - **Repository name**: `tancat`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
4. Save. It will sit as *pending* until the first successful publish, then become the project's
   publisher.

The GitHub side needs the environment too: **Settings -> Environments -> New environment -> `pypi`**.
(No secrets go in it - that is the point of trusted publishing.)

## The release itself

- The front door runs, on `main`: `git tag v0.1.0 && git push origin v0.1.0`.
- The tag must equal the version in `pyproject.toml` (today `0.1.0` -> `v0.1.0`; on launch day `1.0.0` -> `v1.0.0`). To release a
  different version, bump `[project].version` first, merge it, then tag.
- Watch **Actions -> Release**; the publish job prints the filenames and hashes it sent, and the
  result appears at <https://pypi.org/p/tancat>.

## Do we need a placeholder release?

**No.** The pending publisher is what authorises the first upload, and the first 0.x tag is itself the
placeholder-quality first release - it claims the name. A separate empty placeholder would only add
a version nobody should install.

The only thing worth checking after the first publish: the PyPI page for `tancat` should show the
repository and homepage links from `pyproject.toml` - the product's own update check requires them
to trust a future version answer.
