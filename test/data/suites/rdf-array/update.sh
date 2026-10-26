#!/bin/sh
# rdf-array: refresh the vendored copies of the shared contrib suites, as test/data/suites/w3c holds
# copies of the W3C suites: rdf-tests-contrib (rdf/, sparql/) and json-ld-api-contrib (tests/).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for repo in rdf-tests-contrib json-ld-api-contrib; do
  git clone --quiet --depth 1 "https://github.com/rdf-array/$repo.git" "$tmp/$repo"
  git -C "$tmp/$repo" rev-parse HEAD > "$here/$repo.commit"
done
rm -rf "$here/rdf-tests-contrib" "$here/json-ld-api-contrib"
mkdir -p "$here/rdf-tests-contrib" "$here/json-ld-api-contrib"
cp -R "$tmp/rdf-tests-contrib/rdf" "$tmp/rdf-tests-contrib/sparql" "$here/rdf-tests-contrib/"
cp -R "$tmp/json-ld-api-contrib/tests" "$here/json-ld-api-contrib/"
rm -rf "$here/json-ld-api-contrib/tests/array" "$here/json-ld-api-contrib/tests/array-manifest.jsonld"
