import tempfile
from pathlib import Path

from uds_assistant.config import Settings
from uds_assistant.knowledge.ingest import chunk_markdown, chunk_profile
from uds_assistant.knowledge.service import KnowledgeService
from uds_assistant.knowledge.store import BM25Store


def test_chunk_profile_produces_citeable_chunks(profile):
    chunks = chunk_profile(profile, project="demo")
    assert len(chunks) > 10
    assert all(c.source and c.text for c in chunks)


def test_bm25_retrieval_finds_relevant_did(profile):
    chunks = chunk_profile(profile, project="demo")
    store = BM25Store()
    store.add(chunks)
    hits = store.search("how do I write the VIN", k=3)
    assert any("F190" in c.section for c, _ in hits)


def test_knowledge_service_no_evidence_for_offtopic_question(profile):
    d = Path(tempfile.mkdtemp())
    ks = KnowledgeService(Settings(data_dir=d))
    ks.ingest_profile("demo", profile)
    ans = ks.ask("demo", "how do I cook pasta")
    assert ans.mode == "no_evidence"


def test_chunk_markdown_splits_by_heading():
    md = "# Title\n\nIntro text.\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B.\n"
    chunks = chunk_markdown(md, source="doc.md", layer="project", project="demo")
    sections = {c.section for c in chunks}
    assert any("Section A" in s for s in sections)
    assert any("Section B" in s for s in sections)
