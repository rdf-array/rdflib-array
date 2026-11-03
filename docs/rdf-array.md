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
| SPARQL (`plugins/sparql/parser.py`) | `( … )` in a triple pattern or a `CONSTRUCT` template is one sequence term, `()` the empty one; variables inside it bind to a data sequence's elements (`evaluate.py`), and `ORDER BY` sorts sequences after literals (`evalutils.py`). The SPARQL-array syntax below: gaps, `UNNEST`, indexes, slices, `IN ?seq` and the sequence functions | – |
| SPARQL results (`plugins/sparql/results/`) | a sequence binding is `{"type":"seq","value":[…]}` in JSON, `<seq>` in XML, a `( … )` cell in CSV and the Turtle term in TSV, read and written | – |
| RDF/XML, TriX, HexTuples | unchanged: `rdf:parseType="Collection"` is still a ladder | a graph holding a sequence term is refused with an error naming it, since these syntaxes have no form for one |

## SPARQL-array

The query syntax of rdf-array's [array-syntax.md](https://github.com/rdf-array/rdf-array/blob/main/docs/array-syntax.md)
(§1), as `parser.py` (pyparsing) reads it, `algebra.py` translates it and `evaluate.py` and
`operators.py` run it. With the data of that note's §4:

```sparql
PREFIX : <http://ex/>
SELECT ?obs ?v ?unit WHERE {                   # a 3-tuple anywhere in a list of tuples
  ?obs :component ( ... ( "8480-6" ?name ( ?v ?unit ) ) ... )
}
SELECT ?h ?t WHERE { :poly :points ( ?h ...?t ) }        # head and tail
SELECT ?m ?i ?j ?x WHERE {                               # every cell, with its row and column
  ?m :matrix ?rows . UNNEST(?rows AS ?row AT ?i) UNNEST(?row AS ?x AT ?j)
}
SELECT ?cell ?cols WHERE {
  :m1 :matrix ?rows BIND(?rows[2][3] AS ?cell) BIND(?rows[1][2...3] AS ?cols)
}
SELECT ?s WHERE { ?s :points ?pts FILTER(SEQ(3, 4) IN ?pts && SEQLEN(?pts) > 2) }
```

- **Gaps** (`...` and `...?rest`) are members of a sequence pattern, in `WHERE` only: `CollectionPath`
  is `'(' SeqMemberPath+ ')'` with `SeqMemberPath ::= GraphNodePath | '...' | '...' Var` (the
  named gap is one token: `( ?a ... ?b )` is a gap then the member `?b`, `( ?a ...?b )` a named
  gap). `Collection`, used by templates and `INSERT`/`DELETE DATA`, is unchanged, so a gap there is
  a syntax error. A gap is a `parserutils.Gap` node inside the pattern's `Sequence` term, with
  `var` the named gap's variable. The gap is tried before a member, so `( 1... )` is 1 and a gap
  and `( :a... )` is `:a` and a gap (a local name cannot end in `.`), while `:a...b` stays one
  prefixed name, as `:a.b` is. `evalBGP` matches a pattern with gaps in every way it can
  (`_matchTerm`, `_matchMembers`): a gap takes each run length in turn, a named gap binds its
  variable to the run as a sequence, and a variable or named gap met twice must match equal
  values (term equality, as in a join). `( ... ?k ?v ... )` therefore matches every adjacent
  pair, and `( ...?pre ?x ... )` with `SEQLEN(?pre) + 1` gives a member's position.
- **`UNNEST(expr AS ?x AT ?i)`** is a `GraphPatternNotTriples` (`AT ?i` optional). The algebra node
  is `Unnest(p, expr, var, at)`, joined into the group like `Extend`; `evalUnnest` yields one
  solution per member of the sequence `expr` evaluates to, `?i` counting from 1, and none when
  `expr` is unbound, in error or not a sequence. A member or position variable that is bound
  already must agree with the member (join semantics), where SPARQL's `BIND` would make the
  query a syntax error.
