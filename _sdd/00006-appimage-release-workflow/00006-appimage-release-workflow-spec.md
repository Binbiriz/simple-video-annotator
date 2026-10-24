# Spec for appimage-release-workflow

branch: opencode/feature/appimage-release-workflow

## Summary

Add a GitHub Actions workflow that publishes a vidnote release on demand. A
maintainer starts it manually and gives it a version tag. The workflow builds a
Linux AppImage of the desktop app, creates the tag and a GitHub Release, and
attaches the AppImage as the only release asset. Linux is the only target. No
Windows or macOS builds, and no other Linux packages (deb, rpm, tarball and so
on).

## Functional Requirements

- The workflow runs only when started by hand from the GitHub Actions UI or CLI
  (manual trigger). Pushing a tag or a commit does not start it.
- The manual trigger takes the release tag as an input (for example `v0.2.0`).
- The workflow checks that the tag has an accepted format (a `v`-prefixed
  version number) and fails early with a clear message if it does not.
- The workflow fails early if the tag already exists in the repository or if a
  release for it already exists. It never overwrites an existing release or
  moves an existing tag.
- The workflow creates the tag on the commit it was started from. The release is
  published for that tag.
- The workflow builds a single AppImage for Linux x86_64 from the repository
  sources.
- The AppImage contains the app, the Python runtime, the PySide6 dependencies,
  and `scripts/annotate.sh`, so that **Render** works from inside the AppImage
  and not only from a source checkout.
- The AppImage starts the same `vidnote` entry point as `./run.sh`, passes
  through an optional video path argument, and keeps working with the existing
  `VIDNOTE_SCRIPT` and `FONT` environment variables.
- The release is a regular GitHub Release for the tag. It has generated release
  notes and the AppImage as its only uploaded asset.
- The AppImage file name contains the app name, the version taken from the tag,
  and the architecture (for example `vidnote-0.2.0-x86_64.AppImage`). The file
  is marked executable.
- The workflow runs the existing lint and test commands before building and does
  not publish a release if they fail.
- The workflow needs only the repository permissions required to create tags and
  releases, and no extra secrets.
- `README.md` gets a short section on how to cut a release (run the workflow
  with a tag) and how to run the downloaded AppImage. The README keeps the
  existing note that `ffmpeg` (with `libfreetype`) and `fontconfig` are runtime
  requirements, unless the AppImage provides them (see Open Questions).

## Possible Edge Cases

- The tag input is empty, has no `v` prefix, has spaces, or is not a version
  number.
- The tag or release already exists.
- The workflow is started from a branch other than `main`. The tag would point
  at that branch's commit.
- Two runs for the same tag are started at the same time.
- The version in `pyproject.toml` differs from the version in the tag.
- The AppImage build fails or produces no file. No tag and no release may be
  left behind in that case.
- The release creation fails after the tag was created. The tag should not stay
  orphaned.
- Qt platform plugins fail to load inside the AppImage because of missing xcb
  libraries (the app needs `libxcb-cursor0` today).
- The AppImage needs FUSE to run. Machines without FUSE should still have a
  documented way to run it (extract-and-run).
- `annotate.sh` is looked up relative to the source tree today. Inside an
  AppImage that path may not exist, so the script must still be found.
- `ffmpeg` on the user's machine may lack `drawtext` (libfreetype). The AppImage
  cannot fix this unless it bundles its own ffmpeg.
- The build runner image is newer than some target distributions. The AppImage
  may then not run on older glibc versions.
- Sample media files (`*.mp4`, `*.mkv`) are gitignored and must not end up in
  the AppImage or in the release.

## Acceptance Criteria

- Starting the workflow manually with a valid new tag produces a GitHub Release
  for that tag containing exactly one asset, a Linux x86_64 `.AppImage`.
- The workflow cannot be started by a tag push or any other event.
- Starting the workflow with an invalid tag, or a tag that already exists, fails
  before building and creates no tag or release.
- If lint, tests or the build fail, no tag or release is created.
- The downloaded AppImage runs on a typical desktop Linux with `ffmpeg` and
  `fontconfig` installed. It opens the main window, loads a video, and renders
  an annotated video through **Render** without needing the source tree.
- The AppImage runs when started with a video path argument and when started
  without one.
- The release page lists no source-only or non-Linux binary assets from this
  workflow. GitHub's automatic source archives are acceptable.
- `README.md` explains how to publish a release and how to run the AppImage.
- The existing `pytest` and `ruff check src tests` commands still pass.

## Open Questions

- Should the AppImage bundle its own `ffmpeg` (with `libfreetype`) and fonts, or
  keep requiring them on the user's machine as the README does today? Bundling
  makes the file much bigger. ANSWER: no bundle. add a section to the README
  about the runtime requirements.
- Which commit should a release use: only `main`, or whatever ref the workflow
  was started from? ANSWER: only main. the workflow should check that the ref is
  main and fail otherwise.
- Should the workflow require the tag's version to match `version` in
  `pyproject.toml`, or should it set the version from the tag? ANSWER: make the
  workflow check that the tag's version matches `pyproject.toml` and fail if
  not.
- Is x86_64 the only architecture needed, or is aarch64 wanted too? ANSWER: now
  only x86_64, aarch64 can be added later if needed.
- Should releases be marked as pre-release when the tag has a suffix such as
  `-rc1`, or should the manual trigger ask for it explicitly? ANSWER: no
  pre-release, the workflow should fail >if the tag has a suffix.
- Is the oldest supported Linux distribution known (this decides the build
  runner image and glibc baseline)? ANSWER: ubuntu-22.04 and newer.
