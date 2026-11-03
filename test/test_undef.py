"""rdf-undef: the empty slot of a sequence, ``( 1 undef 3 )``: a position with no value,
an element of a sequence and nothing else. The behaviours of jena-array's TestUndefSlots
that the shared rdf-tests-contrib cases (``undef-*``) do not reach, and the Python API."""

from __future__ import annotations

import copy
import io
import pickle

import pytest
from pyparsing import ParseException

from rdflib import UNDEF, BNode, Dataset, Graph, Literal, Namespace, Sequence
from rdflib.compare import isomorphic
from rdflib.plugins.sparql.results.jsonresults import parseJsonTerm, termToJSON
from rdflib.plugins.sparql.results.tsvresults import TSVResultParser
from rdflib.query import Result
from rdflib.term import Node, Undef, Variable

EX = Namespace("http://example/")
DATA = """@prefix : <http://example/> .
:x :p (1 undef 3) .
:y :p (1 2 3) .
:z :p (undef undef) .
:v :w 5 .
"""
X_SEQ = Sequence([Literal(1), UNDEF, Literal(3)])


def data() -> Graph:
    return Graph().parse(data=DATA, format="turtle")


def query(q: str, g: Graph | None = None) -> list[dict]:
    res = (g if g is not None else data()).query("PREFIX : <http://example/>\n" + q)
    return [{str(k): v for k, v in b.items()} for b in res.bindings]


class TestTerm:
    def test_one_object(self) -> None:
        assert Undef() is UNDEF
        assert pickle.loads(pickle.dumps(UNDEF)) is UNDEF
        assert copy.deepcopy(UNDEF) is UNDEF
        assert isinstance(UNDEF, Node) and not isinstance(UNDEF, str)

    def test_equal_only_to_itself(self) -> None:
        assert UNDEF == UNDEF
        for other in (Literal("undef"), EX.undef, BNode("undef"), Variable("undef"), "undef", None):
            assert UNDEF != other and other != UNDEF

    def test_counts_and_lines_up(self) -> None:
        assert len(X_SEQ) == 3 and X_SEQ[1] is UNDEF
        assert Sequence([Literal(1), UNDEF]) == Sequence([Literal(1), UNDEF])
        for other in (
            Sequence([Literal(1)]),
            Sequence([UNDEF, Literal(1)]),
            Sequence([Literal(1), Literal(2)]),
            Sequence([Literal(1), Literal("undef")]),
        ):
            assert Sequence([Literal(1), UNDEF]) != other

    def test_spelling_and_python_value(self) -> None:
        assert Sequence([UNDEF, Sequence([UNDEF])]).n3() == "(undef (undef))"
        assert X_SEQ.toPython() == (1, None, 3)
        assert pickle.loads(pickle.dumps(X_SEQ)) == X_SEQ

    def test_a_triple_refuses_it(self) -> None:
        for triple in ((UNDEF, EX.p, EX.o), (EX.s, UNDEF, EX.o), (EX.s, EX.p, UNDEF)):
            with pytest.raises(ValueError, match="undef"):
                Graph().add(triple)
            with pytest.raises(ValueError, match="undef"):
                Dataset().add(triple)
        Graph().add((EX.s, EX.p, Sequence([UNDEF])))

    def test_graph_api_shows_the_slot(self) -> None:
        g = Graph().add((EX.s, EX.p, X_SEQ))
        assert list(g.items(g.value(EX.s, EX.p))) == [Literal(1), UNDEF, Literal(3)]


class TestSyntaxes:
    @pytest.mark.parametrize(
        "fmt,reader", [("turtle", "turtle"), ("n3", "n3"), ("nt", "nt"), ("longturtle", "turtle")]
    )
    def test_graph_round_trip(self, fmt: str, reader: str) -> None:
        g = data()
        text = g.serialize(format=fmt)
        assert "undef" in text
        assert isomorphic(Graph().parse(data=text, format=reader), g)

    @pytest.mark.parametrize("fmt", ["trig", "nquads"])
    def test_dataset_round_trip(self, fmt: str) -> None:
        ds = Dataset()
        ds.graph(EX.g).parse(data=DATA, format="turtle")
        text = ds.serialize(format=fmt)
        assert "undef" in text
        ds2 = Dataset().parse(data=text, format=fmt)
        assert (EX.x, EX.p, X_SEQ, EX.g) in ds2

    def test_blank_nodes_beside_slots_are_canonicalised(self) -> None:
        a = Graph().parse(data="<http://e/s> <http://e/p> (_:a undef) .", format="turtle")
        b = Graph().parse(data="<http://e/s> <http://e/p> (_:b undef) .", format="turtle")
        c = Graph().parse(data="<http://e/s> <http://e/p> (_:b 1) .", format="turtle")
        assert isomorphic(a, b) and not isomorphic(a, c)

    @pytest.mark.parametrize("fmt", ["xml", "pretty-xml", "hext"])
    def test_refused_where_there_is_no_sequence(self, fmt: str) -> None:
        with pytest.raises(Exception, match="no form for a sequence term"):
            data().serialize(format=fmt)

    def test_sparql_syntax(self) -> None:
        for q in ("SELECT * { ?s :p undef }", "SELECT * { BIND(undef AS ?x) }", "SELECT * { BIND(STR(undef) AS ?x) }"):  # fmt: skip
            with pytest.raises(ParseException):
                query(q)


