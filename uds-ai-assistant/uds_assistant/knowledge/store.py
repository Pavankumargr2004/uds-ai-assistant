"""Retrieval stores.

* ``BM25Store``  - zero-dependency lexical retrieval; default. Excellent for identifier-heavy
  diagnostic text (DIDs, RIDs, NRC codes) and needs no model download.
* ``ChromaStore`` - persistent vector store (ChromaDB) with a pluggable embedder
  (sentence-transformers BGE/E5, or an offline hashing embedder for tests).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional, Protocol

from .models import Chunk

_STOP = {"the", "a", "an", "of", "to", "in", "is", "are", "for", "and", "or", "on", "be", "by", "with", "what",
         "how", "do", "does", "i", "it", "this", "that", "as", "at", "from", "which", "can", "me", "my", "when"}


def _camel(tok: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", tok)]


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9_]+", text):
        low = raw.lower()
        toks.append(low)
        if low.startswith("0x") and len(low) > 2:
            toks.append(low[2:])
        parts = _camel(raw)
        if len(parts) > 1:
            toks.extend(parts)
    out = []
    for t in toks:
        if t in _STOP:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


class Store(Protocol):
    def add(self, chunks: Iterable[Chunk]) -> None: ...
    def delete_source(self, source: str) -> int: ...
    def search(self, query: str, k: int = 5, layers: Optional[list[str]] = None) -> list[tuple[Chunk, float]]: ...
    def sources(self) -> list[dict]: ...
    def count(self) -> int: ...


class BM25Store:
    def __init__(self, path: Optional[Path] = None, k1: float = 1.5, b: float = 0.75):
        self.path = Path(path) if path else None
        self.k1, self.b = k1, b
        self.chunks: dict[str, Chunk] = {}
        self._tf: dict[str, Counter] = {}
        self._len: dict[str, int] = {}
        self._df: Counter = Counter()
        if self.path and self.path.exists():
            self._load()

    # -- persistence
    def _load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.add([Chunk.from_dict(d) for d in data], _persist=False)

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps([c.to_dict() for c in self.chunks.values()]), encoding="utf-8")

    # -- mutation
    def _index(self, c: Chunk) -> None:
        toks = tokenize(c.text)
        self._tf[c.id] = Counter(toks)
        self._len[c.id] = len(toks)
        for t in set(toks):
            self._df[t] += 1

    def _unindex(self, cid: str) -> None:
        for t in self._tf.get(cid, {}):
            self._df[t] -= 1
            if self._df[t] <= 0:
                del self._df[t]
        self._tf.pop(cid, None)
        self._len.pop(cid, None)

    def add(self, chunks: Iterable[Chunk], _persist: bool = True) -> None:
        for c in chunks:
            if c.id in self.chunks:
                self._unindex(c.id)
            self.chunks[c.id] = c
            self._index(c)
        if _persist:
            self.save()

    def delete_source(self, source: str) -> int:
        ids = [i for i, c in self.chunks.items() if c.source == source]
        for i in ids:
            self._unindex(i)
            del self.chunks[i]
        if ids:
            self.save()
        return len(ids)

    # -- query
    def search(self, query: str, k: int = 5, layers: Optional[list[str]] = None) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        if not q or not self.chunks:
            return []
        n = len(self.chunks)
        avg = sum(self._len.values()) / max(n, 1)
        scores: list[tuple[Chunk, float]] = []
        for cid, c in self.chunks.items():
            if layers and c.layer not in layers:
                continue
            tf = self._tf[cid]
            s = 0.0
            for t in set(q):
                f = tf.get(t, 0)
                if not f:
                    continue
                df = self._df.get(t, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self._len[cid] / avg))
            if s > 0:
                scores.append((c, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]

    def sources(self) -> list[dict]:
        agg: dict[str, dict] = {}
        for c in self.chunks.values():
            a = agg.setdefault(c.source, {"source": c.source, "layer": c.layer, "version": c.version, "chunks": 0})
            a["chunks"] += 1
        return sorted(agg.values(), key=lambda a: a["source"])

    def count(self) -> int:
        return len(self.chunks)


# ------------------------------------------------------------------------------------------------
class HashEmbedder:
    """Deterministic feature-hashing embedder (offline, no model download). For tests / air-gapped demos."""
    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in tokenize(t):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0 if (h >> 100) & 1 else -1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


class SentenceTransformerEmbedder:  # pragma: no cover - needs model download
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # type: ignore
        self.model = SentenceTransformer(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()


def make_embedder(spec: str):
    if spec == "hash":
        return HashEmbedder()
    if spec.startswith("sentence-transformers:"):
        return SentenceTransformerEmbedder(spec.split(":", 1)[1])
    raise ValueError(f"unknown embedder {spec!r}")


class ChromaStore:
    def __init__(self, persist_dir: Path, collection: str, embedder):
        try:
            import chromadb  # type: ignore
        except ImportError as e:
            raise RuntimeError("pip install chromadb to use the Chroma backend") from e
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.col = self.client.get_or_create_collection(re.sub(r"[^A-Za-z0-9_-]", "_", collection)[:60] or "col",
                                                        metadata={"hnsw:space": "cosine"})
        self.emb = embedder

    def add(self, chunks: Iterable[Chunk]) -> None:
        chunks = list(chunks)
        if not chunks:
            return
        self.col.upsert(
            ids=[c.id for c in chunks], documents=[c.text for c in chunks],
            embeddings=self.emb.embed([c.text for c in chunks]),
            metadatas=[{"source": c.source, "section": c.section, "page": c.page if c.page is not None else -1,
                        "layer": c.layer, "project": c.project, "version": c.version} for c in chunks])

    def delete_source(self, source: str) -> int:
        got = self.col.get(where={"source": source})
        ids = got.get("ids", [])
        if ids:
            self.col.delete(ids=ids)
        return len(ids)

    def search(self, query: str, k: int = 5, layers: Optional[list[str]] = None) -> list[tuple[Chunk, float]]:
        if self.col.count() == 0:
            return []
        where = {"layer": {"$in": layers}} if layers else None
        r = self.col.query(query_embeddings=self.emb.embed([query]), n_results=min(k, self.col.count()), where=where)
        out = []
        for cid, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0]):
            page = meta.get("page", -1)
            out.append((Chunk(cid, doc, meta["source"], meta.get("section", ""), None if page == -1 else page,
                              meta.get("layer", ""), meta.get("project", ""), meta.get("version", "")),
                        max(0.0, 1.0 - float(dist))))
        return out

    def sources(self) -> list[dict]:
        got = self.col.get()
        agg: dict[str, dict] = {}
        for m in got.get("metadatas", []):
            a = agg.setdefault(m["source"], {"source": m["source"], "layer": m["layer"], "version": m["version"], "chunks": 0})
            a["chunks"] += 1
        return sorted(agg.values(), key=lambda a: a["source"])

    def count(self) -> int:
        return self.col.count()
