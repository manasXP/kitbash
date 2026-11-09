# Epicura

Epicura's project map, playbooks, CLAUDE files and reviewed plugin builds are private. They live in the private `manasXP/kitbash-projects` repo, checked out at `private/projects/` in this repo, which is gitignored. A plain `validate.py` checks them when that checkout is present.

From `catalog/`:

```sh
/usr/bin/python3 scripts/release.py check ../private/projects/epicura
```

See the Release section of [catalog/README.md](../../catalog/README.md). An earlier copy of the map lived here until 9 Nov 2026 and named repos that no longer exist. It remains in the git history.
