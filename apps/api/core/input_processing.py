"""FR1/FR2 input parsing, format verification, extraction and limits."""
from __future__ import annotations

import io
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

MAX_FILE_BYTES = 10 * 1024 * 1024  # FR2a: exactly 10 MiB is accepted
MAX_PROJECT_PAGES = 100
CHARS_PER_PAGE = 3000
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
USER_STORY_RE = re.compile(
    r"^\s*(?:[-*•\x7f\u2022]\s*)?As\s+an?\s+(?P<role>.+?)\s*,?\s+I\s+want\s+(?P<goal>.+?)\s*,?\s+so\s+that\s+(?P<reason>.+?)\s*[.!]?\s*$",
    re.IGNORECASE,
)
FR_NFR_RE = re.compile(r"^\s*((?:FR|NFR)[-_\s]*\d+[a-z]?(?:\.\d+)?)(?:\s*[:.)-])?\s*", re.IGNORECASE)



def pasted_page_count(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_PAGE) if text else 0


def parse_user_stories(text: str) -> tuple[str, dict[str, Any], str | None]:
    """Keep every nonblank line; record structured fields for valid stories."""
    rows = []
    parsed = []
    lines = [line for line in text.splitlines() if line.strip()]
    has_fr = any(FR_NFR_RE.match(line) for line in lines)

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        clean = line.strip()
        match = USER_STORY_RE.match(clean)
        if match:
            item = {
                "line": line_no,
                "structured": True,
                "role": match.group("role").strip(),
                "goal": match.group("goal").strip().rstrip(".,;"),
                "reason": match.group("reason").strip().rstrip(".,;"),
                "original": clean,
            }
            parsed.append(item)
            rows.append(f"As a {item['role']}, I want {item['goal']}, so that {item['reason']}.")
        elif clean.lower().startswith("as a ") or clean.lower().startswith("as an ") or not has_fr:
            parsed.append({"line": line_no, "structured": False, "original": clean})
            rows.append(clean)
        else:
            rows.append(clean)

    warning = None
    if any(not item["structured"] for item in parsed):
        warning = "Some user stories did not match the 'As a … I want … so that …' pattern. They were retained as unstructured free-text requirements."
    return "\n".join(rows), {"parsed_stories": parsed}, warning


def parse_fr_nfr(text: str) -> tuple[str, dict[str, Any], str | None]:
    """Record original FR/NFR IDs without dropping malformed/unnumbered lines."""
    labels = {}
    has_content = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        has_content = True
        match = FR_NFR_RE.match(line)
        if match:
            labels[str(line_no)] = re.sub(r"[\s_]+", "-", match.group(1)).upper()
    nonblank_count = sum(1 for line in text.splitlines() if line.strip())
    warning = None
    if has_content and len(labels) < nonblank_count:
        warning = "Some lines do not have numbered FR/NFR IDs. The input was accepted as free text; IDs could not be preserved for those lines."
    return text, {"source_labels_by_line": labels}, warning


def parse_input_requirements(text: str) -> tuple[str, dict[str, Any], list[str]]:
    """Analyzes text for user stories and FR/NFR lists.

    Returns:
        (text_for_ai, metadata, warnings)
    """
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    text_to_use = text

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    has_user_story = any(USER_STORY_RE.match(line) or line.lower().startswith("as a") for line in lines)
    has_fr_nfr = any(FR_NFR_RE.match(line) for line in lines)

    if has_user_story:
        normalized, story_meta, story_warn = parse_user_stories(text)
        text_to_use = normalized
        metadata.update(story_meta)
        if story_warn:
            warnings.append(story_warn)

    if has_fr_nfr:
        _, fr_meta, fr_warn = parse_fr_nfr(text)
        metadata.update(fr_meta)
        if fr_warn:
            warnings.append(fr_warn)

    return text_to_use, metadata, warnings


