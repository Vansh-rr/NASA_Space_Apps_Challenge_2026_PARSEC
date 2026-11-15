# Safe migration of the uploaded code branch

This archive is a full reorganized source snapshot, not an overlay to unzip into
an existing branch. Extract outside your repository and use the guarded migration.
The migration only touches paths present in the uploaded snapshot or new release;
it refuses conflicting files and preserves unrelated team work and downloaded data.

From the existing repo in Codespaces:

```bash
cd /workspaces/Nasa_Apps_2026
git status --short
# Use a new branch; commit/stash your own changes first if needed.
git switch -c phase2-organization
STAGING=$(mktemp -d "$HOME/parsec-organization.XXXXXX")
unzip -q PARSEC_Organized.zip -d "$STAGING"
python "$STAGING/PARSEC_Organized/tools/apply_organization.py" --target "$PWD"
```

Review the dry run. If there are conflicts, do not force overwrite; reconcile
those files with teammates first. If the dry run is clean:

```bash
python "$STAGING/PARSEC_Organized/tools/apply_organization.py" --target "$PWD" --apply
git status --short
git diff --stat
(cd phase2/algorithm && sha256sum -c SHA256SUMS)
python -m pip install -r requirements.txt
python phase2_test.py
```

This does not commit or push anything. Once the tests pass, review the changes and
stage only the intended source/documentation files, including removed duplicate
paths. Never add `.venv`, data, compiled files or secrets. The old untracked outputs
are deliberately not deleted. `git status` must be reviewed before committing.

If simply extracting a new working copy, the same archive works on its own:
`cd PARSEC_Organized`, install requirements, then `python phase2_test.py`.
