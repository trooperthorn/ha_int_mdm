#!/usr/bin/env bash
# Downloads the current Companion release APK for the given flavor and
# verifies it against the digest GitHub publishes for the asset, so the
# provisioning scripts always push a known-good build.
#
#   scripts/fetch_companion_apk.sh <full|minimal> [outdir]
#
# full    - stock Android / Device Owner tablets (Samsung, Pixel), has
#           Google Play services and the Firebase push transport.
# minimal - Fire OS tablets (lite tier), no Google services, no push.
set -euo pipefail
flavor="${1:?flavor: full or minimal}"
outdir="${2:-.}"
case "$flavor" in
  full|minimal) ;;
  *) echo "flavor must be 'full' or 'minimal', got '$flavor'" >&2; exit 2 ;;
esac

asset="app-${flavor}-release.apk"
tag=$(gh release list --repo home-assistant/android --limit 1 | cut -f1)
info=$(gh api "repos/home-assistant/android/releases/tags/$tag" --jq ".assets[] | select(.name==\"$asset\")")
url=$(echo "$info" | jq -r '.browser_download_url')
digest=$(echo "$info" | jq -r '.digest' | sed 's/^sha256://')

out="$outdir/$asset"
echo "Fetching $asset from release $tag"
curl -fsSL -o "$out" "$url"

got=$(sha256sum "$out" | cut -d' ' -f1)
if [ "$got" != "$digest" ]; then
  echo "Checksum mismatch for $out: expected $digest, got $got" >&2
  rm -f "$out"
  exit 1
fi
echo "Verified $out (sha256 $got), release $tag"
echo "$out"
