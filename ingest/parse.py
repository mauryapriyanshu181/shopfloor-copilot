"""Turn the raw downloads into blocks: small pieces of text that know where they came from.

A block is {source, doc_title, section, path, heading, text, citation, url}. The chunker
later packs consecutive blocks of the same section into chunks.

eCFR XML (OSHA): one block per paragraph (<P>), table, or appendix sub-heading. The
paragraph's position, such as (c)(4), is read from its leading designators.

FAA PDF: text per page with running headers and footers removed and words split across
lines rejoined, cut at the AC's numbered paragraphs (4-1., 6-113., ...) and inside
those at lettered and numbered sub-paragraphs (a., (1)).
"""
import re
import xml.etree.ElementTree as ET

# ---------- eCFR XML ----------

SKIP_TAGS = {"CITA", "AUTH", "SOURCE", "PSPACE", "FTREF", "SECAUTH"}
PARA_TAGS = {"P", "FP", "FP1", "FP2"}
SUBHEAD_TAGS = {"HD1", "HD2", "HD3", "HED"}
ROMAN = re.compile(r"^(?=[ivxl]+$)x{0,3}(ix|iv|v?i{0,3})$")
DESIGNATOR = re.compile(r"(?:^|[—.;:]\s*|\)\s*)\((\w{1,4})\)")


def _text(el):
    return " ".join("".join(el.itertext()).split())


def _level(token, current_letter):
    """Level of a paragraph designator: (a)=0, (1)=1, (i)=2, (A)=3. A roman-looking
    letter is a letter if it comes right after the current one: (h) then (i)."""
    if token.isdigit():
        return 1
    if token.isupper():
        return 3
    if ROMAN.match(token) and not (len(token) == 1 and current_letter
                                   and ord(token) == ord(current_letter) + 1):
        return 2
    return 0


def update_path(path, text):
    """Read the designators at the start of a paragraph and update the running path
    [(a), (1), (i), (A)]. Only designators in the first 160 characters count, and only
    where a new paragraph can start (start of text, after a dash, period or ')')."""
    head = text[:160]
    for m in DESIGNATOR.finditer(head):
        if m.start() > 0 and m.group(0)[0] not in "—.;:)":
            continue
        token = m.group(1)
        level = _level(token, path[0] if path else None)
        path = path[:level] + [""] * max(0, level - len(path)) + [token]
    return path


def cite(path):
    """(a)(1) granularity is enough to point a reader at the right place."""
    return "".join("(%s)" % p for p in path[:2] if p)


def _table(el):
    rows = []
    caption = el.find(".//CAPTION")
    if caption is not None:
        rows.append(_text(caption))
    for tr in el.iter("TR"):
        cells = [_text(c) for c in tr if c.tag in ("TD", "TH")]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def parse_ecfr(xml_bytes, source):
    """Blocks for every section (DIV8) and appendix (DIV9) in an eCFR XML file."""
    root = ET.fromstring(xml_bytes)
    divs = [root] if root.tag in ("DIV8", "DIV9") else \
        [d for d in root.iter() if d.tag in ("DIV8", "DIV9")]
    blocks = []
    for div in divs:
        number = div.get("N", "")
        head = div.find("HEAD")
        title = _text(head) if head is not None else number
        appendix = re.match(r"Appendix (\w+) to Subpart (\w+)", number)
        if div.tag == "DIV9" and appendix:
            # 'Appendix B to Subpart I of Part 1910' -> osha-1910-subpart-i#appendix-b
            section = "appendix-%s" % appendix.group(1).lower()
            source_name = "osha-1910-subpart-%s" % appendix.group(2).lower()
        else:
            section, source_name = number, "osha-" + number
        state = {"path": [], "subhead": ""}

        def emit(text, kind):
            if not text:
                return
            if div.tag == "DIV9":
                where = state["subhead"]
            else:
                where = cite(state["path"])
            blocks.append({"source": source_name,
                           "doc_title": title, "section": section, "path": where,
                           "heading": "%s %s" % (section if div.tag == "DIV8" else number,
                                                 where), "kind": kind,
                           "text": text, "citation": "29 CFR %s %s" % (number, where),
                           "url": source["url"]})

        def walk(el):
            for child in el:
                tag = child.tag
                if tag in SKIP_TAGS or tag == "HEAD":
                    continue
                if tag in PARA_TAGS:
                    text = _text(child)
                    if div.tag == "DIV8":
                        state["path"] = update_path(state["path"], text)
                    emit(text, "paragraph")
                elif tag in SUBHEAD_TAGS:
                    state["subhead"] = _text(child)
                    if div.tag == "DIV9":
                        emit(state["subhead"], "subheading")
                elif tag in ("TABLE", "GPOTABLE"):
                    emit(_table(child), "table")
                else:
                    walk(child)             # NOTE, EXTRACT, DIV and other wrappers

        walk(div)
    return blocks


