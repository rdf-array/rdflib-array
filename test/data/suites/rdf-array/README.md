# The rdf-array contrib suites

Copies of [rdf-tests-contrib](https://github.com/rdf-array/rdf-tests-contrib) (`rdf/`, `sparql/`)
and [json-ld-api-contrib](https://github.com/rdf-array/json-ld-api-contrib) (`tests/`, without the
JSON-LD-array tests, which need a JSON-LD-array processor): the tests every rdf-array implementation
shares and no W3C suite contains. `*.commit` records the commit each was copied from; `update.sh`
refreshes them. Do not edit the copies; change the contrib repositories and copy again.

Run by `test/test_w3c_spec/test_rdf_array_contrib.py` and `test/jsonld/test_rdf_array_contrib.py`.
