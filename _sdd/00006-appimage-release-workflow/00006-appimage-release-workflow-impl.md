# Implementation: appimage-release-workflow

Plan:
`_sdd/00006-appimage-release-workflow/00006-appimage-release-workflow-plan.md`

## Task List

- [x] Create `packaging/appimage/entrypoint.sh`
- [x] Create `packaging/appimage/vidnote.desktop`
- [x] Generate and add `packaging/appimage/vidnote.png`
- [x] Create `packaging/appimage/vidnote.appdata.xml`
- [x] Create `packaging/appimage/requirements.txt` (confirm the pinned PySide6
      series has a `manylinux_2_28` wheel)
- [x] Create `packaging/appimage/build.sh` (executable) and confirm the
      `python-appimage` flags and output name with `-h`
- [x] Run `build.sh` locally and check the AppImage opens, loads a video and
      renders (Verification steps 2-5)
- [x] Create `.github/workflows/release.yml` (`build` job: validation, lint,
      tests, build, smoke test, artifact)
- [x] Add the `release` job to `.github/workflows/release.yml` (re-check, draft,
      asset check, publish, cleanup on failure)
- [x] Update `README.md` (runtime requirements, releases and AppImage section,
      project layout, troubleshooting)
- [x] Update `AGENTS.md` with the packaging and workflow notes
- [ ] Run `ruff check src tests` and `pytest`
- [ ] Run through the remaining Verification steps (workflow runs on a test
      repository, negative runs, failure cleanup, trigger check)

## Implementation Summary

- `packaging/appimage/entrypoint.sh`, `vidnote.desktop`, `vidnote.png` (256x256
  plain yellow placeholder), `vidnote.appdata.xml`: the `python-appimage` recipe
  as planned. The entry point sets `VIDNOTE_SCRIPT` (unless already set),
  `LD_LIBRARY_PATH` (`extra-libs`) and `PYTHONPATH`, then runs
  `python -s -m vidnote "$@"`.
- `packaging/appimage/requirements.txt`: `PySide6==6.8.*`.
- `packaging/appimage/build.sh` (executable): reads the version from
  `pyproject.toml`, installs `python-appimage==1.4.6` in `build/appimage/venv`,
  stages `vidnote/` (no `__pycache__`), `annotate.sh` and `extra-libs/`
  (`libxcb-cursor`, `libxcb-render-util`, `libxcb-image`, `libxcb-util`), builds
  on `manylinux_2_28_x86_64` with Python 3.12 and moves the result to
  `dist/vidnote-<version>-x86_64.AppImage`.
- `.github/workflows/release.yml`: `workflow_dispatch` only, `tag` input, global
  `release` concurrency group, `permissions: {}` at the top. Job `build`
  (`contents: read`): validates ref/tag format/version/existing tag and release,
  installs system packages, lint + tests, builds, smoke-tests, uploads the
  artifact. Job `release` (`contents: write`): re-checks, creates a draft
  release with `--target $SHA`, checks the asset list, publishes; a cleanup step
  removes the release and tag when the run failed after it started creating the
  draft.
- `README.md`: AppImage runtime requirements, new "Releases and the AppImage"
  section, project layout and troubleshooting entries.
- `AGENTS.md`: one Architecture bullet for `packaging/appimage/` and the release
  workflow.

## Verification Results

**Verification failed:** step 1, `ruff check src tests` reports 104 errors with
the ruff 0.17.2 installed in `.venv` (mostly `UP006`/`UP035`/`UP045` typing
rules, `C408`, `PLW1510`). Nothing under `src/` or `tests/` was changed by this
work, so these errors exist without it. The `build` job of the new workflow
installs `.[dev]` (`ruff>=0.4`, so the newest ruff) and runs the same command,
so it would fail at the lint step with this ruff version until the lint findings
are fixed or ruff is pinned or configured. Not fixed here (changing the Python
code is out of scope and the skill says no fix-and-retry loop).

1- `pytest`: pass, 220 passed.

2- `./packaging/appimage/build.sh`: pass, produces
`dist/vidnote-0.1.0-x86_64.AppImage` (executable, the only file in `dist/`,
about 235 MB).

3- Partly checked. The AppImage with and without a video path
(`QT_QPA_PLATFORM=offscreen`, plus a run on the real `:0` display) stays running
until the 8 s timeout (exit 124) and Qt reports the FFmpeg multimedia backend.
Rendering was checked by running the bundled `annotate.sh` (found through
`VIDNOTE_SCRIPT`/`find_script()` from the extracted image, from `/`, with
`PYTHONPATH` pointing at the extracted image so the source tree was not used) on
a generated test video with a blur, a text and an arrow annotation: exit 0,
`out.mp4` written. The **Render** button itself was not clicked.

4- Partly checked: `--appimage-extract-and-run` starts (exit 124). Not checked:
a machine without FUSE, a host without `libxcb-cursor0` (the bundled copy is
present in `extra-libs` and `ldd` of `libqxcb.so` with that path reports nothing
missing), and setting `FONT` or a custom `VIDNOTE_SCRIPT` through the AppImage.

5- Pass: the extracted image has `annotate.sh`, `vidnote/` and `extra-libs/`, no
`*.mp4`/`*.mkv` and no `__pycache__` under `vidnote/`.

6-8- Not run: they need workflow runs on a GitHub fork or test repository. The
workflow YAML parses and every `run:` block passes `bash -n`; the tag regex was
checked locally and rejects `0.1.0`, `v0.1`, `v0.1.0-rc1`, an empty tag,
`v1.2.3 x` and a tag with a newline. `actionlint` is not installed.

9- Pass by inspection: the only trigger in `release.yml` is `workflow_dispatch`.
Not tested by pushing a tag.

10- Pass by inspection: the README covers publishing, running the AppImage, the
runtime requirements and the no-FUSE option.

## Deviations

- `requirements.txt` pins `PySide6==6.8.*` instead of
  `PySide6-Essentials==6.8.*`: `QtMultimedia` is not in the Essentials wheel
  (the first build failed with `No module named 'PySide6.QtMultimedia'`). The
  full wheel makes the AppImage about 235 MB.
- The output name from `python-appimage` is `<Name>-<arch>.AppImage`, so
  `build.sh` renames it to `vidnote-<version>-x86_64.AppImage`. `-x` takes
  several paths, so the `appdir` argument is placed before it.
- Release job: the asset check and publishing use the REST API through `gh api`
  and the release id instead of `gh release view`/`gh release edit` by tag,
  because looking up a draft by tag is unreliable. The tag/release existence
  checks use `gh release list` (this also sees drafts in the `release` job) and
  `git ls-remote` output instead of exit codes. The cleanup step is gated on a
  `started` output set after the re-check, so it can never delete a pre-existing
  release or tag.
- The CI package list also installs `libegl1 libgl1 libxkbcommon0` for the
  offscreen smoke test.
- Not done (left unchecked): `ruff check src tests` passing, and the
  verification steps that need GitHub (6-8) plus the manual checks listed under
  step 3 and 4.
