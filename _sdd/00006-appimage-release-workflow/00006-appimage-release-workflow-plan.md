# Plan: appimage-release-workflow

## Context

Spec:
`_sdd/00006-appimage-release-workflow/00006-appimage-release-workflow-spec.md`

Current behaviour:

- There is no `.github/` directory, no CI and no packaging of any kind. vidnote
  runs from a source checkout through `./run.sh` or `pip install -e .`.
- `find_script()` in `src/vidnote/main_window.py` first honours `VIDNOTE_SCRIPT`
  (only if it points to an existing file) and then falls back to
  `<repo root>/scripts/annotate.sh`, computed from `__file__`. Inside an
  AppImage that fallback does not exist, but the env var override is enough, so
  **no Python change is needed**: the AppImage entry point sets
  `VIDNOTE_SCRIPT`.
- **Render** runs `bash <script> ...` through `QProcess`, so the script does not
  need an executable bit inside the read-only AppImage mount. It calls the
  host's `ffmpeg` and `fc-match`.
- The app imports only
  `PySide6.QtCore/QtGui/QtWidgets/QtMultimedia/ QtMultimediaWidgets`, which are
  all in the `PySide6-Essentials` wheel.

What changes, following the spec and its answered Open Questions:

- A new manually triggered workflow `.github/workflows/release.yml` with one
  input, `tag`. It validates the input, lints and tests, builds the AppImage,
  and only then publishes the release with the AppImage as its only asset.
- Validation (all before anything is built, no tag or release is touched): the
  run must be on `refs/heads/main`; the tag must match
  `^v[0-9]+\.[0-9]+\.[0-9]+$` (so any suffix such as `-rc1` fails, and no
  pre-release exists); the version in the tag must equal `version` in
  `pyproject.toml`; the tag must not exist and no release for it may exist.
- The AppImage is built with `python-appimage` (`build app`) on `ubuntu-22.04`
  against the `manylinux_2_28_x86_64` Python (glibc 2.28, so it runs on Ubuntu
  22.04 and newer). The package sources and `scripts/annotate.sh` are added as
  extra data instead of being pip-installed, which avoids the limitations of
  local requirements. `libxcb-cursor.so.0` and its missing dependencies are
  taken from the runner and bundled. `ffmpeg`, `fontconfig` and fonts are
  **not** bundled (answered Open Question); the README documents them as runtime
  requirements.
- The build is done by a script, `packaging/appimage/build.sh`, that the
  workflow calls and that can also be run locally, so the AppImage can be
  verified without GitHub.
- No tag is orphaned: the release is created as a **draft** with the asset
  attached (a draft does not create the tag), then published with
  `--target <sha>` so the tag is created at publish time on the commit the run
  started from. If anything fails after the draft exists, a cleanup step deletes
  the draft (and the tag, if it was created by this run).

Design decisions made in this plan (not covered by the spec):

- Version format is strictly `vMAJOR.MINOR.PATCH`; the AppImage version is the
  tag without `v`.
- Two jobs: `build` (permissions `contents: read`) and `release` (permissions
  `contents: write`, `needs: build`). The AppImage travels between them as a
  workflow artifact, so the write token is never present while lint, tests and
  the build run.
- `concurrency: group: release (not cancelled)` serializes releases. A single
  global group is used because every run targets `main`; the second run then
  fails its own "tag already exists" check after the first one finishes.
  `release` repeats the tag / release existence check right before creating the
  draft (the time since the first check can be long).
- The tag input is passed to shell steps through `env:` and never interpolated
  into the script text.
- The workflow smoke-tests the built AppImage with `QT_QPA_PLATFORM=offscreen`
  and `--appimage-extract-and-run` (a plain run would need FUSE, which the
  runner image may lack) before uploading it.
- The icon is a simple generated placeholder PNG (a yellow rounded square) that
  can be replaced later.
- Python for the AppImage is 3.12 (`cp312-cp312`); `requires-python` stays
  `>=3.9`. PySide6 is pinned to a minor series in the recipe's
  `requirements.txt` for reproducible builds.

## Files to Modify

### 1. `packaging/appimage/entrypoint.sh` (new)

Template processed by `python-appimage`. Content:

```bash
#! /bin/bash
export VIDNOTE_SCRIPT="${VIDNOTE_SCRIPT:-${APPDIR}/annotate.sh}"
export LD_LIBRARY_PATH="${APPDIR}/extra-libs${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${APPDIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec {{ python-executable }} -s -m vidnote "$@"
```

