"""Bounded syntactic loop anchors for a patch prompt, never runtime proof."""

import ast

MAX_ANCHORS = 12


def step_call_enclosures(sources):
    """Bind .step() call sites and their enclosing loops to delivered source IDs.

    These can include optimizer or scheduler calls. No name is treated as an
    authenticated optimizer, and no update count or numerical property is inferred.
    Nested function/class bodies start their own lexical scope.
    """
    result = []
    for name, document in sources.items():
        if not name.endswith(".py"):
            continue
        lines = document["lines"]
        text = "\n".join(line["text"] for line in lines)
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            continue

        class Visitor(ast.NodeVisitor):
            def __init__(self, path, source_document, source_lines):
                self.loops = []
                self.path = path
                self.document = source_document
                self.lines = source_lines

            def visit_For(self, node):
                self.loops.append(node)
                self.generic_visit(node)
                self.loops.pop()

            visit_While = visit_For
            visit_AsyncFor = visit_For

            def visit_FunctionDef(self, node):
                previous, self.loops = self.loops, []
                self.generic_visit(node)
                self.loops = previous

            visit_AsyncFunctionDef = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef
            visit_Lambda = visit_FunctionDef

            def visit_Call(self, node):
                if (
                    len(result) < MAX_ANCHORS
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "step"
                    and self.loops
                ):
                    # Use only host-supplied line identities; do not copy source
                    # snippets into an alleged trusted instruction or annotation.
                    result.append(
                        {
                            "path": self.path,
                            "source_sha256": self.document["source_sha256"],
                            "step_call_id": self.lines[node.lineno - 1]["id"],
                            "enclosing_loops": [
                                {
                                    "start_id": self.lines[loop.lineno - 1]["id"],
                                    "end_id": self.lines[loop.end_lineno - 1]["id"],
                                    "kind": type(loop).__name__,
                                }
                                for loop in self.loops
                            ],
                            "syntactic_only": True,
                        }
                    )
                self.generic_visit(node)

        start = len(result)
        try:
            Visitor(name, document, lines).visit(tree)
        except RecursionError:
            # Supplemental metadata must not break a valid ordinary patch path.
            del result[start:]
            continue
        if len(result) == MAX_ANCHORS:
            break
    return result
