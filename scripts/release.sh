#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/release.sh <tag>"
  exit 1
fi

TAG="$1"

git tag "$TAG"
git push origin main
git push origin "$TAG"
gh release create "$TAG" --generate-notes