- `-s` keeps the user's site-packages out; `PYTHONPATH` makes the bundled
  `vidnote` package (copied to `$APPDIR/vidnote`) importable.
- `"$@"` passes the optional video path through, as `./run.sh` does.
  `VIDNOTE_SCRIPT` and `FONT` set by the user keep working (`FONT` is read by
  `annotate.sh` itself from the inherited environment).
- `LD_LIBRARY_PATH` is inherited by the `bash`/`ffmpeg` processes the render
  starts; `extra-libs` therefore contains only the few libraries that Qt needs
  and normal desktops lack. If it ever disturbs the host `ffmpeg`, unset it in
  `annotate.sh`'s environment through `QProcess` (not needed now).

### 2. `packaging/appimage/vidnote.desktop` (new)

Standard desktop entry: `Name=vidnote`, `Exec=vidnote %f`, `Icon=vidnote`,
`Type=Application`, `Categories=AudioVideo;Video;`, `Terminal=false`,
`MimeType=video/mp4;video/x-matroska;video/webm;video/quicktime;`.

### 3. `packaging/appimage/vidnote.png` (new)

256x256 placeholder icon, generated once and committed (small binary), for
example with
`ffmpeg -f lavfi -i "color=c=#ffd400:s=256x256" -frames:v 1 vidnote.png`.

### 4. `packaging/appimage/vidnote.appdata.xml` (new)

Minimal AppStream metadata (`id` `io.github.binbiriz.vidnote`, name, summary,
`project_license` placeholder `LicenseRef-proprietary` unless the repo has a
licence, `launchable desktop-id`). Required by the `python-appimage` recipe
layout.

### 5. `packaging/appimage/requirements.txt` (new)

```txt
PySide6-Essentials==6.8.*
```

Pins the Qt series for reproducible builds (confirm during implementation that a
`manylinux_2_28` wheel exists for that series and that the installed Qt has the
`xcb` and ffmpeg media plugins; adjust the series otherwise). `vidnote` itself
is not listed: it is added as extra data.

### 6. `packaging/appimage/build.sh` (new, executable)

`set -euo pipefail`, run from the repo root. Takes no arguments; reads the
version from `pyproject.toml` (`python3 -c "import tomllib..."` on 3.11+, a
`grep` fallback is not needed because CI uses 3.12 but local use of older Python
should print a clear message). Steps:

1. `python3 -m pip install python-appimage==<pinned version>` into a throwaway
   venv under `build/appimage/venv`.
2. Create `build/appimage/extra/` fresh and populate it:
   - `vidnote/`: copy of `src/vidnote` without `__pycache__` (keeps media and
     tests out of the image);
   - `annotate.sh`: copy of `scripts/annotate.sh`;
   - `extra-libs/`: `libxcb-cursor.so.0*` found with
     `ldconfig -p | grep libxcb-cursor`, plus any dependency of it that `ldd`
     reports as coming from a package that desktops usually lack (expected:
     `libxcb-render-util`, `libxcb-image`, `libxcb-util`; copy only libraries
     not provided by the manylinux base). Fail with a clear message if
     `libxcb-cursor` is missing (`sudo apt install libxcb-cursor0`).
3. Run
   `python-appimage build app -l manylinux_2_28_x86_64 -p 3.12 -x build/appimage/extra/* packaging/appimage`
   inside `build/appimage/work`, so the output lands there.
4. Locate the single produced `*.AppImage`; fail if there is none or more than
   one. Move it to `dist/vidnote-<version>-x86_64.AppImage`, `chmod +x`, print
   the path.

Exact flags (`-l` / `-p` spelling, the output file name, how `-x` handles
directories) are to be confirmed against `python-appimage build app -h` while
implementing; the final names above (`dist/vidnote-<version>-x86_64.AppImage`)
are the contract.

### 7. `.github/workflows/release.yml` (new)

```yaml
name: Release
on:
  workflow_dispatch:
    inputs:
      tag:
        description:
          "Release tag, vMAJOR.MINOR.PATCH (must match pyproject.toml)"
        required: true
        type: string
concurrency:
  group: release
  cancel-in-progress: false
permissions: {}
```

Only `workflow_dispatch` is listed, so no push or tag event can start it.

**Job `build`** (`runs-on: ubuntu-22.04`, `permissions: contents: read`,
`GH_TOKEN` for `gh`):

