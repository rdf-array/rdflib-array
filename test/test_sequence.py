"""rdf-array: a collection ``( ... )`` is one sequence term, not a ladder of
rdf:first/rdf:rest blank nodes, and ``()`` is the empty sequence, not rdf:nil.
These are the data-model, parser, serializer and SPARQL sides of that."""

from __future__ import annotations

import pickle

import pytest

from rdflib import RDF, BNode, Dataset, Graph, Literal, Namespace, Sequence, URIRef
from rdflib.compare import isomorphic

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
