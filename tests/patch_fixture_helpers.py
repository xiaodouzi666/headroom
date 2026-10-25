"""Independent mock encoding of existing unified-diff fixtures; never production code."""

import json

from unidiff import PatchSet


def anchored_fixture(proposal, request_body):
    request = json.loads(request_body["messages"][-1]["content"])
    documents = request["sources"]
    edits = []
    for file in PatchSet(proposal["diff"].splitlines(keepends=True)):
        name = file.path
        document = documents.get(name, {})
        for hunk in file:
            old = [line.value.rstrip("\r\n") for line in hunk if line.is_context or line.is_removed]
            new = [line.value.rstrip("\r\n") for line in hunk if line.is_context or line.is_added]
            if not old:
                # Independent insertion fixture: anchor to its known preceding source line.
                original = document["text"].splitlines()
                assert hunk.source_start > 0
                anchor = original[hunk.source_start - 1]
                old, new = [anchor], [anchor, *new]
            edits.append(
                {
                    "path": name,
                    "source_sha256": document.get("source_sha256", "0" * 64),
                    "old_lines": old,
                    "new_lines": new,
                }
            )
    return {
        **{key: value for key, value in proposal.items() if key != "diff"},
        "edits": edits,
    }