- **`expr[i]`, `expr[m...n]`, `expr[m...]`, `expr[...n]`** are `PostfixExpression` suffixes on a
  `PrimaryExpression`, folded by `expandPostfix` into nested `Index(expr, index)` and
  `Slice(expr, start, end)` expressions (`operators.Index`, `operators.Slice`). An index is
  1-based; one that is out of range (so `?s[0]` and `?s[-1]` too), not an integer, or applied
  to a non-sequence is an error, and a `BIND` leaves the variable unbound. A slice is closed,
  1-based and clamped, as the note says: `SEQ(4, 5)[2...3]` is `(5)`, `SEQ()[2...]` is `()`,
  `?s[3...2]` is `()`; a start below 1 is an error, and `[...]` alone is a syntax error. `[2:4]`
  is a syntax error since `:4` lexes as a prefixed name. In `ORDER BY` and `GROUP BY` an index
  needs brackets, `ORDER BY (?x[1])`, because a bare `?x` there is a variable.
- **`?x IN ?seq`, `?x NOT IN ?seq`**: the right-hand side of `IN` may be a `SeqRef`, a variable or a
  `SEQ(…)` call with any index or slice suffixes, so that `IN (` still opens an expression list
  (`?x IN (?seq)` asks whether `?x` equals `?seq`). `RelationalExpression` gets the operators
  `IN SEQ` and `NOT IN SEQ`: true when some member equals the needle by the value equality of `=`,
  an error when the right-hand side is not a sequence; as in SPARQL 1.1's `IN`, a comparison in
  error is skipped when another member matches.
- **`SEQ(…)`, `SEQLEN(e)`, `isSEQ(e)`** are `BuiltInCall`s (`Builtin_SEQ`, `Builtin_SEQLEN`,
  `Builtin_isSEQ`). `SEQ()` is the empty sequence; an argument in error makes `SEQ` an error;
  `SEQLEN` of a non-sequence is an error. The keywords are case-insensitive, like SPARQL's.
- **`=` and `!=`** compare sequences member by member with the value equality of `=`
  (`_sequenceEq`), so `SEQ(1.0, 2) = SEQ(1, 2)`; a sequence equals no other kind of term, without
  error; `sameTerm` and the patterns compare by term. `()` in a pattern or data is the empty
  sequence, and `SEQ()` is its expression.

Where rdflib differs from the note's worked examples: `FILTER(?v >= 90)` keeps a `?v` of `"high"`,
because rdflib orders a string against a number instead of raising the type error SPARQL
prescribes. This predates rdf-array; `isNUMERIC(?v) && ?v >= 90` says what was meant.

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
  as its alternatives, and builds paths back as sequences. A ladder is not a list there, and `rdf:nil` is
  an ordinary IRI (shacl-array.md).
- `len(graph)` counts a `( … )` as one triple where RDF 1.1 counted 2n + 1.

## Tests

New: `test/test_sequence.py` (49 tests: the term, parsing in Turtle/TriG/N3/N-Triples/N-Quads,
untouched legacy ladders, round trips, SPARQL, `items` and `Collection`, and in
`TestArraySyntax` the SPARQL-array syntax: array-syntax.md's §4.1 worked examples with the
result rows given there, and its §5 edge cases). The W3C and other suites run with these
entries flagged, each with an rdf-array reason in the test file:

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
commits are in `*.commit`; `update.sh DIR` copies a local checkout instead of cloning GitHub):