def attach_source_labels(
    requirements: list[dict[str, Any]],
    original_text: str,
    labels_by_line: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach original FR/NFR identifiers to AI-split statements using source line/excerpt."""
    lines = original_text.splitlines()
    for requirement in requirements:
        loc = requirement.get("source_location") or {}
        start = loc.get("line_start")
        if start is not None and labels_by_line and str(start) in labels_by_line:
            requirement["source_label"] = labels_by_line[str(start)]
            continue

        candidates: list[str] = []
        end = loc.get("line_end") or start
        if isinstance(start, int) and 1 <= start <= len(lines):
            candidates.extend(lines[start - 1:max(start, min(end or start, len(lines)))])
        excerpt = loc.get("excerpt")
        if excerpt:
            candidates.extend(line for line in lines if excerpt.strip() and excerpt.strip() in line)
        statement = requirement.get("text", "")
        candidates.extend(line for line in lines if statement.strip() and statement.strip() in line)
        candidates.append(statement)

        for candidate in candidates:
            match = FR_NFR_RE.match(candidate)
            if match:
                requirement["source_label"] = re.sub(r"[\s_]+", "-", match.group(1)).upper()
                break
    return requirements


def attach_user_stories(
    requirements: list[dict[str, Any]],
    original_text: str,
    parsed_stories: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach structured user-story fields (role, goal, reason) or structured:False to statements."""
    lines = original_text.splitlines()

    # Pre-index parsed stories by line and original text
    story_by_line = {}
    story_by_text = {}
    if parsed_stories:
        for s in parsed_stories:
            story_by_line[s["line"]] = s
            orig = s.get("original", "").strip()
            if orig:
                story_by_text[orig] = s

    for requirement in requirements:
        loc = requirement.get("source_location") or {}
        start = loc.get("line_start")

        # 1. Match by line index
        if start is not None and start in story_by_line:
            matched_story = story_by_line[start]
            if matched_story.get("structured"):
                requirement["metadata"] = {
                    "role": matched_story["role"],
                    "goal": matched_story["goal"],
                    "reason": matched_story["reason"],
                    "structured": True,
                }
            else:
                requirement["metadata"] = {"structured": False}
            continue

        candidates: list[str] = []
        end = loc.get("line_end") or start
        if isinstance(start, int) and 1 <= start <= len(lines):
            candidates.extend(lines[start - 1:max(start, min(end or start, len(lines)))])
        excerpt = loc.get("excerpt")
        if excerpt:
            candidates.extend(line for line in lines if excerpt.strip() and excerpt.strip() in line)
        statement = requirement.get("text", "")
        candidates.extend(line for line in lines if statement.strip() and statement.strip() in line)
        candidates.append(statement)

        matched = False
        for candidate in candidates:
            cand_clean = candidate.strip()
            if cand_clean in story_by_text:
                matched_story = story_by_text[cand_clean]
                if matched_story.get("structured"):
                    requirement["metadata"] = {
                        "role": matched_story["role"],
                        "goal": matched_story["goal"],
                        "reason": matched_story["reason"],
                        "structured": True,
                    }
                else:
                    requirement["metadata"] = {"structured": False}
                matched = True
                break

            match = USER_STORY_RE.match(cand_clean)
            if match:
                requirement["metadata"] = {
                    "role": match.group("role").strip(),
                    "goal": match.group("goal").strip().rstrip(".,;"),
                    "reason": match.group("reason").strip().rstrip(".,;"),
                    "structured": True,
                }
                matched = True
                break

        if not matched and parsed_stories:
            # If the user supplied user stories, and this was not matched to a structured story
            # mark it as unstructured free text requirement
            if any(candidate.lower().startswith("as a") for candidate in candidates):
                requirement["metadata"] = {"structured": False}

    return requirements


def enrich_extracted_statements(
    requirements: list[dict[str, Any]],
    original_text: str,
    parsed_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach both source labels (FR/NFR IDs) and user-story metadata."""
    labels_by_line = parsed_metadata.get("source_labels_by_line") if parsed_metadata else None
    parsed_stories = parsed_metadata.get("parsed_stories") if parsed_metadata else None

    # If parsed_metadata wasn't passed, parse on the fly from original_text
    if labels_by_line is None and any(FR_NFR_RE.match(line) for line in original_text.splitlines()):
        _, fr_meta, _ = parse_fr_nfr(original_text)
        labels_by_line = fr_meta.get("source_labels_by_line")

    if parsed_stories is None and any(USER_STORY_RE.match(line) or line.strip().lower().startswith("as a") for line in original_text.splitlines()):
        _, story_meta, _ = parse_user_stories(original_text)
        parsed_stories = story_meta.get("parsed_stories")

    requirements = attach_source_labels(requirements, original_text, labels_by_line=labels_by_line)
    return attach_user_stories(requirements, original_text, parsed_stories=parsed_stories)


def extract_fallback_statements_and_items(
    text: str, project_name: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deterministic rule-based extractor used when AI extraction is unavailable or returns empty.

    Extracts atomic requirements, structured user stories (role/goal/reason), numbered FR/NFRs,
    and derives actors, processes, entities, and relationships for downstream review and diagrams.
    """
    MODAL = re.compile(r"\b(shall|must|should|can|will|may)\b", re.IGNORECASE)
    PREP = re.compile(
        r"\b(to|for|from|with|in|on|by|when|if|after|before|via|into|within|and)\b",
        re.IGNORECASE,
    )

    def title(s: str) -> str:
        s = s.strip()
        return s[:1].upper() + s[1:] if s else ""

    requirements: list[dict[str, Any]] = []
    actors: list[dict[str, Any]] = []
    processes: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    seen_actors: set[str] = set()
    seen_processes: set[str] = set()
    seen_entities: set[str] = set()

    line_no = 1
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            line_no += 1
            continue

        us_m = USER_STORY_RE.match(line)
        fr_m = FR_NFR_RE.match(line)

        rid = f"R-{len(requirements) + 1:03d}"

        if us_m:
            role_clean = us_m.group("role").strip()
            goal_clean = us_m.group("goal").strip()
            reason_clean = us_m.group("reason").strip()
            role_title = title(role_clean)
            requirements.append({
                "id": rid,
                "text": line.lstrip("-*•\x7f\u2022 "),
                "labels": ["functional"],
                "source_location": {"line_start": line_no, "excerpt": line},
                "source_label": None,
                "metadata": {
                    "role": role_clean,
                    "goal": goal_clean,
                    "reason": reason_clean,
                    "structured": True,
                },
            })
            if role_title.lower() not in seen_actors:
                seen_actors.add(role_title.lower())
                actors.append({
                    "name": role_title,
                    "description": f"{role_title} user role",
                    "source_refs": [rid],
                })

            proc_name = title(re.sub(r"^to\s+", "", goal_clean, flags=re.IGNORECASE))
            if proc_name.lower() not in seen_processes:
                seen_processes.add(proc_name.lower())
                processes.append({
                    "name": proc_name,
                    "description": line,
                    "source_refs": [rid],
                })

        elif fr_m:
            raw_label = fr_m.group(1).upper()
            norm_label = re.sub(r"[\s_]+", "-", raw_label)
            stmt_text = line[fr_m.end() :].strip() or line
            is_nfr = "NFR" in norm_label
            requirements.append({
                "id": rid,
                "text": stmt_text,
                "labels": ["non-functional" if is_nfr else "functional"],
                "source_location": {"line_start": line_no, "excerpt": line},
                "source_label": norm_label,
                "metadata": None,
            })
            if not is_nfr:
                modal = MODAL.search(stmt_text)
                if modal:
                    predicate = stmt_text[modal.end() :].strip()
                    predicate = re.sub(
                        r"^be able to\s+", "", predicate, flags=re.IGNORECASE
                    ).strip()
                    parts = PREP.split(predicate)[0].split()
                    if parts:
                        proc_name = title(" ".join(parts[:4]))
                        if proc_name.lower() not in seen_processes:
                            seen_processes.add(proc_name.lower())
                            processes.append({
                                "name": proc_name,
                                "description": stmt_text,
                                "source_refs": [rid],
                            })
                        if len(parts) > 1:
                            ent_name = title(" ".join(parts[1:3]))
                            if (
                                ent_name.lower() not in seen_entities
                                and ent_name.lower() not in seen_actors
                            ):
                                seen_entities.add(ent_name.lower())
                                entities.append({
                                    "name": ent_name,
                                    "description": f"{ent_name} entity",
                                    "source_refs": [rid],
                                })
        elif MODAL.search(line) and len(line) > 15:
            modal = MODAL.search(line)
            predicate = line[modal.end() :].strip()
            parts = PREP.split(predicate)[0].split()
            requirements.append({
                "id": rid,
                "text": line,
                "labels": ["functional"],
                "source_location": {"line_start": line_no, "excerpt": line},
                "source_label": None,
                "metadata": None,
            })
            if parts:
                proc_name = title(" ".join(parts[:4]))
                if proc_name.lower() not in seen_processes:
                    seen_processes.add(proc_name.lower())
                    processes.append({
                        "name": proc_name,
                        "description": line,
                        "source_refs": [rid],
                    })

        line_no += 1

    result_dict = {
        "requirements": requirements,
        "actors": actors,
        "entities": entities,
        "processes": processes,
        "data_flows": [],
        "data_stores": [],
        "interactions": [],
        "relationships": [],
    }
    return requirements, result_dict



def _raise_corrupt(kind: str) -> None:
    raise HTTPException(status_code=400, detail=f"The {kind} file appears corrupted or cannot be opened.")


def _extract_pdf(data: bytes) -> tuple[str, int, list[int]]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import FileNotDecryptedError, WrongPasswordError

        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception:
                unlocked = 0
            if not unlocked:
                raise HTTPException(status_code=400, detail="The PDF is password-protected and cannot be read. Remove the password and try again.")
        try:
            pages = list(reader.pages)
        except (FileNotDecryptedError, WrongPasswordError):
            raise HTTPException(status_code=400, detail="The PDF is password-protected and cannot be read. Remove the password and try again.")
        if len(pages) > MAX_PROJECT_PAGES:
            raise HTTPException(status_code=413, detail=f"This PDF has {len(pages)} pages; the project limit is {MAX_PROJECT_PAGES} pages.")
        extracted, skipped = [], []
        for page_no, page in enumerate(pages, start=1):
            try:
                page_text = (page.extract_text() or "").strip()
            except Exception:
                page_text = ""
            if page_text:
                extracted.append(page_text)
            else:
                skipped.append(page_no)
        if not extracted:
            raise HTTPException(status_code=422, detail="This PDF has no extractable text. Scanned/image-only PDFs are not supported.")
        return "\n\n".join(extracted), len(pages), skipped
    except HTTPException:
        raise
    except Exception:
        _raise_corrupt("PDF")


def _docx_text(data: bytes) -> str:
    try:
        from docx import Document
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(io.BytesIO(data))
        chunks = []
        # Preserve paragraph/table order rather than reading all paragraphs first.
        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                value = Paragraph(child, doc).text.strip()
                if value:
                    chunks.append(value)
            elif isinstance(child, CT_Tbl):
                table = Table(child, doc)
                for row in table.rows:
                    values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    if any(values):
                        chunks.append(" | ".join(values))
        text = "\n".join(chunks).strip()
        if not text:
            raise HTTPException(status_code=422, detail="This DOCX contains no extractable text.")
        return text
    except HTTPException:
        raise
    except Exception as exc:
        # Office-encrypted DOCX files use the OLE compound-file signature.
        if data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise HTTPException(status_code=400, detail="This DOCX is password-protected. Remove its password and try again.") from exc
        _raise_corrupt("DOCX")


def _docx_page_count(data: bytes, extracted_text: str) -> tuple[int, str | None]:
    """Calculates rendered page count using 3 tiers:

    1. Headless LibreOffice conversion to PDF (exact rendered page count)
    2. docProps/app.xml <Pages> extended metadata (authoring application page count)
    3. Fallback character-based estimate (3,000 chars/page) with explicit warning.
    """
    # Tier 1: LibreOffice headless rendering
    office = shutil.which("libreoffice") or shutil.which("soffice")
    if office:
        try:
            with tempfile.TemporaryDirectory(prefix="sddg-docx-") as temp:
                source = Path(temp) / "source.docx"
                source.write_bytes(data)
                completed = subprocess.run(
                    [office, "--headless", "--convert-to", "pdf", "--outdir", temp, str(source)],
                    capture_output=True, timeout=30, check=False,
                )
                rendered = Path(temp) / "source.pdf"
                if completed.returncode == 0 and rendered.exists():
                    from pypdf import PdfReader
                    return len(PdfReader(str(rendered)).pages), None
        except Exception:
            pass

    # Tier 2: Extract <Pages> from docProps/app.xml (Word / OOXML application page count)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "docProps/app.xml" in z.namelist():
                app_xml = z.read("docProps/app.xml").decode("utf-8", errors="ignore")
                match = re.search(r"<Pages>(\d+)</Pages>", app_xml)
                if match:
                    pages = int(match.group(1))
                    if pages > 0:
                        return pages, None
    except Exception:
        pass

    # Tier 3: Conservative estimate with explicit warning
    estimated = max(1, math.ceil(len(extracted_text) / CHARS_PER_PAGE))
    warning = (
        "DOCX page count is estimated (3,000 characters per page) because LibreOffice is not installed "
        "on the API server and document metadata lacked a page count. Install LibreOffice on the API server "
        "for exact rendered page counts."
    )
    return estimated, warning


async def read_and_extract_upload(upload: UploadFile) -> dict[str, Any]:
    """Read bounded upload, verify actual content, and extract text/pages."""
    filename = (upload.filename or "").strip()
    extension = Path(filename).suffix.lower()
    declared_size = getattr(upload, "size", None)
    if declared_size is not None and declared_size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File size is {declared_size / (1024 * 1024):.2f} MB ({declared_size:,} bytes); the maximum allowed size is 10 MB (10 × 1,048,576 bytes).",
        )
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported file type. Supported file types are PDF (.pdf) and DOCX (.docx).")

    data = bytearray()
    total_size = 0
    oversized = False
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_FILE_BYTES:
            oversized = True
            continue
        data.extend(chunk)
    if oversized:
        raise HTTPException(
            status_code=413,
            detail=f"File size is {total_size / (1024 * 1024):.2f} MB ({total_size:,} bytes); the maximum allowed size is 10 MB (10 × 1,048,576 bytes).",
        )
    if total_size == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    data = bytes(data)

    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF. File type is verified by content, not extension.")
        text, pages, skipped = _extract_pdf(data)
        warning = f"No text could be extracted from page(s): {', '.join(map(str, skipped))}. Those pages were skipped." if skipped else None
        return {
            "filename": filename,
            "extension": extension,
            "data": data,
            "text": text,
            "page_count": pages,
            "warning": warning,
            "skipped_pages": skipped,
            "size_bytes": len(data),
        }

    # DOCX is an OOXML ZIP package; check required members rather than MIME type alone.
    if data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise HTTPException(status_code=400, detail="This DOCX is password-protected. Remove its password and try again.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "EncryptedPackage" in names:
                raise HTTPException(status_code=400, detail="This DOCX is password-protected. Remove its password and try again.")
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("Missing DOCX package members")
            if archive.testzip() is not None:
                raise ValueError("Corrupt ZIP member")
    except HTTPException:
        raise
    except Exception:
        _raise_corrupt("DOCX")
    text = _docx_text(data)
    pages, page_warning = _docx_page_count(data, text)
    if pages > MAX_PROJECT_PAGES:
        raise HTTPException(status_code=413, detail=f"This DOCX renders to {pages} pages; the project limit is {MAX_PROJECT_PAGES} pages.")
    warning = page_warning
    return {
        "filename": filename,
        "extension": extension,
        "data": data,
        "text": text,
        "page_count": pages,
        "warning": warning,
        "skipped_pages": [],
        "size_bytes": len(data),
    }
