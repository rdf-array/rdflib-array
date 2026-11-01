"""rdf-array: a collection ``( ... )`` is one sequence term, not a ladder of
rdf:first/rdf:rest blank nodes, and ``()`` is the empty sequence, not rdf:nil.
These are the data-model, parser, serializer and SPARQL sides of that, the
SPARQL-array syntax included (gaps, UNNEST, indexes, slices, IN ?seq and the
sequence functions; ``TestArraySyntax``)."""

from __future__ import annotations

import pickle
from typing import Any

import pytest
from pyparsing import ParseException

from rdflib import RDF, BNode, Dataset, Graph, Literal, Namespace, Sequence, URIRef
from rdflib.compare import isomorphic
from rdflib.term import Node, Variable

EX = Namespace("http://example.org/")


def parse(data: str, fmt: str = "turtle") -> Graph:
    g = Graph()
    g.parse(data=data, format=fmt, publicID=str(EX))
    return g


class TestSequenceTerm:
    def test_is_a_term_with_elements(self) -> None:
        s = Sequence([Literal(1), EX.x, Sequence([])])
        assert s.elements == (Literal(1), EX.x, Sequence())
        assert len(s) == 3
        assert list(s) == [Literal(1), EX.x, Sequence()]
        assert s[1] == EX.x
        assert EX.x in s
        assert s.n3() == '("1"^^<http://www.w3.org/2001/XMLSchema#integer> <http://example.org/x> ())'
        assert str(s) == s.n3()
        assert repr(s).startswith("rdflib.term.Sequence((")
        assert s.toPython() == (1, "http://example.org/x", ())

    def test_equality_is_by_elements(self) -> None:
        assert Sequence([Literal(1), EX.x]) == Sequence([Literal("1", datatype=XSD_INTEGER), EX.x])
        assert hash(Sequence([Literal(1)])) == hash(Sequence([Literal(1)]))
        assert Sequence([Literal(1), EX.x]) != Sequence([EX.x, Literal(1)])
        assert Sequence([Literal(1)]) != Sequence([Literal(1), Literal(1)])
        assert Sequence() == Sequence(())
        assert Sequence() != RDF.nil
        assert Sequence([EX.x]) != EX.x
        assert Sequence([EX.x]) != Literal("(<http://example.org/x>)")

    def test_elements_must_be_terms(self) -> None:
        with pytest.raises(TypeError):
            Sequence(["http://example.org/x"])

    def test_orders_after_the_other_terms(self) -> None:
        assert sorted([Sequence([Literal(1)]), Literal(1), EX.x, BNode("b")]) == [
            BNode("b"),
            EX.x,
            Literal(1),
            Sequence([Literal(1)]),
        ]

    def test_pickles(self) -> None:
        s = Sequence([Literal(1), Sequence([EX.x])])
        assert pickle.loads(pickle.dumps(s)) == s


XSD_INTEGER = URIRef("http://www.w3.org/2001/XMLSchema#integer")


