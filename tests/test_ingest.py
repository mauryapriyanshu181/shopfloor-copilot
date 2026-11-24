import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ingest import build, parse  # noqa: E402

SOURCE = {"id": "test", "url": "https://example.test/doc", "chapters": [4]}


# ---------- eCFR ----------

def test_paragraph_designators_become_a_path():
    path = parse.update_path([], "(a) Scope, application, and purpose—(1) Scope. (i) This standard")
    assert path == ["a", "1", "i"]
    assert parse.cite(path) == "(a)(1)"
    path = parse.update_path(path, "(2) Application. (i) This standard applies")
    assert parse.cite(path) == "(a)(2)"
    # after (h), '(i)' is the next letter, not roman numeral one
    assert parse.update_path(["h"], "(i) Training.") == ["i"]
    assert parse.update_path(["c", "4"], "(ii) Procedures shall") == ["c", "4", "ii"]


ECFR = b"""<DIV8 N="1910.999" TYPE="SECTION">
<HEAD>\xc2\xa7 1910.999 Test machines.</HEAD>
<P>(a) <I>Guards</I>\xe2\x80\x94(1) Every machine shall be guarded.</P>
<P>(2) Guards shall be fixed.</P>
<NOTE><HED>Note:</HED><P>Fixed means bolted.</P></NOTE>
<TABLE><CAPTION>Table 1</CAPTION><TR><TH>Size</TH><TH>Gap</TH></TR><TR><TD>small</TD><TD>1 in</TD></TR></TABLE>
<P>(b) Training is required.</P>
<CITA>[39 FR 23502]</CITA>
</DIV8>"""


def test_ecfr_xml_becomes_cited_blocks():
    blocks = parse.parse_ecfr(ECFR, SOURCE)
    assert [b["path"] for b in blocks] == ["(a)(1)", "(a)(2)", "(a)(2)", "(a)(2)", "(b)"]
    assert blocks[0]["source"] == "osha-1910.999"
    assert blocks[0]["citation"] == "29 CFR 1910.999 (a)(1)"
    assert blocks[0]["doc_title"] == "§ 1910.999 Test machines."
    assert blocks[3]["kind"] == "table" and "Size | Gap" in blocks[3]["text"]
    assert not any("39 FR" in b["text"] for b in blocks)        # citations skipped


# ---------- FAA PDF text ----------

def test_running_headers_footers_and_soft_hyphens_are_removed():
    page = "9/27/01 AC 43.13-1B CHG 1 \n \nThe soaking time de­\npends on mass.\nPar 5-18 Page 5-11 "
    assert parse.clean_page(page) == ["The soaking time depends on mass."]


def test_broken_words_are_rejoined_only_when_the_word_exists():
    vocab = {"objects", "foreign"}
    assert parse.dehyphenate(["foreign ob-", "jects remain"], vocab) == ["foreign objects remain"]
    assert parse.dehyphenate(["a self-", "locking nut"], vocab) == ["a self-locking nut"]


def test_headings_with_and_without_a_closing_period():
    assert parse.split_heading("GENERAL. Proper identification") == ("GENERAL", "Proper identification")
    assert parse.split_heading("STEEL TUBING . a. Welded") == ("STEEL TUBING", "a. Welded")
    assert parse.split_heading("ROSETTE WELDS are generally used") == ("ROSETTE WELDS", "are generally used")


def test_numbered_paragraph_starts_including_wrapped_and_reserved():
    lines = ["4-3. INTERCHANGEABILITY OF", "STEEL TUBING .", "a. text"]
    assert parse._paragraph_start(lines, 0, 4) == ("4-3", "INTERCHANGEABILITY OF STEEL TUBING", "", 2)
    assert parse._paragraph_start(["4-5. - 4-15. [RESERVED.]"], 0, 4)[:2] == ("reserved", 15)
    assert parse._paragraph_start(["4-17.) The condition causing"], 0, 4) is None


def test_letter_spaced_pdf_text_is_collapsed():
    assert parse.fix_letter_spacing("T h e particles are fine") == "The particles are fine"
    assert parse.fix_letter_spacing("use a or b here") == "use a or b here"


# ---------- chunking and checks ----------

def block(text, section="4-1", path="", kind="paragraph"):
    return {"source": "faa", "doc_title": "Doc", "section": section, "path": path,
            "heading": "4-1. General", "kind": kind, "text": text, "citation": "par. 4-1",
            "url": "u"}


def test_blocks_are_packed_and_long_ones_split():
    long = " ".join("Word%d is here." % i for i in range(200))       # ~600 words
    blocks = [block("a. " + "x " * 100), block("b. " + "y " * 100), block(long)]
    chunks, _ = build.chunk_blocks(blocks)
    chunks = build._assign_ids(chunks)
    assert all(c["words"] <= build.TARGET_WORDS + 5 for c in chunks)
    assert chunks[0]["text"].count("\n") == 2          # a. and b. packed together
    assert chunks[0]["chunk_id"] == "faa#4-1" and chunks[1]["chunk_id"] == "faa#4-1~2"
    assert chunks[0]["text"].startswith("## 4-1. General\n")


def test_a_small_leftover_is_merged_into_the_chunk_before_it():
    chunks, merged = build.chunk_blocks([block("a. " + "x " * 248), block("c. a short tail")])
    assert merged == 1 and len(chunks) == 1
    assert chunks[0]["body"].endswith("c. a short tail")


def test_osha_paragraphs_do_not_share_a_chunk_across_top_level_letters():
    chunks, _ = build.chunk_blocks([block("(a) first " * 5, "1910.1", "(a)"),
                                    block("(b) second " * 5, "1910.1", "(b)")])
    assert len(chunks) == 2


def test_heading_only_and_number_table_chunks_are_dropped():
    ok = {"chunk_id": "ok", "text": "## h\n" + "a real rule about guards " * 5}
    tiny = {"chunk_id": "tiny", "text": "## h\n(c) Alligator shears."}
    numbers = {"chunk_id": "num", "text": "## h\n" + " ".join("%d 0.%04d" % (i, i) for i in range(40))}
    kept, dropped_tiny, dropped_numbers = build.drop_unusable([ok, tiny, numbers])
    assert [c["chunk_id"] for c in kept] == ["ok"]
    assert dropped_tiny == ["tiny"] and dropped_numbers == ["num"]


def test_public_chunks_load_next_to_the_plant_rule_book(tmp_path):
    from app.retrievers import load_chunks
    public = tmp_path / "chunks.jsonl"
    public.write_text(json.dumps({"chunk_id": "osha-1910.147#(c)(4)", "source": "osha-1910.147",
                                  "doc_title": "§ 1910.147 Lockout/tagout.",
                                  "heading": "1910.147 (c)(4)", "citation": "29 CFR 1910.147 (c)(4)",
                                  "text": "## 1910.147 (c)(4)\nProcedures shall be developed."}) + "\n")
    plant = load_chunks()
    both = load_chunks(contextual=True, include_public=True, public_path=str(public))
    assert len(both) == len(plant) + 1
    assert both[-1]["text"].startswith("# § 1910.147 Lockout/tagout.\n## 1910.147 (c)(4)")
