"""Document ingestion: parse and chunk by section so every chunk is citeable."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from ..protocol.profile import ECUProfile, load_profile
from .models import Chunk

MAX_CHARS = 1100


def _cid(*parts: object) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def _split_paragraphs(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split on blank lines, keeping tables/lists together where possible."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 2 > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
        while len(cur) > max_chars * 2:  # very long paragraph / table: hard split on line boundary
            cut = cur.rfind("\n", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(cur[:cut])
            cur = cur[cut:].lstrip("\n")
    if cur:
        out.append(cur)
    return out


def chunk_markdown(text: str, source: str, layer: str, project: str, version: str = "") -> list[Chunk]:
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2)))
            sections.append((" > ".join(t for _, t in stack), []))
        else:
            sections[-1][1].append(line)
    chunks: list[Chunk] = []
    for sec, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        for i, part in enumerate(_split_paragraphs(body)):
            full = f"{sec}\n{part}" if sec else part
            chunks.append(Chunk(_cid(source, sec, i, part[:40]), full, source, sec, None, layer, project, version))
    return chunks


def chunk_pdf(path: Path, source: str, layer: str, project: str, version: str = "") -> list[Chunk]:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pypdf is required to ingest PDF files") from e
    reader = PdfReader(str(path))
    chunks: list[Chunk] = []
    for pno, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue  # scanned page: OCR (e.g. Tesseract) would be plugged in here
        for i, part in enumerate(_split_paragraphs(text)):
            chunks.append(Chunk(_cid(source, pno, i, part[:40]), part, source, f"page {pno}", pno, layer, project, version))
    return chunks


def chunk_profile(profile: ECUProfile, project: str, source: Optional[str] = None) -> list[Chunk]:
    """Turn the machine-readable ECU profile into citeable text chunks (layer 'ecu')."""
    src = source or f"ECU profile {profile.name} v{profile.version}"
    ver = profile.version
    out: list[Chunk] = []

    def add(section: str, text: str) -> None:
        out.append(Chunk(_cid(src, section), f"{section}\n{text}", src, section, None, "ecu", project, ver))

    def sess(ss) -> str:
        return ", ".join(f"0x{s:02X} {profile.session_name(s)}" for s in ss)

    add("Overview", f"ECU {profile.name} from {profile.oem}. {profile.description} Request CAN ID "
                    f"0x{profile.request_id:X}, response CAN ID 0x{profile.response_id:X}. Timing: P2 "
                    f"{profile.timing.p2_ms} ms, P2* {profile.timing.p2_star_ms} ms, S3 {profile.timing.s3_ms} ms.")
    add("Sessions", "Supported diagnostic sessions: " + sess(profile.sessions))
    for sid, svc in profile.services.items():
        subs = "; ".join(f"0x{k:02X} {v.name}" for k, v in svc.subfunctions.items())
        add(f"Service 0x{sid:02X} {svc.name}",
            f"Service 0x{sid:02X} {svc.name} is available in sessions: {sess(svc.sessions)}."
            + (f" Sub-functions: {subs}." if subs else "") + (f" {svc.notes}" if svc.notes else ""))
    for d in profile.dids:
        r = (f"read in {sess(d.read.sessions)}" + (f" after security level {d.read.security}" if d.read.security else "")
             if d.read else "not readable")
        w = (f"write in {sess(d.write.sessions)}" + (f" after security level {d.write.security}" if d.write.security else "")
             if d.write else "not writable")
        rng = f" Range {d.min}..{d.max}." if d.min is not None or d.max is not None else ""
        pat = f" Format pattern {d.pattern}." if d.pattern else ""
        add(f"DID 0x{d.id:04X} {d.name}",
            f"Data identifier 0x{d.id:04X} {d.name}: {d.length} byte(s), {d.data_type}. {r}; {w}.{rng}{pat} {d.description}")
    for r in profile.routines:
        lvl = f" Requires security level {r.security}." if r.security else ""
        add(f"Routine 0x{r.id:04X} {r.name}",
            f"Routine identifier 0x{r.id:04X} {r.name}: available in {sess(r.sessions)}.{lvl} Start option record "
            f"{r.option_length} byte(s). {'Single instance. ' if r.single_instance else ''}"
            f"{'ECU sends NRC 0x78 before the final response. ' if r.send_pending else ''}{r.description}")
    if profile.security_levels:
        add("Security access", " ".join(
            f"Level {s.level}: requestSeed sub-function 0x{s.level:02X}, sendKey 0x{s.send_key_sub:02X}, seed "
            f"{s.seed_length} bytes, key {s.key_length} bytes, {s.max_attempts} attempts then {s.lockout_ms} ms "
            f"lock-out. {s.description}" for s in profile.security_levels))
    if profile.dtcs:
        add("DTCs", " ".join(f"DTC 0x{d.code:06X} {d.name} status 0x{d.status:02X}." for d in profile.dtcs))
    return out


def ingest_path(path: str | Path, layer: str, project: str, version: str = "", source_name: Optional[str] = None) -> list[Chunk]:
    path = Path(path)
    source = source_name or path.name
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown", ".txt", ".rst"):
        return chunk_markdown(path.read_text(encoding="utf-8", errors="replace"), source, layer, project, version)
    if suffix == ".pdf":
        return chunk_pdf(path, source, layer, project, version)
    if suffix in (".yaml", ".yml"):
        return chunk_profile(load_profile(path), project, source=source)
    raise ValueError(f"unsupported file type {suffix!r} (supported: .md .txt .pdf .yaml)")
