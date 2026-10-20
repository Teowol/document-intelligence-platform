"""Phase 7: grounded question answering with LLM function calling.

Pipeline: question -> (Phase 6 semantic search) -> context assembly
(top-k chunks within a token budget) + (optional function-calling tool
loop) -> gpt-4o-mini answer. Every tool call and every retrieval is scoped
server-side to the requesting user's permissions; the LLM never decides who
may see what.

Answers always carry citations (`[Kaynak: dosya.pdf, s.3]`) so the user can
trace claims back to their own documents.
"""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from .ai_engine import (
    get_document_chunks,
    get_document_metadata,
    list_documents,
    search_semantic,
)
from .parsing import count_tokens

logger = logging.getLogger(__name__)

# ---- model + budget -------------------------------------------------------

QA_MODEL = "gpt-4o-mini"
MAX_TOOL_ROUNDS = 5
MAX_ANSWER_TOKENS = 500
# ~3-4K token context budget; retrieval fills it with chunks, citations and
# the system prompt share it.
CONTEXT_TOKEN_BUDGET = 3000

_SYSTEM_PROMPT = (
    "You are an assistant for a research & document intelligence platform. "
    "Answer the user's question using ONLY the context supplied from their "
    "documents. Never invent facts: if the answer is not in the context, "
    "say exactly: 'Belgelerimde bu bilgi bulunmuyor.' Always end your answer "
    "with a citation line listing the sources you used, formatted as "
    "[Kaynak: <filename>, s.<page>] for each source. Be concise and Turkish."
)

# Each tool is a real function on AI_Engine methods (RBAC-scoped).
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Semantically search the user's own documents and return the "
                "most relevant text chunks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A natural-language search query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "How many chunks to return (1-8).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_chunks",
            "description": (
                "Retrieve text chunks of a given document (optionally a "
                "specific page)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "page": {"type": "integer"},
                },
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List the documents the user can access.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_metadata",
            "description": (
                "Return metadata (title, type, filename, size, public) of a "
                "document the user can access."
            ),
            "parameters": {
                "type": "object",
                "properties": {"document_id": {"type": "integer"}},
                "required": ["document_id"],
            },
        },
    },
]


def _client() -> OpenAI:
    return OpenAI()


def _tool_dispatch(user, tool_name: str, tool_args: dict, *, document_ids=None):
    """Run an RBAC-scoped tool and return a plain text result for the LLM."""
    try:
        if tool_name == "search_documents":
            top_k = min(int(tool_args.get("top_k", 4)), 8)
            chunks = search_semantic(user, tool_args["query"], top_k=top_k)
            if document_ids is not None:
                document_ids.update(c.document_id for c in chunks)
            return "\n\n".join(
                f"[{c.chunk_index}] {c.document.original_filename}"
                f"(s.{c.page_number}) {c.text}"
                for c in chunks
            )
        if tool_name == "get_document_chunks":
            chunks = get_document_chunks(
                user, int(tool_args["document_id"])
            )
            page = tool_args.get("page")
            if page is not None:
                chunks = [c for c in chunks if c.page_number == int(page)]
            if document_ids is not None:
                document_ids.update(c.document_id for c in chunks)
            return "\n\n".join(
                f"[{c.chunk_index}] (s.{c.page_number}) {c.text}" for c in chunks
            )
        if tool_name == "list_documents":
            docs = list_documents(user)
            if document_ids is not None:
                document_ids.update(d.pk for d in docs)
            return "\n".join(
                f"#{d.pk} {d.title} ({d.get_doc_type_display()})" for d in docs
            )
        if tool_name == "get_document_metadata":
            meta = get_document_metadata(user, int(tool_args["document_id"]))
            if meta and document_ids is not None:
                document_ids.add(meta["id"])
            return json.dumps(meta, ensure_ascii=False, default=str) if meta else "Not found"
    except Exception as exc:  # noqa: BLE001 - tool errors go back to the model
        logger.warning("tool %s failed: %s", tool_name, exc)
        return f"Tool error: {exc}"
    return "Unknown tool"


def assemble_context(user, query: str, *, top_k: int = 6, document_ids=None) -> str:
    """Retrieve top-k chunks and render them within the token budget."""
    sections: list[str] = []
    tokens = 0
    for chunk in search_semantic(user, query, top_k=top_k):
        piece = (
            f"[Kaynak: {chunk.document.original_filename}, "
            f"s.{chunk.page_number}]\n{chunk.text}"
        )
        piece_tokens = count_tokens(piece)
        if tokens + piece_tokens > CONTEXT_TOKEN_BUDGET:
            break
        sections.append(piece)
        if document_ids is not None:
            document_ids.add(chunk.document_id)
        tokens += piece_tokens
    return "\n\n".join(sections)


def answer_question(user, question: str, *, use_tools: bool = True) -> dict:
    """
    Full Phase 7 pipeline. Returns a dict:
        {answer, sources: list[{file, page}], tool_rounds}
    Every call is scoped to `user`; unauthorized content is never leaked.
    """
    if not question or not question.strip():
        return {"answer": "", "sources": [], "tool_rounds": 0}

    client = _client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    # Stage 1: retrieval grounding (always used)
    document_ids = set()
    context = assemble_context(user, question, document_ids=document_ids)
    if context:
        messages.append(
            {"role": "user", "content": "DOCUMENTS:\n" + context}
        )
    else:
        messages.append(
            {"role": "user", "content": "DOCUMENTS:\n(no matching documents)"}
        )

    tool_rounds = 0
    if use_tools:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Use the tools if needed to gather more evidence, then "
                    "answer. Remember: only what is in the docs, with sources."
                ),
            }
        )
        while tool_rounds < MAX_TOOL_ROUNDS:
            response = client.chat.completions.create(
                model=QA_MODEL,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                max_tokens=MAX_ANSWER_TOKENS,
            )
            msg = response.choices[0].message
            if not msg.tool_calls:
                break
            tool_rounds += 1
            messages.append(msg.model_dump())
            for call in msg.tool_calls:
                result = _tool_dispatch(
                    user, call.function.name, json.loads(call.function.arguments or "{}"),
                    document_ids=document_ids,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
        if tool_rounds >= MAX_TOOL_ROUNDS:
            logger.warning("tool loop hit %s rounds; answering with current state", MAX_TOOL_ROUNDS)
    else:
        response = client.chat.completions.create(
            model=QA_MODEL,
            messages=messages,
            max_tokens=MAX_ANSWER_TOKENS,
        )

    answer = response.choices[0].message.content or ""
    # Parse [Kaynak: file, s.page] citations out of the answer
    sources = []

    for match in re.finditer(r"\[Kaynak:\s*([^,\]]+)(?:,\s*s\.(\d+))?\]", answer):
        sources.append(
            {"file": match.group(1).strip(), "page": int(match.group(2)) if match.group(2) else None}
        )

    return {
        "answer": answer,
        "sources": sources,
        "tool_rounds": tool_rounds,
        "document_ids": sorted(document_ids),
    }
