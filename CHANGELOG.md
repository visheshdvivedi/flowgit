# Changelog

All notable changes to flowgit are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] - 2026-08-02

First hardened release: fixes every bug found during a full test-hardening
pass, brings the object format into byte-for-byte compatibility with real
git, and adds filesystem-based remote sync (`remote`, `clone`, `fetch`,
`pull`, `push`).

### Added

- Full pytest suite (154 tests) covering every object type (blob, tree,
  commit, tag, index) and the `Repository` class (init, object store, index
  operations, refs/branches, add/commit/status/diff/restore, switch/checkout,
  merge, log, remote sync), with dedicated fixtures for isolated repos and
  multi-repo (local + remote) scenarios.
- Config generalization: `FlowGitConfigManager` gained `set_value`,
  `get_value`, `remove_section`, and `is_section_exist`, so config sections
  beyond `[user]`/`[core]` can be added/read/removed without wiping the rest
  of the file.
- `remote` command: `add` / `remove` / `list` / `get-url` / `set-url`,
  storing remote definitions as `[remote "<name>"]` sections in
  `.flowgit/config`.
- `clone` (filesystem remotes): recreates a full repository from another
  flowgit repo's path, including every branch, by walking each branch's
  commit graph and copying every reachable blob/tree/commit object.
- `fetch` (filesystem remotes): updates `refs/remotes/<remote>/<branch>` to
  reflect a remote's current state and copies any new objects, without
  touching the local branch or working tree.
- `pull` (filesystem remotes): fetch, then merge the fetched
  remote-tracking ref into whatever branch is actually checked out (fast-
  forward, three-way merge, or conflict, reusing the same merge core as
  `merge`).
- `push` (filesystem remotes): copies new local commits to a remote's
  object store and updates its branch ref, with a non-fast-forward check
  that refuses to push if the remote has moved since the last fetch.
- `[core]` section (`repositoryformatversion`, `filemode`, `bare`,
  `logallrefupdates`, `ignorecase`, `precomposeunicode`) written on init, so
  a real `git` binary recognizes `.flowgit` as a well-formed repository.

### Fixed

Object format and serialization:
- Commit timestamps were silently replaced with the current time every time
  a commit was read back from disk; now the original timestamp round-trips
  correctly.
- Tag objects were completely broken: `deserialize()` crashed on a
  bytes/str mismatch, had no `return` statement, never captured the message
  body, and mis-parsed multi-word tagger names. All fixed; tags now
  serialize/deserialize/round-trip correctly, including timestamp and
  timezone.
- Tree objects included a git-incompatible extra `type` field in their wire
  format, and had a mode-type (`str` vs `int`) inconsistency that crashed
  `maketree` and broke round-tripping through `clone`. Both fixed.
- Multi-word author/committer names broke commit parsing (silently
  shifting every subsequent field); fixed to handle names of any length.
- `read_object()` had no handling for tag objects at all - reading a tag
  back silently returned its raw sha string instead of a usable object.
- `make_tag()` referenced a class that no longer existed after a rename,
  and always wrote a blank timestamp/timezone (not a valid git tag object).

Repository operations:
- `initalize_flowgit(replace=True)` crashed trying to `os.remove()` a
  directory; now uses `shutil.rmtree`.
- Several methods (`restore`, `diff`, `_get_unstaged_changes_status`,
  `update_index`) silently assumed `self.path == os.getcwd()` and broke
  when that wasn't true.
- `_is_file_modified()` only compared file size and whole-second mtime,
  missing same-size edits made within the same second - now falls back to
  a content-hash comparison when the cheap check is ambiguous.
- `merge()` crashed on any merge that introduced a file new to the current
  branch (reading from the working tree instead of the object store), and
  a second bug in the index-folding step both mutated a dict while
  iterating over it and silently dropped genuinely new paths from the
  final index.
- `merge()` never actually deleted files removed by a three-way merge from
  the working directory.
- `log()` only ever walked the first-parent chain, so merge commits' other
  parents - and anything unique to a merged-in branch - were never shown.
- `_list_all_branches()` raised an undefined name (`ValidationError`)
  instead of a real exception when `refs/heads` was missing.
- `restore(staged=True)` / `diff(staged=True)` crashed on a repository with
  no commits yet instead of failing gracefully.
- `create_index_entry_from_sha()` called `exit(0)` on a missing object
  (hard-killing the process) and hardcoded every entry's mode to a symlink
  mode regardless of the real file type.
- Fixed a Python 3.9 import-time crash (`str | None` union syntax requires
  3.10+) via `from __future__ import annotations`, restoring compatibility
  with the project's declared minimum Python version.

### Changed

- Tree, commit, and tag object formats now match real git's byte-for-byte,
  validated with `git fsck --full` and real `git log`/`git push`/`git pull`
  pointed at `.flowgit` via `--git-dir`.

### Known issues (carried forward, not yet fixed)

- `clone()`'s empty-directory check uses the process's current working
  directory instead of the target repository path.
- `clone`/`fetch` hardcode checking out a branch named `main` rather than
  reading the remote's actual default branch.
- `pull` does not guard against running while in a detached HEAD state.
- `push` cannot create a brand-new branch on a remote that has never been
  fetched - it can only update a branch the remote already has.
- Commits carrying a GPG signature (`gpgsig` header, e.g. commits made via
  GitHub's web UI) do not round-trip byte-for-byte - the signature block is
  dropped during parsing.
- Some early scaffolding for an alternate fetch implementation
  (`fetch()`, `_fetch_from_filesystem()`, `_get_remote_type()`) is
  non-functional and unused; superseded by `fetch_remote()`.

## [2.0.0] - Planned

- HTTPS/SSH-based `clone`, `fetch`, `pull`, and `push` against real remotes
  (e.g. GitHub), building on the git-format compatibility already in place.