# ---------- FAA PDF ----------

HEADER = re.compile(r"^\s*(\d{1,2}/\d{1,2}/\d{2}\s+)?AC 43\.13-1B(\s+CHG\s*1)?(\s+\d{1,2}/\d{1,2}/\d{2})?\s*$")
FOOTER = re.compile(r"^\s*(Par|Page)\s+[\dA-Z]+-[\d]+.*$|^\s*Page\s+\d+-\d+.*$")
CHAPTER = re.compile(r"^CHAPTER\s+(\d+)\.\s+(.+)$")
SECTION = re.compile(r"^SECTION\s+(\d+)\.\s+(.+)$")
SUBPARA = re.compile(r"^([a-z]\.|\(\d+\)|\([a-z]\)|NOTE:|TABLE\s+\d+-\d+|FIGURE\s+\d+-\d+)\s")


def clean_page(text):
    """Drop running headers/footers and blank lines; rejoin hyphen-broken words."""
    text = text.replace("­\n", "").replace("­", "")   # soft hyphens
    lines = []
    for line in text.split("\n"):
        if not line.strip() or HEADER.match(line) or FOOTER.match(line):
            continue
        lines.append(line.rstrip())
    return lines


def dehyphenate(lines, vocabulary):
    """Join 'ob-' + 'jects' into 'objects' when the joined word is used elsewhere in the
    document; otherwise keep the hyphen ('self-' + 'locking' stays 'self-locking')."""
    out = []
    for line in lines:
        m = re.search(r"(\w+)\s?-$", out[-1]) if out else None
        first = re.match(r"^\s*([a-z]\w*)(.*)$", line)
        if m and first:
            joined = m.group(1) + first.group(1)
            sep = "" if joined.lower() in vocabulary else "-"
            out[-1] = out[-1][:m.start()] + m.group(1) + sep + first.group(1) + first.group(2)
        else:
            out.append(line)
    return out


PRIVATE_USE = re.compile("[\\ue000-\\uf8ff]")   # stray PDF glyphs (Unicode private use area)
RESERVED = re.compile(r"\[RESERVED\.?\]", re.I)


