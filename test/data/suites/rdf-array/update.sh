#!/bin/sh
# rdf-array: refresh the vendored copies of the shared contrib suites, as test/data/suites/w3c holds
# copies of the W3C suites: rdf-tests-contrib (rdf/, sparql/) and json-ld-api-contrib (tests/).
#
#   update.sh [RDF_TESTS_CONTRIB_DIR [JSON_LD_API_CONTRIB_DIR]]
#
# Each suite is cloned from GitHub, or copied from the local checkout given (its HEAD is the
# commit recorded; uncommitted changes in it come along).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fetch() { # fetch REPO [LOCAL_DIR [BRANCH]]
  if [ -n "${2:-}" ]; then
    cp -R "$2" "$tmp/$1"
  else
    git clone --quiet --depth 1 ${3:+--branch "$3"} "https://github.com/rdf-array/$1.git" "$tmp/$1"
  fi
  git -C "$tmp/$1" rev-parse HEAD > "$here/$1.commit"
}
fetch rdf-tests-contrib "${1:-}" rdf-undef
fetch json-ld-api-contrib "${2:-}" rdf-undef
rm -rf "$here/rdf-tests-contrib" "$here/json-ld-api-contrib"
mkdir -p "$here/rdf-tests-contrib" "$here/json-ld-api-contrib"
cp -R "$tmp/rdf-tests-contrib/rdf" "$tmp/rdf-tests-contrib/sparql" "$here/rdf-tests-contrib/"
cp -R "$tmp/json-ld-api-contrib/tests" "$here/json-ld-api-contrib/"
rm -rf "$here/json-ld-api-contrib/tests/array" "$here/json-ld-api-contrib/tests/array-manifest.jsonld"
for api in expand compact flatten; do  # rdf-undef: these run in jsonld.js-array; rdflib has no such API
  rm -rf "$here/json-ld-api-contrib/tests/$api" "$here/json-ld-api-contrib/tests/$api-manifest.jsonld"
done