class TestResults:
    def round_trip(self, fmt: str) -> Sequence:
        res = data().query("PREFIX : <http://example/> SELECT ?v { :x :p ?v }")
        text = res.serialize(format=fmt)
        got = Result.parse(io.BytesIO(text), format=fmt)
        return got.bindings[0][Variable("v")]

    @pytest.mark.parametrize("fmt", ["json", "xml"])
    def test_round_trip(self, fmt: str) -> None:
        assert self.round_trip(fmt) == X_SEQ

    def test_json_spelling(self) -> None:
        got = termToJSON(None, X_SEQ)
        assert got["value"][1] == {"type": "undef"}
        assert parseJsonTerm(got) == X_SEQ

    def test_json_slot_only_in_a_seq(self) -> None:
        with pytest.raises(NotImplementedError):
            parseJsonTerm({"type": "undef"})

    def test_xml_spelling(self) -> None:
        res = data().query("PREFIX : <http://example/> SELECT ?v { :x :p ?v }")
        assert b"<unbound" in res.serialize(format="xml")

    def test_tsv_reads_a_slot(self) -> None:
        text = '?v\n(1 undef "a")\n'
        got = TSVResultParser().parse(io.StringIO(text))
        assert got.bindings[0][Variable("v")] == Sequence([Literal(1), UNDEF, Literal("a")])

    def test_csv_cell(self) -> None:
        res = data().query("PREFIX : <http://example/> SELECT ?v { :z :p ?v }")
        assert b"(undef undef)" in res.serialize(format="csv")


class TestEngine:
    def test_substituted_pattern_is_not_looked_up(self) -> None:
        # every variable of the pattern is bound before the pattern is reached
        rows = query("SELECT ?s { VALUES ?b { 5 } ?s :p (1 ?b 3) }")
        assert rows == [{"s": EX.x}]

    def test_repeated_variable_in_a_group(self) -> None:
        g = Graph().parse(
            data="@prefix : <http://example/> . :s1 :p (1 undef) . :s2 :p (undef 1) . :s3 :p (1 2) .", format="turtle"
        )
        assert {r["s"] for r in query("SELECT ?s { VALUES ?v { 1 } ?s :p (?v ?v) }", g)} == {EX.s1, EX.s2}

    def test_a_nested_pattern_does_not_match_a_slot(self) -> None:
        g = Graph().parse(data="@prefix : <http://example/> . :s :p (undef) .", format="turtle")
        assert query("SELECT ?s { ?s :p ( ( ?a ) ) }", g) == []
        assert query("SELECT ?s { ?s :p ( ?a ) }", g) == [{"s": EX.s}]

    def test_unnest_joins_through_a_slot(self) -> None:
        rows = query("SELECT ?i ?m { VALUES ?m { 5 } :x :p ?s UNNEST(?s AS ?m AT ?i) }")
        assert rows == [{"i": Literal(2), "m": Literal(5)}]

    def test_slice_of_only_slots(self) -> None:
        assert query("SELECT ?t { :z :p ?s BIND(?s[1...1] AS ?t) }") == [{"t": Sequence([UNDEF])}]

    def test_undef_in_a_blank_node_list_in_a_pattern(self) -> None:
        g = Graph().parse(data="@prefix : <http://example/> . :s :p ( undef [ :q 1 ] ) .", format="turtle")
        assert query("SELECT ?s { ?s :p ( undef [ :q 1 ] ) }", g) == [{"s": EX.s}]

    def test_update_delete_where_with_an_unbound_variable_in_the_template(self) -> None:
        g = Graph().parse(data="@prefix : <http://example/> . :s :p (1 undef) .", format="turtle")
        g.update("PREFIX : <http://example/> DELETE { ?s :p (?a ?b) } WHERE { ?s :p (?a ?b) }")
        assert len(g) == 0


JSONLD_LIST = '{"@id": "http://example/s", "http://example/p": {"@list": %s}}'


def jsonld_object(list_: str, **kwargs) -> Node:
    return next(iter(Graph().parse(data=JSONLD_LIST % list_, format="json-ld", **kwargs)))[2]


def test_jsonld_null_in_a_list_is_a_slot() -> None:
    one = Literal(1)
    assert jsonld_object("[1, null]") == Sequence([one, UNDEF])
    assert jsonld_object("[null]") == Sequence([UNDEF])
    assert jsonld_object('[[null, 1], {"@list": [null]}]') == Sequence(
        [Sequence([UNDEF, one]), Sequence([UNDEF])]
    )


def test_jsonld_other_nulls_stay_dropped() -> None:
    assert jsonld_object('[{"@value": null}]') == Sequence([])
    data = '{"@id": "http://example/s", "http://example/p": [1, null]}'
    assert next(iter(Graph().parse(data=data, format="json-ld")))[2] == Literal(1)
    data = '{"@context": {"p": {"@id": "http://example/p", "@container": "@list"}}, "@id": "http://example/s", "p": null}'
    assert len(Graph().parse(data=data, format="json-ld")) == 0


def test_jsonld_round_trip() -> None:
    g = data()
    text = g.serialize(format="json-ld")
    assert "null" in text
    assert isomorphic(Graph().parse(data=text, format="json-ld"), g)