1. `actions/checkout@v4` (pinned to a major version).
2. `actions/setup-python@v5` with Python 3.12.
3. "Validate input" step with `env: TAG: ${{ inputs.tag }}` and
   `REF: ${{ github.ref }}`:
   - fail unless `REF == refs/heads/main`;
   - fail unless `TAG` matches `^v[0-9]+\.[0-9]+\.[0-9]+$` (message names the
     expected format and says suffixes such as `-rc1` are not accepted);
   - fail unless `${TAG#v}` equals the `version` read from `pyproject.toml` with
     `tomllib`;
   - fail if `git ls-remote --exit-code --tags origin "refs/tags/$TAG"`
     succeeds, or if `gh release view "$TAG"` succeeds.
4. `sudo apt-get update && sudo apt-get install -y ffmpeg fontconfig fonts-dejavu-core libxcb-cursor0`
   (ffmpeg and fonts for `tests/test_annotate_sh.py`; `libxcb-cursor0` for the
   bundle step and the smoke test).
5. `pip install -e ".[dev]"`, then `ruff check src tests`, then `pytest`.
6. `bash packaging/appimage/build.sh`.
7. Smoke test: fail unless `dist/vidnote-*-x86_64.AppImage` exists and is
   executable; run it with
   `QT_QPA_PLATFORM=offscreen timeout 10 dist/...AppImage --appimage-extract-and-run`
   and accept exit code `124` (still running, so the window opened) but fail on
   any other code. Also check the bundled files exist by extracting it
   (`--appimage-extract`) and testing `squashfs-root/annotate.sh` and
   `squashfs-root/vidnote/__main__.py`, and that no `*.mp4`/`*.mkv` is inside.
8. `actions/upload-artifact@v4` with the AppImage, `if-no-files-found: error`,
   `retention-days: 1`.

**Job `release`** (`needs: build`, `runs-on: ubuntu-22.04`,
`permissions: contents: write`, `env: GH_TOKEN: ${{ github.token }}`, `TAG`,
`SHA: ${{ github.sha }}`, `GH_REPO: ${{ github.repository }}` so no checkout is
needed):

1. `actions/download-artifact@v4`.
2. "Re-check" step: fail if the tag or a release for it now exists
   (`gh api repos/$GH_REPO/git/ref/tags/$TAG` succeeds, or `gh release view`
   succeeds).
3. "Create draft":
   `gh release create "$TAG" "$FILE" --draft --target "$SHA" --generate-notes --title "$TAG"`,
   with `id: draft` setting an output `created=true` afterwards. Not marked
   pre-release or latest-overridden.
4. "Publish": `gh release edit "$TAG" --draft=false`. Publishing creates the tag
   on `$SHA`.
5. "Cleanup on failure"
   (`if: failure() && steps.draft.outputs.created == 'true'`):
   `gh release delete "$TAG" --yes --cleanup-tag || true`. Because it only runs
   when this run created the draft, it never touches a pre-existing release or
   tag.
6. "Check asset": `gh release view "$TAG" --json assets` must list exactly one
   asset whose name ends in `-x86_64.AppImage` (fail otherwise; this runs before
   the cleanup step is skipped, so the failure also cleans up). Order: draft,
   check asset, publish, so a bad asset list never gets published.

### 8. `README.md`

- `## Requirements`: add a short "AppImage runtime requirements" note: the
  AppImage bundles Python and Qt but not `ffmpeg` (with `libfreetype`),
  `fontconfig` or fonts; install them with the existing `apt` line (minus
  `python3-venv`; `libxcb-cursor0` is bundled but harmless to install). Keep the
  existing requirements text.
- New section `## Releases and the AppImage` with:
  - for users: download `vidnote-<version>-x86_64.AppImage` from the Releases
    page, `chmod +x`, run `./vidnote-<version>-x86_64.AppImage [video]`; Ubuntu
    22.04 and newer (x86_64 only); without FUSE use
    `./vidnote-...AppImage --appimage-extract-and-run [video]` (or
    `APPIMAGE_EXTRACT_AND_RUN=1`); `VIDNOTE_SCRIPT` and `FONT` still work;
  - for maintainers: bump `version` in `pyproject.toml`, merge to `main`, run
    the **Release** workflow from the Actions tab (or
    `gh workflow run release.yml --ref main -f tag=v0.2.0`); the tag must be
    `vMAJOR.MINOR.PATCH` and equal the `pyproject.toml` version; the workflow
    fails (and creates nothing) for other refs, suffixes, existing tags or
    failing lint/tests; how to build locally with
    `./packaging/appimage/build.sh`.
- `## Project layout`: add `packaging/appimage/` and `.github/workflows/`.
- `## Troubleshooting`: add the AppImage FUSE hint.

### 9. `AGENTS.md`

