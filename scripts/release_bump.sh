#!/usr/bin/env bash
set -euo pipefail

# Prepare a clean release bump by normalizing hash-suffixed versions.
PART="${1:-patch}"
MESSAGE_TEMPLATE="${2:-incrementing version to {new_version}}"

git add .
if ! git diff --staged --quiet; then
  git commit -m "pre-release: staging changes"
fi

CURRENT_VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
BASE_VERSION="${CURRENT_VERSION%%+g*}"

if [[ "${CURRENT_VERSION}" != "${BASE_VERSION}" ]]; then
  # Normalize pyproject version before bumpversion search/replace.
  python3 -c "from pathlib import Path; import sys; old_version = sys.argv[1]; new_version = sys.argv[2]; file_path = Path('pyproject.toml'); source = file_path.read_text(); old_line = f'version = \"{old_version}\"'; new_line = f'version = \"{new_version}\"'; assert old_line in source, f'Missing {old_line} in pyproject.toml'; file_path.write_text(source.replace(old_line, new_line, 1))" "${CURRENT_VERSION}" "${BASE_VERSION}"
fi

IFS=. read -r MAJOR MINOR PATCH <<< "${BASE_VERSION}"
case "${PART}" in
  major) NEW_VERSION="$((MAJOR + 1)).0.0" ;;
  minor) NEW_VERSION="${MAJOR}.$((MINOR + 1)).0" ;;
  patch) NEW_VERSION="${MAJOR}.${MINOR}.$((PATCH + 1))" ;;
  *) echo "Unsupported part: ${PART}" >&2; exit 1 ;;
esac

MESSAGE="${MESSAGE_TEMPLATE//\{new_version\}/${NEW_VERSION}}"
bumpversion --current-version "${BASE_VERSION}" --new-version "${NEW_VERSION}" "${PART}" --no-commit --no-tag
git add -A
git commit -m "${MESSAGE}"
git tag "v${NEW_VERSION}"
git push origin HEAD --tags
