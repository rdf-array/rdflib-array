"""
Notation 3 (N3) RDF graph serializer for RDFLib.
"""

import warnings

from rdflib.graph import Graph
from rdflib.namespace import OWL, Namespace
from rdflib.plugins.serializers.turtle import OBJECT, SUBJECT, TurtleSerializer
from rdflib.term import Sequence

__all__ = ["N3Serializer"]

SWAP_LOG = Namespace("http://www.w3.org/2000/10/swap/log#")


def _formulae_in(node):
    """The formulae a term is or (rdf-array: inside a sequence term) holds."""
    if isinstance(node, Graph):
        yield node
    elif isinstance(node, Sequence):
        for e in node.elements:
            yield from _formulae_in(e)


class N3Serializer(TurtleSerializer):
    """Notation 3 (N3) RDF graph serializer."""

    short_name = "n3"

    def __init__(self, store: Graph, parent=None):
        super(N3Serializer, self).__init__(store)
        self.keywords.update({OWL.sameAs: "=", SWAP_LOG.implies: "=>"})
        self.parent = parent

    def reset(self):
        super(N3Serializer, self).reset()
        self._stores = {}

    def endDocument(self):  # noqa: N802
        if not self.parent:
            super(N3Serializer, self).endDocument()

    def indent(self, modifier=0):
        indent = super(N3Serializer, self).indent(modifier)
        if self.parent is not None:
            indent += self.parent.indent()  # modifier)
        return indent

    def preprocessTriple(self, triple):  # noqa: N802
        super(N3Serializer, self).preprocessTriple(triple)
        for node in triple:
            for formula in _formulae_in(node):
                for t in formula:
                    self.preprocessTriple(t)

    def get_pname(self, uri, gen_prefix=True):
        qname = None
        if self.parent is not None:
            qname = self.parent.get_pname(uri, gen_prefix)
        if qname is None:
            qname = super(N3Serializer, self).get_pname(uri, gen_prefix)
        return qname

    def getQName(self, uri, gen_prefix=True):  # noqa: N802
        warnings.warn(
            "N3Serializer.getQName is deprecated, use N3Serializer.get_pname instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_pname(uri, gen_prefix)

    def statement(self, subject):
        self.subjectDone(subject)
        properties = self.buildPredicateHash(subject)
        if len(properties) == 0:
            return False
        return self.s_clause(subject) or super(N3Serializer, self).statement(subject)

    def path(self, node, position, newline=False):
        if not self.p_clause(node, position):
            super(N3Serializer, self).path(node, position, newline)

    def s_clause(self, subject):
        if isinstance(subject, Graph):
            self.write("\n" + self.indent())
            self.p_clause(subject, SUBJECT)
            self.predicateList(subject)
            self.write(" .")
            return True
        else:
            return False

    def p_clause(self, node, position):
        if isinstance(node, Graph):
            self.subjectDone(node)
            if position is OBJECT:
                self.write(" ")
            self.write("{")
            self.depth += 1
            serializer = N3Serializer(node, parent=self)
            # type error: Argument 1 to "serialize" of "TurtleSerializer" has incompatible type "Optional[IO[bytes]]"; expected "IO[bytes]"
            serializer.serialize(self.stream)  # type: ignore[arg-type]
            self.depth -= 1
            self.write(self.indent() + "}")
            return True
        else:
            return False