def _is_upper_word(word):
    letters = [c for c in word if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def split_heading(text):
    """'REPAIR OF CRACKS. Text...' -> ('REPAIR OF CRACKS', 'Text...').
    The heading is the run of capitalised words at the start; it ends at a word that
    ends with a period, or at the first word with a lowercase letter (some headings in
    the AC have no closing period: 'ROSETTE WELDS are generally...')."""
    words = text.split()
    head = []
    for i, w in enumerate(words):
        if w == "." and head:                       # 'STEEL TUBING .'
            return " ".join(head), " ".join(words[i + 1:])
        if not _is_upper_word(w) and not (w in "-&/" and head):
            break
        head.append(w)
        if w.endswith(".") and not re.match(r"^\(?[A-Z]\.$", w):
            head[-1] = w[:-1]
            return " ".join(head), " ".join(words[i + 1:])
    return " ".join(head), " ".join(words[len(head):])


def _paragraph_start(lines, i, chapter):
    """If lines[i] opens numbered paragraph '<chapter>-<n>.', return
    (number, heading, first text, lines consumed). Wrapped headings are joined with up
    to two following lines. Returns ('reserved', last number, ...) for placeholder
    ranges such as '4-5. - 4-15. [RESERVED.]'."""
    m = re.match(r"^(%d-(\d{1,3}))\.\s*(.*)$" % chapter, lines[i].strip())
    if not m:
        return None
    rest = m.group(3)
    if RESERVED.search(rest):
        upto = re.findall(r"%d-(\d{1,3})" % chapter, rest)
        return ("reserved", int(upto[-1]) if upto else int(m.group(2)), "", 1)
    used = 1
    # a heading that runs to the end of the line continues on the next line
    while used < 3 and i + used < len(lines):
        head, tail = split_heading(rest)
        if tail or not head or rest.rstrip().endswith("."):
            break
        rest = rest.rstrip(" -") + " " + lines[i + used].strip()
        used += 1
    head, tail = split_heading(rest)
    letters = [c for c in head if c.isalpha()]
    if len(letters) < 3:
        return None                                  # '4-17.) The condition...' cross-reference
    return (m.group(1), head, tail, used)


LETTER_SPACED = re.compile(r"\b(?:[A-Za-z] ){2,}[A-Za-z]\b")


def fix_letter_spacing(text):
    """Some PDF lines come out letter-spaced: 'T h e particles' -> 'The particles'.
    Needs three or more single letters in a row, so ordinary text is left alone."""
    return LETTER_SPACED.sub(lambda m: m.group().replace(" ", ""), text)


def parse_faa(pdf_path, source):
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    pages = [[PRIVATE_USE.sub("", l) for l in clean_page(p.extract_text() or "")]
             for p in reader.pages]
    vocabulary = {w.lower() for lines in pages for line in lines
                  for w in re.findall(r"[A-Za-z]+", line)}

    # chapter start pages, ignoring the table of contents at the front
    starts = {}
    for i, lines in enumerate(pages):
        for line in lines[:6]:
            m = CHAPTER.match(line.strip())
            if m and i > 33 and int(m.group(1)) not in starts:
                starts[int(m.group(1))] = (i, m.group(2).strip().rstrip(","))

    blocks, gaps, chapter_pages = [], [], {}
    for ch in source["chapters"]:
        first, chapter_title = starts[ch]
        last = min([starts[c][0] for c in starts if c > ch] or [len(pages)])
        chapter_pages[ch] = first + 1
        lines, page_of = [], []
        for page_index in range(first, last):
            for line in dehyphenate(pages[page_index], vocabulary):
                lines.append(line)
                page_of.append(page_index + 1)

        section_title, para, prev = "", None, 0
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if CHAPTER.match(stripped):
                i += 1
                continue
            sm = SECTION.match(stripped)
            if sm:
                section_title = "Section %s %s" % (sm.group(1), sm.group(2).title())
                i += 1
                continue
            start = _paragraph_start(lines, i, ch)
            if start and start[0] == "reserved":
                prev = max(prev, start[1])
                para = None
                i += 1
                continue
            if start:
                number = int(start[0].split("-")[1])
                if number <= prev:                   # numbering went backwards: not a heading
                    start = None
                else:
                    if number != prev + 1:
                        gaps.append("%d-%d after %d-%d" % (ch, number, ch, prev))
                    prev = number
            if start:
                para = {"number": start[0], "title": start[1].title(), "page": page_of[i],
                        "units": [[start[2]]] if start[2] else [[]]}
                blocks.append(_faa_block(source, ch, chapter_title, section_title, para))
                i += start[3]
                continue
            if para is not None:
                if SUBPARA.match(stripped):
                    para["units"].append([stripped])
                else:
                    para["units"][-1].append(stripped)
            i += 1

    out = []
    for b in blocks:
        for unit in b.pop("units"):
            text = fix_letter_spacing(" ".join(" ".join(unit).split()))
            if text:
                out.append(dict(b, text=text))
    return out, {"chapter_pages": chapter_pages, "paragraph_number_gaps": gaps}


def _faa_block(source, ch, chapter_title, section_title, para):
    return {"source": "faa-ac43.13-1b", "doc_title": "FAA AC 43.13-1B, Chapter %d %s"
            % (ch, chapter_title.title()),
            "section": para["number"], "path": "",
            "heading": "%s. %s (%s)" % (para["number"], para["title"], section_title),
            "kind": "paragraph", "units": para["units"],
            "citation": "AC 43.13-1B par. %s, PDF page %d" % (para["number"], para["page"]),
            "url": source["url"]}