class TestParsing:
    def test_turtle_collection_is_one_triple(self) -> None:
        g = parse("<s> <p> (1 'x' <o> (2) ()) .")
        assert len(g) == 1
        o = g.value(EX.s, EX.p)
        assert isinstance(o, Sequence)
        assert o == Sequence([Literal(1), Literal("x"), EX.o, Sequence([Literal(2)]), Sequence()])
        assert (None, RDF.first, None) not in g
        assert (None, RDF.rest, None) not in g

    def test_empty_collection_is_the_empty_sequence(self) -> None:
        g = parse("<s> <p> () .")
        assert g.value(EX.s, EX.p) == Sequence()
        assert (EX.s, EX.p, RDF.nil) not in g

    def test_collection_as_subject_and_with_blank_node_property_lists(self) -> None:
        g = parse("(1 [ <q> 2 ]) <p> <o> .")
        assert len(g) == 2
        subj = next(g.subjects(EX.p, EX.o))
        assert isinstance(subj, Sequence)
        assert subj[0] == Literal(1)
        assert isinstance(subj[1], BNode)
        assert (subj[1], EX.q, Literal(2)) in g

    def test_trig_and_n3_too(self) -> None:
        ds = Dataset(default_union=True)
        ds.parse(data="<g> { <s> <p> (1 2) . }", format="trig", publicID=str(EX))
        assert next(ds.objects(EX.s, EX.p)) == Sequence([Literal(1), Literal(2)])
        g = parse("<s> <p> (1 2) .", "n3")
        assert g.value(EX.s, EX.p) == Sequence([Literal(1), Literal(2)])

    def test_ntriples_and_nquads_sequences(self) -> None:
        g = parse('<http://example.org/s> <http://example.org/p> ("1"^^<http://www.w3.org/2001/XMLSchema#integer> <http://example.org/o> ( ) ) .', "nt")
        assert g.value(EX.s, EX.p) == Sequence([Literal(1), EX.o, Sequence()])
        g = parse("(<http://example.org/a> _:b) <http://example.org/p> <http://example.org/o> .", "nt")
        subj = next(g.subjects(EX.p, EX.o))
        assert isinstance(subj, Sequence) and subj[0] == EX.a and isinstance(subj[1], BNode)
        ds = Dataset(default_union=True)
        ds.parse(data='<http://example.org/s> <http://example.org/p> ("1" "2") <http://example.org/g> .', format="nquads")
        assert next(ds.objects(EX.s, EX.p)) == Sequence([Literal("1"), Literal("2")])

    def test_legacy_ladders_are_untouched(self) -> None:
        g = parse(
            "<s> <p> _:l . _:l <http://www.w3.org/1999/02/22-rdf-syntax-ns#first> 1 ; "
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#rest> <http://www.w3.org/1999/02/22-rdf-syntax-ns#nil> ."
        )
        assert len(g) == 3
        assert isinstance(g.value(EX.s, EX.p), BNode)


class TestSerializing:
    @pytest.mark.parametrize("fmt", ["turtle", "longturtle", "n3", "nt"])
    def test_round_trips(self, fmt: str) -> None:
        g = parse("<s> <p> (1 'x' <o> (2) ()) . ((1) 2) <p> <o> .")
        text = g.serialize(format=fmt)
        assert "rdf-syntax-ns#first" not in text
        back = Graph()
        back.parse(data=text, format=fmt if fmt not in ("longturtle",) else "turtle", publicID=str(EX))
        assert isomorphic(g, back)

    @pytest.mark.parametrize("fmt", ["trig", "nquads"])
    def test_dataset_round_trips(self, fmt: str) -> None:
        ds = Dataset()
        ds.parse(data="<g> { <s> <p> (1 'x' <o> (2) ()) . ((1) 2) <p> <o> . }", format="trig", publicID=str(EX))
        text = ds.serialize(format=fmt)
        assert "rdf-syntax-ns#first" not in text
        back = Dataset()
        back.parse(data=text, format=fmt, publicID=str(EX))
        assert isomorphic(ds.graph(EX.g), back.graph(EX.g))

    def test_turtle_writes_a_collection(self) -> None:
        g = parse("<s> <p> (1 'x' ()) .")
        text = g.serialize(format="turtle", base=str(EX))
        assert '(1 "x" ())' in text

    def test_ntriples_writes_a_collection(self) -> None:
        g = Graph()
        g.add((EX.s, EX.p, Sequence([Literal(1), Sequence()])))
        assert g.serialize(format="nt").strip() == (
            '<http://example.org/s> <http://example.org/p> ("1"^^<http://www.w3.org/2001/XMLSchema#integer> ()) .'
        )


class TestSparql:
    def test_collection_pattern_matches_a_sequence(self) -> None:
        g = parse("<s> <p> (1 2) . <t> <p> (1 2 3) . <u> <p> () .")
        rows = list(g.query("SELECT ?s WHERE { ?s <http://example.org/p> (1 2) }"))
        assert [r.s for r in rows] == [EX.s]
        rows = list(g.query("SELECT ?s WHERE { ?s <http://example.org/p> () }"))
        assert [r.s for r in rows] == [EX.u]

    def test_collection_with_property_list_elements(self) -> None:
        g = parse("<s> <p> (1 [ <q> 2 ]) .")
        rows = list(g.query("SELECT ?s WHERE { ?s <http://example.org/p> (1 [ <http://example.org/q> 2 ]) }"))
        # the [ .. ] is a variable in the pattern: it binds the data's element, whose <q> 2 holds
        assert rows == [(EX.s,)]
        rows = list(g.query("SELECT ?s WHERE { ?s <http://example.org/p> (1 [ <http://example.org/q> 3 ]) }"))
        assert rows == []
        rows = list(g.query("SELECT ?o WHERE { <http://example.org/s> <http://example.org/p> ?o }"))
        assert isinstance(rows[0].o, Sequence) and len(rows[0].o) == 2


