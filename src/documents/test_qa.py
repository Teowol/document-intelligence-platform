"""Phase 7 tests: grounded QA + RBAC-scoped tool dispatch.

The LLM itself is mocked (we never want real gpt-4o-mini calls in the test
suite); we test that the pipeline dispatches the RBAC tools correctly,
never leaks unauthorized content, and parses citations.
"""

import pytest

from documents.qa import answer_question

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------------
# Minimal OpenAI client fake. qa.py does:
#     client = _client()
#     client.chat.completions.create(**kwargs)
# We expose exactly that surface.
# ----------------------------------------------------------------------

class _FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.role = "assistant"
        self.tool_calls = tool_calls or []

    def model_dump(self):
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name,
                                 "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ] or None if self.tool_calls else None,
        }


class _FakeToolCall:
    def __init__(self, name, args="{}"):
        self.id = "call_1"

        class _Func:
            pass
        _Func.name = name
        _Func.arguments = args
        self.function = _Func()


def _make_response(message):
    class _Choices:
        def __init__(self, m):
            self.message = m
    class _Resp:
        choices = [_Choices(message)]
    return _Resp()


class _Completions:
    """Scripted create(): first call emits tool_calls, later calls answer."""

    def __init__(self, tool_calls, final_content):
        self.tool_calls = tool_calls
        self.final_content = final_content
        self.seen_kwargs = []

    def create(self, **kwargs):
        self.seen_kwargs.append(kwargs)
        if self.tool_calls:
            tc = self.tool_calls
            self.tool_calls = None
            return _make_response(_FakeMessage(None, tc))
        return _make_response(_FakeMessage(self.final_content))


def _patch_client(monkeypatch, *, tool_calls=None, final_content="cevap"):
    import documents.qa as qa

    completions = _Completions(tool_calls, final_content)

    class _Client:
        chat = None
    inst = _Client()
    inst.chat = type("chat", (), {})()
    inst.chat.completions = completions

    monkeypatch.setattr(qa, "_client", lambda: inst)
    return completions


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="qauser", email="qa@example.com", password="Pass123!"
    )


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(
        username="other", email="other@example.com", password="Pass123!"
    )


def test_answer_question_returns_answer_and_rounds(user, monkeypatch):
    comp = _patch_client(monkeypatch)
    result = answer_question(user, "Bir soru")
    assert result["answer"] == "cevap"
    assert result["tool_rounds"] == 0
    assert isinstance(result["sources"], list)
    assert comp.seen_kwargs  # a request actually happened


def test_answer_question_empty_query(user, monkeypatch):
    # empty -> no client call, no exception; a broken client would still pass
    comp = _patch_client(monkeypatch)  # patches but must not be called
    result = answer_question(user, "   ")
    assert result["answer"] == ""
    assert result["tool_rounds"] == 0
    assert comp.seen_kwargs == []  # the client was never invoked


def test_answer_tracks_real_document_ids_even_without_citations(user, monkeypatch):
    from conftest import make_chunks, make_document

    document = make_document(user)
    chunks = make_chunks(document, count=1)
    monkeypatch.setattr("documents.qa.search_semantic", lambda *args, **kwargs: chunks)
    _patch_client(monkeypatch, final_content="Answer without a filename")
    result = answer_question(user, "React?")
    assert result["document_ids"] == [document.pk]
    assert result["sources"] == []


def test_tool_only_document_is_tracked(user, monkeypatch):
    from conftest import make_chunks, make_document

    document = make_document(user)
    make_chunks(document, count=1)
    monkeypatch.setattr("documents.qa.search_semantic", lambda *args, **kwargs: [])
    _patch_client(monkeypatch, tool_calls=[
        _FakeToolCall("get_document_chunks", '{"document_id": %s}' % document.pk),
    ])
    assert answer_question(user, "React?")["document_ids"] == [document.pk]


def test_answer_question_one_tool_round_and_citations(user, monkeypatch):
    comp = _patch_client(
        monkeypatch,
        tool_calls=[_FakeToolCall("list_documents")],
        final_content="Yanıt: [Kaynak: a.pdf, s.1]",
    )
    result = answer_question(user, "Dökümanlar?")
    assert result["tool_rounds"] == 1
    assert any(s["file"] == "a.pdf" and s["page"] == 1 for s in result["sources"])
    assert comp.seen_kwargs[0].get("tools") is not None


def test_tool_dispatch_never_leaks_unauthorized(user, other_user):
    from documents.models import Document
    from documents.qa import _tool_dispatch

    doc = Document.objects.create(
        owner=other_user, title="private", original_filename="p.pdf",
        doc_type="pdf", status="ready",
    )
    meta = _tool_dispatch(
        user, "get_document_metadata", {"document_id": doc.pk}
    )
    # unauthorized -> plain "Not found" string, no metadata serialized
    assert meta == "Not found"

    chunks = _tool_dispatch(
        user, "get_document_chunks", {"document_id": doc.pk}
    )
    assert chunks == ""
