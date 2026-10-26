"""rdf-array: the shared tests of rdf-tests-contrib (https://github.com/rdf-array/rdf-tests-contrib),
copied into test/data/suites/rdf-array/ (see its README): Turtle-, TriG-, N-Triples- and N-Quads-array
syntax and evaluation, and SPARQL-array evaluation, update, syntax and results."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack
from typing import Optional

import pytest
from pytest import MonkeyPatch

from rdflib import Namespace, URIRef
from test.data import TEST_DATA_DIR
from test.test_w3c_spec import test_nquads_w3c, test_nt_w3c, test_trig_w3c, test_turtle_w3c
from test.utils import ensure_suffix
from test.utils.dawg_manifest import ManifestEntry, MarksDictType, params_from_sources
from test.utils.iri import URIMapper
from test.utils.namespace import MF
from test.utils.sparql_checker import SKIP_TYPES, SPARQLEntry, check_entry, ctx_configure_rdflib

REMOTE_BASE_IRI = "https://rdf-array.github.io/rdf-tests-contrib/"
LOCAL_BASE_DIR = TEST_DATA_DIR / "suites/rdf-array/rdf-tests-contrib/"
MAPPER = URIMapper.from_mappings((REMOTE_BASE_IRI, ensure_suffix(LOCAL_BASE_DIR.as_uri(), "/")))

SYNTAXES = {
    "rdf-turtle": test_turtle_w3c.check_entry,
    "rdf-trig": test_trig_w3c.check_entry,
    "rdf-n-triples": test_nt_w3c.check_entry,
    "rdf-n-quads": test_nquads_w3c.check_entry,
}

# rdflib keeps "x"^^xsd:string apart from "x" everywhere, not only in a sequence (RDF 1.0 behaviour)
SYNTAX_MARKS: MarksDictType = {
    f"{REMOTE_BASE_IRI}rdf/rdf-turtle/#seq-literal-kinds": pytest.mark.xfail(
        reason='rdflib keeps "x"^^xsd:string and "x" as different literals, at any position'
    ),
}

# The SPARQL-array this engine does not have, by the feature a test requires
RA = Namespace("https://rdf-array.github.io/rdf-array/vocab#")
MF_REQUIRES = URIRef("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#requires")
UNSUPPORTED = {
    RA.PositionPatterns: "rdf-array: no position patterns ((e))[i], [?i], [*] (rdf-array/rdf-array#8)",
    RA.SequenceFunctions: "rdf-array: no sequence functions isSEQ, SEQLEN, SEQ, x[i] (rdf-array/rdf-array#8)",
}
SPARQL_MARKS: MarksDictType = {}


def unsupported(entry: SPARQLEntry) -> Optional[pytest.MarkDecorator]:
    """xfail a test needing a feature this engine lacks; a negative syntax test still runs,
    since rejecting the query is what it asks"""
    if entry.type in (MF.NegativeSyntaxTest11, MF.NegativeUpdateSyntaxTest11):
        return None
    for feature in entry.graph.objects(entry.identifier, MF_REQUIRES):
        if feature in UNSUPPORTED:
            return pytest.mark.xfail(reason=UNSUPPORTED[feature], strict=True)
    return None


@pytest.mark.parametrize(
    ["syntax", "manifest_entry"],
    [
        pytest.param(syntax, *param.values, marks=param.marks, id=param.id)
        for syntax in SYNTAXES
        for param in params_from_sources(
            MAPPER,
            ManifestEntry,
            LOCAL_BASE_DIR / "rdf" / syntax / "manifest.ttl",
            mark_dict=SYNTAX_MARKS,
        )
    ],
)
def test_syntax_entry(syntax: str, manifest_entry: ManifestEntry) -> None:
    SYNTAXES[syntax](manifest_entry)


@pytest.fixture(scope="module")
def configure_rdflib() -> Generator[None, None, None]:
    with ctx_configure_rdflib():
        yield None


@pytest.mark.usefixtures("configure_rdflib")
@pytest.mark.parametrize(
    ["manifest_entry"],
    [
        param
        for suite in ("eval", "update", "syntax-query", "results")
        for param in params_from_sources(
            MAPPER,
            SPARQLEntry,
            LOCAL_BASE_DIR / "sparql" / suite / "manifest.ttl",
            mark_dict=SPARQL_MARKS,
            markers=(
                lambda entry: pytest.mark.skip(reason="tester not implemented") if entry.type in SKIP_TYPES else None,
                unsupported,
            ),
        )
    ],
)
def test_sparql_entry(monkeypatch: MonkeyPatch, exit_stack: ExitStack, manifest_entry: SPARQLEntry) -> None:
    check_entry(monkeypatch, exit_stack, manifest_entry)