class TestListConsumers:
    def test_graph_items_and_collection_read_a_sequence(self) -> None:
        from rdflib.collection import Collection

        g = parse("<s> <p> (1 2 3) .")
        seq = g.value(EX.s, EX.p)
        assert list(g.items(seq)) == [Literal(1), Literal(2), Literal(3)]
        c = Collection(g, seq)
        assert len(c) == 3 and c[1] == Literal(2) and c.index(Literal(3)) == 2 and list(c) == list(seq)
        assert c.n3() == seq.n3()
        with pytest.raises(TypeError):
            c.append(Literal(4))


# The SPARQL-array syntax of rdf-array's docs/array-syntax.md: its section 4 data and
# worked examples (4.1, with the result rows given there) and its section 5 edge cases.

AR = Namespace("http://ex/")

ARRAY_DATA = """
@prefix : <http://ex/> .
:obs1 :component ( ( "8480-6" "systolic"  ( 120 "mm[Hg]" ) )
                   ( "8462-4" "diastolic" (  80 "mm[Hg]" ) ) ) .
:obs2 :component ( ( "8480-6" "systolic"  ( 150 "mm[Hg]" ) )
                   ( "8462-4" "diastolic" (  95 "mm[Hg]" ) ) ) .
:obs3 :component ( ( "8480-6" "systolic"  ( "high" "mm[Hg]" ) ) ) .
:m1   :matrix ( ( 1 2 3 ) ( 4 5 6 ) ) .
:m2   :matrix ( ( 1 2 3 ) ( 4 5 ) ) .
:poly :points ( ( 0 0 ) ( 3 0 ) ( 3 4 ) ) .
:kv   :pairs  ( "a" 1 "b" 2 "c" 3 ) .
:tree :node   ( "root" ( ( "left" ( ) ) ( "right" ( ( "leaf" ( ) ) ) ) ) ) .
"""


def seq(*elements: Any) -> Sequence:
    """a sequence of terms; a Python value is a literal"""
    return Sequence([e if isinstance(e, Node) else Literal(e) for e in elements])


def rows(g: Graph, query: str) -> list[tuple]:
    """the solutions of a query on g, with the prefix : <http://ex/>, as tuples in
    the order of the SELECT clause; sorted unless the query orders them"""
    res = g.query("PREFIX : <http://ex/>\n" + query)
    out = [tuple(row) for row in res]
    if "ORDER BY" in query:
        return out
    return sorted(out, key=lambda r: ["" if x is None else x.n3() for x in r])


def ordered(rows_: list[tuple]) -> list[tuple]:
    return sorted(rows_, key=lambda r: ["" if x is None else x.n3() for x in r])


def rejected(query: str) -> None:
    with pytest.raises(ParseException):
        Graph().query("PREFIX : <http://ex/>\n" + query)


def rejected_update(update: str) -> None:
    with pytest.raises(ParseException):
        Graph().update("PREFIX : <http://ex/>\n" + update)


@pytest.fixture(scope="module")
def ar() -> Graph:
    g = Graph()
    g.parse(data=ARRAY_DATA, format="turtle")
    assert len(g) == 8
    return g


