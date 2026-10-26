# rdflib-array: RDFLib for rdf-array (sequences as terms)

rdf-array is RDF whose data model has a fifth kind of term, the **sequence**: `(1 2 3)` in Turtle-array
is one term holding its elements in order, not a ladder of `rdf:first`/`rdf:rest` blank nodes,
and `()` is the empty sequence, not `rdf:nil`. Triples that spell out `rdf:first`/`rdf:rest`
stay ordinary triples and `rdf:nil` an ordinary IRI; they are just no longer what `( … )` means.
This fork gives RDFLib the term, reads and writes it in the concrete syntaxes that can carry it,
and teaches the graph API about it. The validator side is
[PyShEx-array](https://github.com/rdf-array/PyShEx-array), whose `doc/rdf-array.md` lists the
sibling forks.

## The term

```python
from rdflib import Literal, URIRef
from rdflib.term import Sequence

seq = Sequence([Literal(1), Sequence([Literal(2), Literal(3)]), URIRef("http://a.example/o")])
seq.elements        # (Literal('1'), Sequence((Literal('2'), Literal('3'))), URIRef('http://a.example/o'))
len(seq), seq[1]    # 3, the nested sequence
seq.n3()            # '("1"^^<http://www.w3.org/2001/XMLSchema#integer> ("2"^^… "3"^^…) <http://a.example/o>)'
seq.toPython()      # (1, (2, 3), 'http://a.example/o')
Sequence()          # the empty sequence; it is falsy, so test `is not None`, not truth
```

`Sequence` is an `Identifier` (so a `str`) whose string value is its N-Triples form, which gives
it equality, hashing and store keys by content: two sequences with equal elements are the same
term. A sequence may hold any node, including blank nodes, other sequences and, in N3, formulae;
elements must be rdflib nodes (`TypeError` otherwise). It is immutable, and in the ordering used
to sort terms it comes after literals.

## Reading and writing

| syntax | parsing | serializing |
|---|---|---|
| Turtle, TriG, N3 (`plugins/parsers/notation3.py`, `plugins/serializers/turtle.py`, `n3.py`) | `( … )` is one `Sequence`, `()` the empty one; `rdf:nil` and explicit `rdf:first`/`rdf:rest` triples are read as written | `( … )` with the elements inline: a blank node referred to only from the sequence is written as its `[ … ]` property list, a formula as `{ … }`, and the elements' prefixes are declared; an explicit ladder is written as the blank node property lists it is, never as `( )`, and `rdf:nil` as `rdf:nil` |
| long Turtle (`longturtle.py`) | as Turtle | as Turtle, one element per line |
| N-Triples, N-Quads (`plugins/parsers/ntriples.py`) | `( … )` of N-Triples terms, nested, as subject or object: an rdf-array extension of the grammar | the term's N-Triples form |
| JSON-LD (`plugins/parsers/jsonld.py`, `plugins/serializers/jsonld.py`) | `@list` is a `Sequence` (nested lists nest; an empty `@list` is `()`) | a `Sequence` object is an `@list`; a ladder is ordinary nodes |
| SPARQL (`plugins/sparql/parser.py`) | `( … )` in a triple pattern or a `CONSTRUCT` template is one sequence term, `()` the empty one; variables inside it bind to a data sequence's elements (`evaluate.py`), and `ORDER BY` sorts sequences after literals (`evalutils.py`) | – |
| SPARQL results (`plugins/sparql/results/`) | a sequence binding is `{"type":"seq","value":[…]}` in JSON, `<seq>` in XML, a `( … )` cell in CSV and the Turtle term in TSV, read and written | – |
| RDF/XML, TriX, HexTuples | unchanged: `rdf:parseType="Collection"` is still a ladder | a graph holding a sequence term is refused with an error naming it, since these syntaxes have no form for one |

## Graph API

- `Graph.items(seq)` yields a sequence's elements, and `rdflib.collection.Collection(graph, seq)`
  reads one (indexing, iteration, `n3()`); its mutators raise `TypeError`, a term cannot be edited
  in place.
- `Graph.cbd(resource)` includes the blank nodes a sequence holds.
- `rdflib.resource.Resource` wraps a sequence as it does a blank node or IRI, so
  `resource.value(OWL.oneOf).items()` iterates the elements.
- `rdflib.compare` (`to_isomorphic`, `isomorphic`, `graph_diff`, `to_canonical_graph`)
  canonicalises blank nodes inside sequences: while colouring, each sequence is expanded into
  pseudo-triples `s <p#rdf-array-object/i/j> element` so the elements' positions take part in the
  hashes, and the canonical graph is re-assembled with the relabelled nodes inside the sequence
  terms.
- `rdflib.extras.shacl` reads `sh:path ( … )` as a sequence path and `sh:alternativePath ( … )`
  as its alternatives, and builds paths back as sequences.
- `len(graph)` counts a `( … )` as one triple where RDF 1.1 counted 2n + 1.

## Tests

New: `test/test_sequence.py` (22 tests: the term, parsing in Turtle/TriG/N3/N-Triples/N-Quads,
untouched legacy ladders, round trips, SPARQL, `items` and `Collection`). The W3C and other
suites run with these entries flagged, each with an rdf-array reason in the test file:

- W3C Turtle and TriG evaluation tests whose data writes a collection, where the expected
  N-Triples spells a ladder (`RDF_MINUS_COLLECTION_TESTS` in `test/test_w3c_spec/test_turtle_w3c.py`
  and `test_trig_w3c.py`: `blankNodePropertyList_containing_collection`, `collection_subject`,
  `collection_object`, `empty_collection`, `nested_collection`, `first`, `last`, `*-subm-08`,
  `*-subm-09`), and the same entries plus `turtle-eval-lists-01` … `05` in the N3 suite's Turtle
  manifests (`test_n3_w3c.py`, `EXPECTED_FAILURES`).
- The JSON-LD test suites (`test/jsonld/test_onedotone.py`, `test_testsuite.py`): the `toRdf`,
  `fromRdf` and `html` cases whose expected N-Quads spell a `@list` as a ladder or `rdf:nil`.
- Round trips (`test/test_roundtrip.py`): the 13 N3 fixtures that write collections, through
  RDF/XML, TriX and HexTuples, and `n3-writer-test-14.n3` through JSON-LD (a sequence as subject).
- `test_serializer_turtle.py::test_turtle_valid_list` now checks that a sequence is written as a
  collection and a ladder as property lists; `test_tools/test_chunk_serializer.py` expects fewer
  triples than RDF 1.1's count.
- `test/test_extras/test_infixowl`: four serialization tests (`xfail(strict=True)`) whose expected
  Turtle spells the OWL lists infixowl builds as `( … )`; infixowl still builds them as ladders
  through `Collection`, which the serializer now writes as the property lists they are.
- The harness (`test/utils`) collapses blank nodes inside sequences and compares a formula inside
  a sequence by its triple set.

The shared rdf-array tests, copied into `test/data/suites/rdf-array/` by its `update.sh` (the
commits are in `*.commit`):

- [rdf-tests-contrib](https://github.com/rdf-array/rdf-tests-contrib) through
  `test/test_w3c_spec/test_rdf_array_contrib.py`: Turtle-, TriG-, N-Triples- and N-Quads-array
  syntax and evaluation with each format's W3C checker, and SPARQL-array evaluation, update,
  syntax and results with the SPARQL checker. 59 pass. 28 are `xfail(strict=True)`: the 27 that
  require `ra:PositionPatterns` or `ra:SequenceFunctions` (`((e))[i]`, `isSEQ`, `SEQLEN`, `SEQ`,
  `x[i]`; [rdf-array#8](https://github.com/rdf-array/rdf-array/issues/8)), and Turtle
  `seq-literal-kinds`, since rdflib keeps `"x"^^xsd:string` apart from `"x"` at any position. The
  negative syntax tests for positions run and pass.
- [json-ld-api-contrib](https://github.com/rdf-array/json-ld-api-contrib) `toRdf` and `fromRdf`
  through `test/jsonld/test_rdf_array_contrib.py` and the JSON-LD runner: all 18 pass. The
  JSON-LD-array tests (`array-manifest.jsonld`) need a JSON-LD-array processor and are not copied.

Running them found and fixed: a sequence accepted as a Turtle predicate; `ORDER BY` over
sequences (no sort key); a prefixed name or typed literal inside a SPARQL sequence pattern (the
parser built the term before the prologue resolved it; it now waits for the algebra); variables
inside a sequence pattern, now unified with the data's elements (`evalBGP`), collected for
`SELECT *` and projection, and filled in `CONSTRUCT` templates; and the four result formats, which
now read and write a sequence (`{"type":"seq"}`, `<seq>`, the CSV `( … )` cell and the TSV term).
SPARQL 1.0 `basic/list-3` and `list-4` pass as a result, and
`test_sequence.py::test_collection_with_property_list_elements` now expects the match.

Unrelated to rdf-array: `test/test_misc/test_plugins.py` installs a test plugin with `pip`, which a
`uv` virtual environment does not have; the two tests fail in such an environment.

Run the suite with `pytest -m "not webtest and not testcontainer"` (the rest needs the network or
Docker). The W3C report files in `test_reports/` were not regenerated.

## Not done

- RDF/XML, TriX and HexTuples refuse a graph holding a sequence term rather than inventing a form
  for it; their parsers are unchanged.
- SPARQL: no position patterns (`((e))[i]`, `[?i]`, `[*]`) and no functions over sequences
  (`isSEQ`, `SEQLEN`, `SEQ`, `x[i]`).
- JSON-LD has no node form for a sequence as a subject.
- Stores other than `Memory` are untested with the new term (it is a `str`, so stores that key on
  the term's string form should hold it).
- `rdflib.collection.Collection` cannot edit a sequence in place.
- `rdflib.extras.infixowl` still builds `owl:unionOf`, `owl:intersectionOf` and `owl:oneOf` lists
  as ladders through `Collection`; under rdf-array they would be sequence terms.
