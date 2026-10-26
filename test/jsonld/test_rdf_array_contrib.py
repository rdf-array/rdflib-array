"""rdf-array: the shared JSON-LD tests of json-ld-api-contrib
(https://github.com/rdf-array/json-ld-api-contrib), copied into
test/data/suites/rdf-array/json-ld-api-contrib/ (see test/data/suites/rdf-array/README.md):
a @list is one sequence term on the way to RDF, and a sequence is written as @list on
the way back."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pytest import MonkeyPatch

from test.data import TEST_DATA_DIR

from . import runner

TC_BASE = "https://rdf-array.github.io/json-ld-api-contrib/tests/"
TESTS_DIR = TEST_DATA_DIR / "suites/rdf-array/json-ld-api-contrib/tests"
MANIFESTS = {"toRdf": runner.do_test_parser, "fromRdf": runner.do_test_serializer}


def cases() -> list[Any]:
    params = []
    for direction, func in MANIFESTS.items():
        manifest = json.loads((TESTS_DIR / f"{direction}-manifest.jsonld").read_text())
        for test in manifest["sequence"]:
            category, num = test["input"].split(".")[0].rsplit("-", 1)[0].split("/")
            params.append(
                pytest.param(
                    func, category, num, test["input"], test["expect"], test.get("context", False),
                    test.get("option") or {}, id=f"{direction}-manifest{test['@id']}",
                )
            )
    return params


@pytest.mark.parametrize("func, cat, num, inputpath, expectedpath, context, options", cases())
def test_contrib(monkeypatch: MonkeyPatch, func, cat, num, inputpath, expectedpath, context, options) -> None:
    monkeypatch.chdir(TESTS_DIR)
    func(TC_BASE, cat, num, inputpath, expectedpath, context, options)