class TestArraySyntax:
    # 4.1 Worked examples

    def test_a_tuple_anywhere_in_a_list_of_tuples(self, ar: Graph) -> None:
        q = 'SELECT ?obs ?v ?unit WHERE { ?obs :component ( ... ( "8480-6" ?name ( ?v ?unit ) ) ... ) }'
        assert rows(ar, q) == ordered(
            [
                (AR.obs1, Literal(120), Literal("mm[Hg]")),
                (AR.obs2, Literal(150), Literal("mm[Hg]")),
                (AR.obs3, Literal("high"), Literal("mm[Hg]")),
            ]
        )

    def test_the_first_and_the_last_member_nested(self, ar: Graph) -> None:
        q = "SELECT ?x0 ?last WHERE { :poly :points ( ( ?x0 ?y0 ) ... ?last ) }"
        assert rows(ar, q) == [(Literal(0), seq(3, 4))]

    def test_head_and_tail(self, ar: Graph) -> None:
        q = "SELECT ?h ?t ?t2 WHERE { :poly :points ( ?h ...?t ) . :poly :points ?pts BIND(?pts[2...] AS ?t2) }"
        tail = seq(seq(3, 0), seq(3, 4))
        assert rows(ar, q) == [(seq(0, 0), tail, tail)]

    def test_a_position_from_a_pattern(self, ar: Graph) -> None:
        q = "SELECT ?x ?i WHERE { :poly :points ( ...?pre ?x ... ) BIND(SEQLEN(?pre) + 1 AS ?i) }"
        assert rows(ar, q) == ordered(
            [(seq(0, 0), Literal(1)), (seq(3, 0), Literal(2)), (seq(3, 4), Literal(3))]
        )

    def test_gaps_at_two_levels_of_recursive_data(self, ar: Graph) -> None:
        q = 'SELECT ?child ?grandchild WHERE { :tree :node ( "root" ( ... ( ?child ( ... ( ?grandchild ?kids ) ... ) ) ... ) ) }'
        assert rows(ar, q) == [(Literal("right"), Literal("leaf"))]

    def test_unnest_twice(self, ar: Graph) -> None:
        q = "SELECT ?m ?i ?j ?x WHERE { ?m :matrix ?rows . UNNEST(?rows AS ?row AT ?i) UNNEST(?row AS ?x AT ?j) }"
        cells = [(1, 1, 1), (1, 2, 2), (1, 3, 3), (2, 1, 4), (2, 2, 5), (2, 3, 6)]
        expected = [(AR.m1, Literal(i), Literal(j), Literal(x)) for i, j, x in cells]
        expected += [(AR.m2, Literal(i), Literal(j), Literal(x)) for i, j, x in cells[:5]]
        assert rows(ar, q) == ordered(expected)

    @pytest.mark.xfail(
        strict=True,
        reason='rdflib orders a string against a number ("high" >= 90 is true) where '
        "SPARQL raises a type error; this predates rdf-array and keeps :obs3's row",
    )
    def test_unnest_then_index_into_each_tuple(self, ar: Graph) -> None:
        q = (
            "SELECT ?obs ?i ?code ?v WHERE { ?obs :component ?c . UNNEST(?c AS ?comp AT ?i) "
            "BIND(?comp[1] AS ?code) BIND(?comp[3][1] AS ?v) FILTER(?v >= 90) }"
        )
        assert rows(ar, q) == ordered(
            [
                (AR.obs1, Literal(1), Literal("8480-6"), Literal(120)),
                (AR.obs2, Literal(1), Literal("8480-6"), Literal(150)),
                (AR.obs2, Literal(2), Literal("8462-4"), Literal(95)),
            ]
        )

    def test_unnest_then_index_into_each_tuple_numeric(self, ar: Graph) -> None:
        # the same with the type error made explicit, which every engine agrees on
        q = (
            "SELECT ?obs ?i ?code ?v WHERE { ?obs :component ?c . UNNEST(?c AS ?comp AT ?i) "
            "BIND(?comp[1] AS ?code) BIND(?comp[3][1] AS ?v) FILTER(isNUMERIC(?v) && ?v >= 90) }"
        )
        assert rows(ar, q) == ordered(
            [
                (AR.obs1, Literal(1), Literal("8480-6"), Literal(120)),
                (AR.obs2, Literal(1), Literal("8480-6"), Literal(150)),
                (AR.obs2, Literal(2), Literal("8462-4"), Literal(95)),
            ]
        )

    def test_a_slice_of_every_row(self, ar: Graph) -> None:
        q = "SELECT ?m ?i ?cols WHERE { ?m :matrix ?rows . UNNEST(?rows AS ?row AT ?i) BIND(?row[2...3] AS ?cols) }"
        assert rows(ar, q) == ordered(
            [
                (AR.m1, Literal(1), seq(2, 3)),
                (AR.m1, Literal(2), seq(5, 6)),
                (AR.m2, Literal(1), seq(2, 3)),
                (AR.m2, Literal(2), seq(5)),
            ]
        )

    def test_stride(self, ar: Graph) -> None:
        q = (
            "SELECT ?k ?v WHERE { :kv :pairs ?p . UNNEST(?p AS ?k AT ?i) "
            "BIND(?p[?i + 1] AS ?v) FILTER(?i - 2 * FLOOR(?i / 2) = 1) }"
        )
        assert rows(ar, q) == ordered(
            [(Literal("a"), Literal(1)), (Literal("b"), Literal(2)), (Literal("c"), Literal(3))]
        )

    def test_chained_indexes(self, ar: Graph) -> None:
        q = "SELECT ?m ?cell ?len WHERE { ?m :matrix ?rows . BIND(?rows[2][3] AS ?cell) BIND(SEQLEN(?rows[2]) AS ?len) }"
        assert rows(ar, q) == ordered([(AR.m1, Literal(6), Literal(3)), (AR.m2, None, Literal(2))])

    def test_a_sequence_as_the_needle(self, ar: Graph) -> None:
        assert rows(ar, "SELECT ?s WHERE { ?s :points ?pts FILTER(SEQ(3, 4) IN ?pts) }") == [(AR.poly,)]

    def test_whole_nested_values(self, ar: Graph) -> None:
        q = "SELECT ?m ?n WHERE { ?m :matrix ?rows FILTER(?rows = SEQ(SEQ(1, 2, 3), SEQ(4, 5, 6))) ?n :matrix ( ( 1 2 3 ) ( 4 5 6 ) ) }"
        assert rows(ar, q) == [(AR.m1, AR.m1)]

    # 5. Edge cases and limits

    def test_lexing_ellipsis(self) -> None:
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p (1 2) , (:a :b) , (:a...b) .", format="turtle")
        # `1...` is 1 and a gap, `:a...` is :a and a gap, `:a...b` one prefixed name
        assert rows(g, "SELECT ?s { ?s :p ( 1... ) }") == [(AR.s,)]
        assert rows(g, "SELECT ?s { ?s :p ( :a... ) }") == [(AR.s,)]
        assert rows(g, "SELECT ?o { :s :p ( :a...b ) . :s :p ?o FILTER(?o = SEQ(:a...b)) }") == [
            (seq(AR["a...b"]),)
        ]
        # `[2...4]` is 2, `...`, 4: `...` wins over the decimal `.4`
        assert rows(g, "SELECT ?x { :s :p ( 1 2 ) . BIND(SEQ(1, 2, 3, 4, 5)[2...4] AS ?x) }") == [(seq(2, 3, 4),)]

    def test_no_gap_outside_patterns(self) -> None:
        rejected("CONSTRUCT { ?s :p ( ?a ... ) } WHERE { ?s :p ?a }")
        rejected_update("INSERT DATA { :s :p ( 1 ... ) }")
        rejected_update("INSERT { ?s :q ( ?a ...?rest ) } WHERE { ?s :p ( ?a ...?rest ) }")
        # a gap in the WHERE of an update is fine
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p (1 2 3) .", format="turtle")
        g.update("PREFIX : <http://ex/> INSERT { ?s :q ?rest } WHERE { ?s :p ( ?a ...?rest ) }")
        assert g.value(AR.s, AR.q) == seq(2, 3)

    def test_a_named_gap_is_one_token(self) -> None:
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p (1 2 3) .", format="turtle")
        # a gap and then the member ?b
        assert rows(g, "SELECT ?a ?b { :s :p ( ?a ... ?b ) }") == [(Literal(1), Literal(3))]
        # the named gap ?b
        assert rows(g, "SELECT ?a ?b { :s :p ( ?a ...?b ) }") == [(Literal(1), seq(2, 3))]
        # a named gap may be empty, and the same name must match equal runs
        assert rows(g, "SELECT ?t { :s :p ( 1 2 3 ...?t ) }") == [(seq(),)]
        assert rows(g, "SELECT ?t { :s :p ( ...?t ...?t ) }") == []
        g.parse(data="@prefix : <http://ex/> . :s :q (1 2 1 2) .", format="turtle")
        assert rows(g, "SELECT ?t { :s :q ( ...?t ...?t ) }") == [(seq(1, 2),)]

    def test_no_stride_in_patterns(self, ar: Graph) -> None:
        # every adjacent pair, ("b" 2) as well as (1 "b")
        assert rows(ar, "SELECT ?k ?v { :kv :pairs ( ... ?k ?v ... ) }") == ordered(
            [
                (Literal("a"), Literal(1)),
                (Literal(1), Literal("b")),
                (Literal("b"), Literal(2)),
                (Literal(2), Literal("c")),
                (Literal("c"), Literal(3)),
            ]
        )
        # the named-gap idiom gives the position
        q = "SELECT ?k ?v { :kv :pairs ( ...?pre ?k ?v ... ) FILTER(SEQLEN(?pre) - 2 * FLOOR(SEQLEN(?pre) / 2) = 0) }"
        assert rows(ar, q) == ordered(
            [(Literal("a"), Literal(1)), (Literal("b"), Literal(2)), (Literal("c"), Literal(3))]
        )

    def test_slice_syntax(self) -> None:
        rejected("SELECT * { ?s :p ?o BIND(?o[2:4] AS ?x) }")  # :4 is a prefixed name
        rejected("SELECT * { ?s :p ?o BIND(?o[...] AS ?x) }")  # one end at least
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p (1 2 3 4 5) .", format="turtle")
        q = (
            "SELECT ?x ?y ?z ?w ?v { :s :p ?o BIND(?o[2...4] AS ?x) BIND(?o[...SEQLEN(?o) - 1] AS ?y) "
            "BIND(?o[2...][1] AS ?z) BIND(?o[SEQLEN(?o) - 1 ... SEQLEN(?o)] AS ?w) BIND(?o[...2] AS ?v) }"
        )
        assert rows(g, q) == [(seq(2, 3, 4), seq(1, 2, 3, 4), Literal(2), seq(4, 5), seq(1, 2))]

    def test_slices_are_clamped_and_indexes_are_not(self) -> None:
        g = Graph()
        q = (
            "SELECT ?a ?b ?c ?d ?e ?f ?g { BIND(SEQ(4, 5) AS ?s) BIND(?s[2...3] AS ?a) BIND(SEQ()[2...] AS ?b) "
            "BIND(?s[3...2] AS ?c) BIND(?s[3] AS ?d) BIND(?s[0] AS ?e) BIND(?s[-1] AS ?f) BIND(?s[0...1] AS ?g) }"
        )
        # a slice past the end is clamped; an index out of range, or a slice from 0, is an error
        assert rows(g, q) == [(seq(5), seq(), seq(), None, None, None, None)]

    def test_index_and_slice_errors_leave_the_variable_unbound(self, ar: Graph) -> None:
        q = (
            "SELECT ?a ?b ?c ?d ?p { :kv :pairs ?p BIND(?p[1][1] AS ?a) BIND(?p[1.5] AS ?b) "
            'BIND(?p["2"] AS ?c) BIND(?nothing[1] AS ?d) }'
        )
        assert rows(ar, q) == [(None, None, None, None, seq("a", 1, "b", 2, "c", 3))]

    def test_in_a_list_keeps_its_meaning(self) -> None:
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p (1 2 3) ; :q 2 .", format="turtle")
        # IN ( ?seq ) asks whether ?o equals ?seq; IN ?seq whether it is a member
        assert rows(g, "SELECT ?o { :s :q ?o . :s :p ?seq FILTER(?o IN (?seq)) }") == []
        assert rows(g, "SELECT ?o { :s :q ?o . :s :p ?seq FILTER(?o IN ?seq) }") == [(Literal(2),)]
        assert rows(g, "SELECT ?o { :s :q ?o . :s :p ?seq FILTER(?o NOT IN ?seq) }") == []
        assert rows(g, "SELECT ?o { :s :p ?o FILTER(?o IN (?o) && 4 NOT IN ?o) }") == [(seq(1, 2, 3),)]
        # an indexed or built right-hand side
        assert rows(g, "SELECT ?o { :s :q ?o FILTER(?o IN SEQ(1, 2) && ?o IN SEQ(SEQ(2, 3))[1] && 2.0 IN SEQ(2)) }") == [
            (Literal(2),)
        ]
        # a right-hand side that is not a sequence, or unbound, is an error
        assert rows(g, "SELECT ?o { :s :q ?o FILTER(?o IN ?o) }") == []
        assert rows(g, "SELECT ?o { :s :q ?o FILTER(?o IN ?unbound) }") == []
        assert rows(g, "SELECT ?o { :s :q ?o FILTER(?o IN SEQ(?o, ?unbound)) }") == []
        # SPARQL 1.1 IN: a failing comparison is skipped when another matches
        assert rows(g, "SELECT ?o { :s :q ?o FILTER(?o IN SEQ(:x, 2)) }") == [(Literal(2),)]

    def test_empty_sequences(self) -> None:
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p () . :t :p (1) .", format="turtle")
        assert rows(g, "SELECT ?s { ?s :p () }") == [(AR.s,)]
        assert rows(g, "SELECT ?s { ?s :p ( ... ) }") == ordered([(AR.s,), (AR.t,)])
        assert rows(g, "SELECT ?s { ?s :p ( ...?t ) FILTER(SEQLEN(?t) = 0) }") == [(AR.s,)]
        assert rows(g, "SELECT ?s { ?s :p ?o FILTER(?o = SEQ()) }") == [(AR.s,)]
        assert rows(g, "SELECT ?n ?e { :s :p ?o BIND(SEQLEN(?o) AS ?n) BIND(?o[1] AS ?e) }") == [(Literal(0), None)]
        assert rows(g, "SELECT ?x { :s :p ?o UNNEST(?o AS ?x) }") == []

    def test_unnest(self) -> None:
        g = Graph()
        g.parse(data='@prefix : <http://ex/> . :s :p (:a (:b :c) ()) ; :q "not a sequence" .', format="turtle")
        assert rows(g, "SELECT ?x ?i { :s :p ?o UNNEST(?o AS ?x AT ?i) }") == ordered(
            [(AR.a, Literal(1)), (seq(AR.b, AR.c), Literal(2)), (seq(), Literal(3))]
        )
        # AT is optional; the expression may be any expression
        assert rows(g, "SELECT ?x { :s :p ?o UNNEST(?o[2] AS ?x) }") == ordered([(AR.b,), (AR.c,)])
        assert rows(g, "SELECT ?x { UNNEST(SEQ(1, 2) AS ?x) }") == ordered([(Literal(1),), (Literal(2),)])
        # no solution for a non-sequence, an unbound variable or an error
        assert rows(g, "SELECT ?x { :s :q ?o UNNEST(?o AS ?x) }") == []
        assert rows(g, "SELECT ?x { :s :q ?o UNNEST(?nothing AS ?x) }") == []
        assert rows(g, "SELECT ?x { :s :p ?o UNNEST(?o[9] AS ?x) }") == []
        # a member or position variable bound already must agree
        assert rows(g, "SELECT ?x { :s :p ?o BIND(:a AS ?x) UNNEST(?o AS ?x) }") == [(AR.a,)]
        assert rows(g, "SELECT ?x { :s :p ?o BIND(2 AS ?i) UNNEST(?o AS ?x AT ?i) }") == [(seq(AR.b, AR.c),)]
        # SELECT * sees UNNEST's variables, and a solution modifier may use them
        res = g.query("PREFIX : <http://ex/> SELECT * { :s :p ?o UNNEST(?o AS ?x AT ?i) } ORDER BY DESC(?i) LIMIT 1")
        assert set(res.vars or []) == {Variable("o"), Variable("x"), Variable("i")}
        assert [row.asdict() for row in res] == [
            {"o": seq(AR.a, seq(AR.b, AR.c), seq()), "x": seq(), "i": Literal(3)}
        ]

    def test_sequence_functions(self) -> None:
        g = Graph()
        g.parse(data='@prefix : <http://ex/> . :s :p (1 (2 3)) ; :q "x" .', format="turtle")
        q = (
            "SELECT ?isseq ?isnot ?len ?lenerr ?built ?empty { :s :p ?o ; :q ?l "
            "BIND(isSEQ(?o) AS ?isseq) BIND(isSEQ(?l) AS ?isnot) BIND(SEQLEN(?o) AS ?len) BIND(SEQLEN(?l) AS ?lenerr) "
            "BIND(SEQ(?l, ?o[2][1], SEQ(), :s) AS ?built) BIND(SEQ() AS ?empty) }"
        )
        assert rows(g, q) == [
            (Literal(True), Literal(False), Literal(2), None, seq("x", 2, seq(), AR.s), seq())
        ]
        # an argument in error is an error; the keywords are case-insensitive
        assert rows(g, "SELECT ?x ?l { :s :q ?l BIND(SEQ(1, ?unbound) AS ?x) }") == [(None, Literal("x"))]
        assert rows(g, "SELECT ?x { BIND(seqlen(seq(1)) AS ?x) }") == [(Literal(1),)]

    def test_equality_of_sequences_is_by_value(self) -> None:
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . :s :p (1 (2 3)) . :t :p (1.0 (2 3)) . :u :p (1 2 3) .", format="turtle")
        # = compares members by value, so 1.0 = 1; != is its negation; sameTerm is by term
        assert rows(g, "SELECT ?s { ?s :p ?o FILTER(?o = SEQ(1, SEQ(2, 3))) }") == ordered([(AR.s,), (AR.t,)])
        assert rows(g, "SELECT ?s { ?s :p ?o FILTER(?o != SEQ(1, SEQ(2, 3))) }") == [(AR.u,)]
        assert rows(g, "SELECT ?s { ?s :p ?o FILTER(sameTerm(?o, SEQ(1, SEQ(2, 3)))) }") == [(AR.s,)]
        # a sequence equals no other kind of term, without error
        assert rows(g, "SELECT ?s { ?s :p ?o FILTER(?o != 1 && ?o != :s && !(?o = SEQ(1, SEQ(2, 3))[1])) }") == ordered(
            [(AR.s,), (AR.t,), (AR.u,)]
        )
        # a pattern matches by term: (1.0 (2 3)) is not (1 (2 3))
        assert rows(g, "SELECT ?s { ?s :p ( 1 ( 2 3 ) ) }") == [(AR.s,)]
        # SEQ(1, 2, 3) IN ?seq finds a member, not the sequence itself
        assert rows(g, "SELECT ?s { ?s :p ?o FILTER(SEQ(2, 3) IN ?o) }") == ordered([(AR.s,), (AR.t,)])

    def test_order_by_and_group_by_an_index_need_brackets(self, ar: Graph) -> None:
        rejected("SELECT ?r { ?m :matrix ?r } ORDER BY ?r[1]")
        q = "SELECT ?m { ?m :matrix ?r } ORDER BY DESC(?r[2][2]) (?r[1])"
        assert rows(ar, q) == [(AR.m1,), (AR.m2,)]
        q = "SELECT ?first (COUNT(*) AS ?n) { ?m :matrix ?r } GROUP BY (?r[1] AS ?first)"
        assert rows(ar, q) == [(seq(1, 2, 3), Literal(2))]

    def test_gaps_in_a_subject_and_in_the_results(self, ar: Graph) -> None:
        g = Graph()
        g.parse(data="@prefix : <http://ex/> . (1 2 3) :p :o .", format="turtle")
        res = g.query("PREFIX : <http://ex/> SELECT ?h ?t { ( ?h ...?t ) :p :o }")
        assert list(res) == [(Literal(1), seq(2, 3))]
        # a named gap's sequence comes through the result formats
        for fmt in ("json", "xml", "csv"):
            text = res.serialize(format=fmt)
            assert b"2" in text and b"3" in text