- [rdf-tests-contrib](https://github.com/rdf-array/rdf-tests-contrib) through
  `test/test_w3c_spec/test_rdf_array_contrib.py`: Turtle-, TriG-, N-Triples- and N-Quads-array
  syntax and evaluation with each format's W3C checker, and SPARQL-array evaluation, update,
  syntax and results with the SPARQL checker, the `ra:GapPatterns`, `ra:Unnest` and
  `ra:SequenceFunctions` tests included (the suite at commit `eee4e346` has array-syntax.md's
  §4.1 examples and §5 edge cases as tests, in place of the strawman's position patterns).
  118 pass. 2 are `xfail(strict=True)`: Turtle `seq-literal-kinds`, since rdflib keeps
  `"x"^^xsd:string` apart from `"x"` at any position, and SPARQL `unnest-index-filter`, whose
  `FILTER(?v >= 90)` should drop the `"high"` row that rdflib's ordering of a string against a
  number keeps (the SPARQL-array section above).
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

## rdf-undef: empty slots

On the `rdf-undef` branch a position in a sequence may be empty, `( 1 undef 3 )`, as
[rdf-undef.md](https://github.com/rdf-array/rdf-array/blob/rdf-undef/docs/rdf-undef.md) specifies (§3's table is
what the engine follows).

- **Term.** `rdflib.term.UNDEF` (`from rdflib import UNDEF`), the one instance of `Undef`, a `Node` and not an
  `Identifier`: `n3()` is `undef`, `toPython()` is `None`, and it is equal only to itself. It is a member of a
  `Sequence` and nothing else: `Graph.add`, `addN` and `Dataset.add` raise `ValueError` for it in a triple, and
  `QueryContext` refuses to bind it. `Graph.items(seq)` and `Collection` show it at its position.
- **Syntaxes.** Turtle, TriG, N3, N-Triples and N-Quads read `undef`, in any case, as a member at any depth, and
  writers emit it; `undef:x` stays a prefixed name and `:s :p undef` a syntax error. RDF/XML, TriX and HexTuples
  already refuse any sequence. In JSON-LD a `null` that is a member of a list's array is a slot, and a slot is written as such a `null`. Other nulls
  stay dropped.
  Beside this, an array directly in `"@list"` is now a nested list (it was a string of its Python `repr`), and a `null` value
  of a `@container: @list` term is now no value (it was `()`).
- **SPARQL.** `undef` is a member in patterns, templates and `INSERT`/`DELETE DATA`, and an argument of `SEQ`; it is
  not an expression. A sequence pattern with a variable, a blank node or a gap in it is matched against the data's
  sequences and never looked up by its substituted form (`_openSequence`), since `( ?x )` with `?x` bound also
  matches `( undef )`. In `_matchTerm` a variable at a slot stays as it is, and any other pattern term matches a slot
  only if it is `undef`. rdflib has no fixed-variables analysis and places filters at the end of their group, so
  nothing further needed changing for joins, `OPTIONAL` or filters. `UNNEST` gives a solution at a slot with the
  member unbound; `?s[i]` at a slot is an error; slices and named gaps keep slots; `SEQLEN` counts them; `IN` skips
  them; `=` is false between a slot and a value. `SEQ` writes a slot for `undef` or an unbound variable, and any other
  error is the error of the `SEQ`. An unbound variable in a template's sequence writes a slot; at the top of a
  template it still drops the triple. `ORDER BY` puts a slot before every term, member by member.
- **Results.** `{"type":"undef"}` in a JSON `seq` and `<unbound/>` in an XML `<seq>`, read and written; `undef` in a
  CSV `( … )` cell (written) and in a TSV one (read). Each is refused outside a sequence.
- **Status.** `pytest -m "not webtest and not testcontainer"`: 7697 pass, the same 2 `test_plugins.py` failures as
  `rdf-sequences` (7506 pass there, run from a scratch worktree, where `test_chunk_serializer.py::test_chunk_by_size`
  also fails with a `TypeError`; it passes here). New: `test/test_undef.py` (34). `test/data/suites/rdf-array/rdf-tests-contrib` is at rdf-undef commit
  `3f13149`, with `test_rdf_array_contrib.py` at 256 pass and the same 2 `xfail` as above: all 138 `undef-*` cases
  pass. `test_sequence.py`'s two uses of `SEQ(…, ?unbound)` as "an argument in error" now use `1/0`, since §3 makes the
  unbound one a slot.
- **JSON-LD status.** `test/data/suites/rdf-array/json-ld-api-contrib` is at rdf-undef commit `29de801`, without its array,
  expand, compact and flatten tests, which run in jsonld.js-array; its 12 toRdf tests and 3 fromRdf pass.
  `test/test_undef.py` gains 3.
- **Not yet.** ShEx and SHACL slots wait for rdf-undef.md §5's decisions. PyShEx-array, unchanged, reads a
  slot-bearing sequence and a slot fails a member constraint (`LIST * xsd:integer` against `( 1 undef )`).

## Not done

- RDF/XML, TriX and HexTuples refuse a graph holding a sequence term rather than inventing a form
  for it; their parsers are unchanged.
- SPARQL: no aggregate builds a sequence from solutions (the `COLLECT` array-syntax.md §6 leaves
  open), and `?s[-1]` is an error rather than the last member. `algebra.translateAlgebra`, which
  writes an algebra back as query text, does not know `Unnest`, `Index`, `Slice` or the sequence
  functions.
- JSON-LD has no node form for a sequence as a subject.
- Stores other than `Memory` are untested with the new term (it is a `str`, so stores that key on
  the term's string form should hold it).
- `rdflib.collection.Collection` cannot edit a sequence in place.
- `rdflib.extras.infixowl` still builds `owl:unionOf`, `owl:intersectionOf` and `owl:oneOf` lists
  as ladders through `Collection`; under rdf-array they would be sequence terms.