Add `packaging/appimage/` to Architecture/Repo notes in one or two lines: the
recipe and `build.sh`, the AppImage sets `VIDNOTE_SCRIPT` to the bundled
`annotate.sh`, and the release workflow lives in
`.github/workflows/ release.yml` (manual trigger only, `main` only). Do not
touch the annotation format section.

## Out of Scope

- Windows, macOS, aarch64, and other Linux packages (deb, rpm, tarball, Flatpak,
  Snap).
- Bundling `ffmpeg`, `fontconfig` or fonts in the AppImage.
- Pre-releases and tag suffixes such as `-rc1`.
- Changing the version automatically, or bumping `pyproject.toml` from the
  workflow.
- Triggering on pushes, tags, schedules or pull requests; a separate CI workflow
  for lint and tests on every push.
- AppImage update information (zsync), signing, and publishing a checksum file
  (the release must contain exactly one asset).
- Any change to the app's Python code, the annotation format,
  `scripts/annotate.sh` or its tests.
- A final application icon (a placeholder is used).

## Verification

1. `ruff check src tests` and `pytest` still pass locally (nothing in `src/`
   changes).
2. Locally on Ubuntu 22.04 or newer with `libxcb-cursor0` installed, run
   `./packaging/appimage/build.sh`. It produces
   `dist/vidnote-0.1.0-x86_64.AppImage`, executable, and no other file in
   `dist/`.
3. Run `dist/vidnote-0.1.0-x86_64.AppImage` with no argument: the main window
   opens. Run it with a video path: the video loads. Add a text, a blur and an
   arrow annotation, press **Render**: the render dialog finishes with
   `Saved: ...` and the output video shows the annotations (this proves
   `annotate.sh` is found without the source tree). Run it from another
   directory with the repository moved or hidden to be sure.
4. Run it with `--appimage-extract-and-run` (and on a machine or container
   without FUSE): it starts. Without `libxcb-cursor0` installed on the host the
   window still opens (bundled library). Set `VIDNOTE_SCRIPT=/tmp/x.sh` and
   `FONT=...` and confirm they are honoured.
5. Extract it (`--appimage-extract`) and check that `annotate.sh` and `vidnote/`
   are present and that no `*.mp4`, `*.mkv` or `__pycache__` is inside.
6. On a fork or a test repository, run the **Release** workflow on `main` with a
   valid new tag whose version matches `pyproject.toml`: the release for the tag
   exists, is not a draft or pre-release, has generated notes, and has exactly
   one asset, `vidnote-<version>-x86_64.AppImage`. The tag points to the commit
   of the run.
7. Negative runs on the same repository, each must fail before building and
   leave no new tag, release or draft: run from a non-`main` branch; tag `0.1.0`
   (no `v`), `v0.1`, `v0.1.0-rc1`, empty, and `v1.2.3 x`; a tag whose version
   differs from `pyproject.toml`; the tag of the release created in step 6.
8. Force a failure in lint, in a test, in the AppImage build, and in the publish
   step (for example by making the asset check fail temporarily): no tag or
   release remains afterwards (the draft cleanup step ran).
9. Confirm the workflow file has only a `workflow_dispatch` trigger and that
   pushing a tag does not start it.
10. Confirm `README.md` explains how to publish a release and how to run the
    AppImage, including the runtime requirements and the no-FUSE option.

## Task List

- [ ] Create `packaging/appimage/entrypoint.sh`
- [ ] Create `packaging/appimage/vidnote.desktop`
- [ ] Generate and add `packaging/appimage/vidnote.png`
- [ ] Create `packaging/appimage/vidnote.appdata.xml`
- [ ] Create `packaging/appimage/requirements.txt` (confirm the pinned PySide6
      series has a `manylinux_2_28` wheel)
- [ ] Create `packaging/appimage/build.sh` (executable) and confirm the
      `python-appimage` flags and output name with `-h`
- [ ] Run `build.sh` locally and check the AppImage opens, loads a video and
      renders (Verification steps 2-5)
- [ ] Create `.github/workflows/release.yml` (`build` job: validation, lint,
      tests, build, smoke test, artifact)
- [ ] Add the `release` job to `.github/workflows/release.yml` (re-check, draft,
      asset check, publish, cleanup on failure)
- [ ] Update `README.md` (runtime requirements, releases and AppImage section,
      project layout, troubleshooting)
- [ ] Update `AGENTS.md` with the packaging and workflow notes
- [ ] Run `ruff check src tests` and `pytest`
- [ ] Run through the remaining Verification steps (workflow runs on a test
      repository, negative runs, failure cleanup, trigger check)
