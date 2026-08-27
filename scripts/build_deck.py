"""Build the Phase-2 Review-1 deck from the mandated department template.

    uv run python scripts/build_deck.py

The template in docs/review1/template/ is the format: its slide order, its
placeholders, its fonts, its footer and its slide numbering are kept exactly as
they are. Slides are only ever reused or duplicated from it, never restyled.
Where one mandated section needs more than one slide, the extra slide is a
duplicate of the same template slide with "(contd.)" in the title.

Every figure on the results slides is traceable to this repository; the two
literature figures are attributed to their papers on the slide itself.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (
    ROOT
    / "docs/review1/template"
    / "ISE-Division 5 7th sem Major Project PPT Template_Phase 2 review-1.pptx"
)
OUT = ROOT / "docs/review1/Travel_Yantra_Phase2_Review1.pptx"
SHOTS = ROOT / "docs/screenshots"

#: The template's own theme colours (theme1.xml), used for every diagram so no
#: colour enters the deck that the template did not already define.
INK = RGBColor(0x00, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xD1, 0x28, 0x2E)  # dk2
SAND = RGBColor(0xC8, 0xC8, 0xB1)  # lt2
GREY = RGBColor(0x7A, 0x7A, 0x7A)  # accent1
YELLOW = RGBColor(0xF5, 0xC2, 0x01)  # accent2
BLUE = RGBColor(0x52, 0x6D, 0xB0)  # accent3
MUTED = RGBColor(0x98, 0x9A, 0xAC)  # accent4
ORANGE = RGBColor(0xDC, 0x59, 0x24)  # accent5
OLIVE = RGBColor(0xB4, 0xB3, 0x92)  # accent6
SERIF = "Times New Roman"

# Template slide indices, by the section they carry.
T_TITLE, T_CONTENT, T_ABSTRACT, T_INTRO, T_PROBLEM = 0, 1, 2, 3, 4
T_OBJECTIVES, T_METHOD, T_DEMO, T_RESULTS, T_STATUS, T_PUB = 5, 6, 7, 8, 9, 10


# --------------------------------------------------------------------------- #
# template surgery
# --------------------------------------------------------------------------- #


def duplicate(prs: Presentation, index: int):
    """A copy of a template slide, appended at the end.

    Only slides whose shapes are placeholders are duplicated (every slide but
    the title one), so there are no image relationships to re-link.
    """
    source = prs.slides[index]
    new = prs.slides.add_slide(source.slide_layout)
    for shape in list(new.shapes):
        shape._element.getparent().remove(shape._element)
    for shape in source.shapes:
        # Only the placeholders: a diagram already drawn on the source slide
        # must not follow its copy.
        if shape.is_placeholder:
            new.shapes._spTree.append(copy.deepcopy(shape._element))
    return new


def reorder(prs: Presentation, order: list[int]) -> None:
    """Rewrite the slide order. `order` holds current indices, in the order wanted."""
    ids = prs.slides._sldIdLst
    entries = list(ids)
    for entry in entries:
        ids.remove(entry)
    for index in order:
        ids.append(entries[index])


def body_of(slide):
    for shape in slide.shapes:
        if shape.is_placeholder and shape.placeholder_format.idx == 1:
            return shape
    return None


def title_of(slide):
    for shape in slide.shapes:
        if shape.is_placeholder and shape.placeholder_format.idx == 0:
            return shape
    return None


def set_title(slide, text: str) -> None:
    shape = title_of(slide)
    frame = shape.text_frame
    first = frame.paragraphs[0]
    for para in list(frame.paragraphs)[1:]:
        para._p.getparent().remove(para._p)
    if first.runs:
        first.runs[0].text = text
        for run in list(first.runs)[1:]:
            run._r.getparent().remove(run._r)
    else:
        first.add_run().text = text


def set_body(slide, items, size: float | None = None, space: int | None = None):
    """Replace the body text, cloning the template's own first paragraph.

    `items` are (level, text) or (level, text, bold). Cloning keeps the
    template's bullet character, indent, font and colour; only the size is
    overridden, and only where the slide would otherwise overflow.
    """
    shape = body_of(slide)
    frame = shape.text_frame
    frame.word_wrap = True
    paragraphs = list(frame.paragraphs)
    prototype = copy.deepcopy(paragraphs[0]._p)
    for para in paragraphs:
        para._p.getparent().remove(para._p)
    for item in items:
        level, text = item[0], item[1]
        bold = item[2] if len(item) > 2 else None
        element = copy.deepcopy(prototype)
        frame._txBody.append(element)
        para = frame.paragraphs[-1]
        for run in list(para.runs)[1:]:
            run._r.getparent().remove(run._r)
        if not para.runs:
            para.add_run()
        para.runs[0].text = text
        para.level = level
        if size is not None:
            para.runs[0].font.size = Pt(size)
        if bold is not None:
            para.runs[0].font.bold = bold
        if space is not None:
            para.space_after = Pt(space)
    return shape


def head(slide, text, *, size=None, top=0.17, height=0.82, left=0.5, width=8.96):
    """Set a section title and its box together. The template's own title boxes
    are 1.5 in tall for one line of text; a shorter box needs a matching size,
    or the text overflows upward out of the slide."""
    set_title(slide, text)
    shape = title_of(slide)
    place(shape, left=left, top=top, width=width, height=height)
    shape.text_frame.vertical_anchor = MSO_ANCHOR.TOP
    if size is not None:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                run.font.size = Pt(size)
    return shape


def place(shape, left=None, top=None, width=None, height=None) -> None:
    if left is not None:
        shape.left = Inches(left)
    if top is not None:
        shape.top = Inches(top)
    if width is not None:
        shape.width = Inches(width)
    if height is not None:
        shape.height = Inches(height)


# --------------------------------------------------------------------------- #
# diagram primitives, all in the template's own colours and typeface
# --------------------------------------------------------------------------- #


def box(
    slide,
    left,
    top,
    width,
    height,
    text,
    *,
    fill=WHITE,
    line=GREY,
    color=INK,
    size=10.5,
    bold=False,
    shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    align=PP_ALIGN.CENTER,
    line_width=1.0,
    anchor=MSO_ANCHOR.MIDDLE,
):
    node = slide.shapes.add_shape(
        shape, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    node.fill.solid()
    node.fill.fore_color.rgb = fill
    if line is None:
        node.line.fill.background()
    else:
        node.line.color.rgb = line
        node.line.width = Pt(line_width)
    node.shadow.inherit = False
    frame = node.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = Emu(36000)
    frame.margin_top = frame.margin_bottom = Emu(54000)
    for i, line_text in enumerate(text.split("\n")):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        run = para.add_run()
        run.text = line_text
        run.font.size = Pt(size if i == 0 else size - 1)
        run.font.bold = bold and i == 0
        run.font.name = SERIF
        run.font.color.rgb = color
    return node


def label(
    slide,
    left,
    top,
    width,
    height,
    text,
    *,
    size=9,
    bold=False,
    color=INK,
    align=PP_ALIGN.LEFT,
    italic=False,
):
    tb = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    frame = tb.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    for i, line_text in enumerate(text.split("\n")):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        run = para.add_run()
        run.text = line_text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.name = SERIF
        run.font.color.rgb = color
    return tb


def arrow(slide, x1, y1, x2, y2, color=GREY, width=1.25):
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
    )
    line.line.color.rgb = color
    line.line.width = Pt(width)
    tail = line.line._get_or_add_ln()
    from pptx.oxml.ns import qn

    end = tail.makeelement(
        qn("a:tailEnd"), {"type": "triangle", "w": "sm", "len": "sm"}
    )
    tail.append(end)
    return line


def bar(slide, left, top, width, height, *, fill, text, size=9, color=WHITE):
    rect = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    rect.fill.solid()
    rect.fill.fore_color.rgb = fill
    rect.line.fill.background()
    rect.shadow.inherit = False
    frame = rect.text_frame
    frame.margin_left = frame.margin_right = Emu(36000)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    para = frame.paragraphs[0]
    para.alignment = PP_ALIGN.RIGHT
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.name = SERIF
    run.font.color.rgb = color
    return rect


def table(slide, left, top, width, rows, *, col_widths, size=10.5, head_size=10.5):
    shape = slide.shapes.add_table(
        len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(0.3)
    )
    tbl = shape.table
    tbl.first_row = True
    tbl.horz_banding = True
    for i, w in enumerate(col_widths):
        tbl.columns[i].width = Inches(w)
    for r, row in enumerate(rows):
        tbl.rows[r].height = Inches(0.26)
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = Emu(54000)
            cell.margin_right = Emu(36000)
            cell.margin_top = cell.margin_bottom = Emu(9000)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
            run = para.add_run()
            run.text = str(value)
            run.font.size = Pt(head_size if r == 0 else size)
            run.font.bold = r == 0
            run.font.name = SERIF
    return tbl


def shot(slide, name, left, top, width, caption, *, size=9.5):
    """One screenshot with the single line that says what it proves."""
    path = SHOTS / name
    if not path.exists():
        raise SystemExit(f"missing screenshot: {path}")
    picture = slide.shapes.add_picture(
        str(path), Inches(left), Inches(top), Inches(width)
    )
    picture.line.color.rgb = GREY
    picture.line.width = Pt(0.75)
    height = Emu(picture.height).inches
    label(
        slide,
        left,
        top + height + 0.04,
        width,
        0.38,
        caption,
        size=size,
        color=RGBColor(0x33, 0x33, 0x33),
    )
    return picture


# --------------------------------------------------------------------------- #
# the deck
# --------------------------------------------------------------------------- #

TITLE = (
    "Travel Yantra — AI Based Personalized Travel Itinerary Planner "
    "and Virtual Tour Guide with Multilingual Support"
)
TEAM = [
    "Nithin G (1BY23IS140)",
    "Pushkar Reddy S (1BY23IS167)",
    "Rishab Paul (1BY23IS175)",
    "Rohan Balu (1BY23IS177)",
]


def slide_title(prs) -> None:
    slide = prs.slides[T_TITLE]
    body = body_of(slide)
    paragraphs = body.text_frame.paragraphs
    paragraphs[3].runs[0].text = TITLE
    paragraphs[3].runs[0].font.size = Pt(24)
    for i, member in enumerate(TEAM):
        paragraphs[5 + i].runs[0].text = member
    paragraphs[14].runs[0].text = "Prof. Shwetha T"
    paragraphs[15].runs[0].text = "Assistant Professor, Dept. of ISE"


def slide_content(prs) -> None:
    """The template's own agenda, unchanged: it is the mandated running order."""


def slide_abstract(prs) -> None:
    slide = prs.slides[T_ABSTRACT]
    set_body(
        slide,
        [
            (
                0,
                (
                    "Context: Planning a multi-day trip in India means assembling it by "
                    "hand across booking, review and mapping platforms, and almost every "
                    "one of those tools assumes the traveller reads English. At the site "
                    "itself there is no grounded guide to explain what is being looked at."
                ),
            ),
            (
                0,
                (
                    "Problem Identified: Generic large language models are fluent but "
                    "unreliable planners — under one percent of multi-constraint plans "
                    "pass on the TravelPlanner benchmark — and free-form generation "
                    "invents opening hours, fees and history that a traveller cannot check."
                ),
            ),
            (
                0,
                (
                    "Objective: This review demonstrates two of the six project "
                    "objectives in working software: Objective 1, AI-Powered Personalised "
                    "Itinerary Generation, and Objective 5, Virtual Cultural Tour Guide, "
                    "delivered as the feature named Katha."
                ),
            ),
            (
                0,
                (
                    "Methods: A deterministic solver computes the itinerary — candidate "
                    "selection, k-means day clustering, nearest-neighbour and 2-opt "
                    "ordering under opening-hour windows, a validator and a repair loop. "
                    "The language model is confined to parsing the traveller's words and "
                    "narrating what the solver has already decided, over a "
                    "retrieval-augmented corpus in which every paragraph carries a source."
                ),
            ),
            (
                0,
                (
                    "Results: On the seeded demonstration trip the routed itinerary is "
                    "30.9 km against 34.98 km for the same stops visited in list order, "
                    "with 37 of 37 constraint checks passed and a 3 ms build. Retrieval "
                    "reaches Recall@5 of 0.933, all 14 narration segments passed the "
                    "groundedness check, and 101 automated tests pass."
                ),
            ),
        ],
        size=14,
        space=8,
    )


def slide_introduction(prs) -> None:
    slide = prs.slides[T_INTRO]
    head(slide, "INTRODUCTION", size=30)
    set_body(
        slide,
        [
            (
                0,
                (
                    "Travel Yantra is an AI-based personalised itinerary planner and "
                    "virtual tour guide for the Indian tourism context, built for "
                    "travellers who currently plan across several disconnected platforms "
                    "and who are more comfortable in an Indian language than in English."
                ),
            ),
            (
                0,
                (
                    "Phase 1 established the problem, surveyed twenty-two papers and set "
                    "six measurable objectives. Phase 2 is implementation. This review "
                    "presents working software for two of those six objectives, evaluated "
                    "on real data rather than described as intent."
                ),
            ),
            (
                0,
                (
                    "Scope of this review — Objective 1: the planner is an India-wide "
                    "architecture; nothing in the solver is specific to one state. It is "
                    "demonstrated on a Karnataka dataset because that is where our "
                    "verified data currently exists."
                ),
            ),
            (
                0,
                (
                    "Scope of this review — Objective 5: the Katha guide is scoped to "
                    "Karnataka, since every paragraph it can speak has to be written and "
                    "sourced before it can be retrieved."
                ),
            ),
            (
                0,
                (
                    "Related work in one line: TravelPlanner (Xie et al., 2024) showed "
                    "that a single language model fails multi-constraint travel planning; "
                    "ChinaTravel (ICLR 2026) showed that pairing a language model with a "
                    "solver recovers the accuracy. Our architecture follows that finding "
                    "rather than restating the problem."
                ),
            ),
        ],
        size=16,
        space=10,
    )
    place(body_of(slide), left=0.5, top=1.45, width=8.96, height=5.4)


def slide_problem(prs) -> None:
    slide = prs.slides[T_PROBLEM]
    head(slide, "PROBLEM STATEMENT", size=30)
    set_body(
        slide,
        [
            (
                0,
                (
                    "A traveller assembling a three-day trip must reconcile opening "
                    "hours, weekly closing days, entry fees, road time between stops, a "
                    "midday meal, a budget and how far the oldest member of the group can "
                    "walk. These are hard constraints and they interact: fixing one "
                    "breaks another."
                ),
            ),
            (
                0,
                (
                    "Booking and review platforms each solve one slice — flights, hotels, "
                    "reviews, maps — and leave the traveller to be the integration layer. "
                    "None of them sequence a day against opening hours."
                ),
            ),
            (
                0,
                (
                    "General-purpose chat models are fluent but measured to pass under "
                    "one percent of multi-constraint travel plans, and they state fees "
                    "and timings with a confidence they have not earned."
                ),
            ),
            (
                0,
                (
                    "Both classes of tool are English-first, which excludes the traveller "
                    "who would rather read and listen in Kannada or Hindi."
                ),
            ),
            (
                0,
                (
                    "On site, there is no grounded, source-cited guide. This is exactly "
                    "where a fabricated date or fee is least detectable by the listener "
                    "and most damaging to trust."
                ),
            ),
            (
                0,
                (
                    "Stated as an engineering problem: an itinerary must be computed "
                    "against its constraints and be able to show the working — not "
                    "generated and hoped for."
                ),
                True,
            ),
        ],
        size=16,
        space=10,
    )
    place(body_of(slide), left=0.5, top=1.45, width=8.96, height=5.4)


def slide_objectives(prs) -> None:
    slide = prs.slides[T_OBJECTIVES]
    head(slide, "OBJECTIVES OF THE WORK", size=30)
    set_body(
        slide,
        [
            (0, "Demonstrated in this review", True),
            (
                1,
                (
                    "Objective 1 — AI-Powered Personalised Itinerary Generation: "
                    "“Design and implement a multi-agent AI system that generates "
                    "day-by-day itineraries from user preferences, budget, dates and "
                    "group composition, targeting a user satisfaction rate of ninety "
                    "percent or higher.”"
                ),
            ),
            (
                1,
                (
                    "Objective 5 — Virtual Cultural Tour Guide: “Build a "
                    "Retrieval-Augmented Generation based interactive guide for history, "
                    "food, cultural significance and emergency information, with "
                    "sub-three-second response latency.” Delivered as the feature named "
                    "Katha."
                ),
            ),
            (
                0,
                (
                    "Scope: Objective 1 is an India-wide architecture demonstrated on "
                    "Karnataka; Objective 5 is scoped to Karnataka."
                ),
                True,
            ),
            (0, "Deferred to Review 2", True),
            (
                1,
                (
                    "Objective 2 — Multilingual Natural Language Support across Hindi, "
                    "Tamil, Telugu, Kannada and Bengali. English and Kannada are working "
                    "today; the full five-language pipeline is Review-2 work."
                ),
            ),
            (
                1,
                (
                    "Objective 3 — Multi-Channel Deployment and Accessibility across web, "
                    "WhatsApp and voice. The web channel is built; WhatsApp and telephony "
                    "are Review-2 work."
                ),
            ),
            (
                1,
                (
                    "Objective 4 — Real-Time Booking and Route Optimisation against live "
                    "booking and routing APIs."
                ),
            ),
            (
                0,
                (
                    "Objective 6 — Privacy and Cost Constraints is a standing constraint, "
                    "not a milestone: the stack is open-source-first and the measured "
                    "model spend for the whole project to date is under one US dollar."
                ),
            ),
        ],
        size=13.5,
        space=6,
    )
    place(body_of(slide), left=0.5, top=1.20, width=8.96, height=5.7)


# --------------------------------------------------------------------------- #
# methodology: the central claim, drawn
# --------------------------------------------------------------------------- #

PIPELINE = [
    ("1. Structured intake", "form: who, when,\nbudget, pace, tastes", False),
    ("2. Candidate selection", "SQL + interest tags +\nknowledge-graph edges", False),
    ("3. Day clustering", "k-means over (lat, lng),\nfixed seed", False),
    ("4. Ordering", "nearest neighbour, then\n2-opt under hour windows", False),
    ("5. Validator", "hours, closures, day end,\nmeal gap, travel, budget", False),
    ("6. Repair loop", "drops one flexible stop,\nrebuilds that day only", False),
    ("7. Reasons", "one plain sentence per\nstop, from templates", False),
    ("8. Narration", "Katha and chat replies,\nfact-checked after", True),
]


def slide_methodology(prs) -> None:
    slide = prs.slides[T_METHOD]
    head(slide, "METHODOLOGY", size=30)
    set_body(
        slide,
        [
            (
                0,
                (
                    "The language model parses what the traveller writes and narrates "
                    "what has been decided. The itinerary itself is computed by our own "
                    "deterministic solver."
                ),
                True,
            ),
            (
                0,
                (
                    "Seven of the eight stages below are ordinary code with a fixed "
                    "random seed, so the same request always produces the same plan."
                ),
            ),
        ],
        size=14,
        space=4,
    )
    place(body_of(slide), left=0.5, top=1.00, width=8.96, height=1.05)

    top, w, h, gap = 2.30, 2.12, 1.05, 0.14
    for row in (0, 1):
        y = top + row * (h + 0.80)
        for col in range(4):
            index = row * 4 + col
            _stage, detail, is_llm = PIPELINE[index]
            x = 0.55 + col * (w + gap)
            box(
                slide,
                x,
                y,
                w,
                h,
                f"{head}\n{detail}",
                fill=WHITE,
                line=ORANGE if is_llm else BLUE,
                line_width=1.75,
                size=9.5,
                bold=True,
            )
            if col < 3:
                arrow(slide, x + w, y + h / 2, x + w + gap, y + h / 2)
        if row == 0:
            drop = y + h + 0.40
            right = 0.55 + 3 * (w + gap) + w / 2
            arrow(slide, right, y + h, right, drop, color=GREY)
            arrow(slide, right, drop, 0.55 + w / 2, drop, color=GREY)
            arrow(slide, 0.55 + w / 2, drop, 0.55 + w / 2, y + h + 0.80, color=GREY)

    legend_y = 5.42
    box(slide, 0.55, legend_y, 0.22, 0.16, "", fill=BLUE, line=None)
    label(
        slide,
        0.85,
        legend_y - 0.03,
        3.5,
        0.25,
        "Our code — deterministic, seeded",
        size=10,
    )
    box(slide, 4.35, legend_y, 0.22, 0.16, "", fill=ORANGE, line=None)
    label(
        slide,
        4.65,
        legend_y - 0.03,
        4.2,
        0.25,
        "Large language model — language only",
        size=10,
    )
    label(
        slide,
        0.55,
        5.78,
        8.9,
        0.9,
        "The model is also used to parse a chat edit into a strict JSON instruction "
        "(stage 1 on a later turn). It never chooses a stop, a time or an order; a "
        "message it cannot parse becomes one clarifying question, not a guess.",
        size=11,
        italic=True,
        color=RGBColor(0x33, 0x33, 0x33),
    )


def slide_methodology_2(slide) -> None:
    head(slide, "METHODOLOGY (contd.)", size=30)
    set_body(
        slide,
        [
            (
                0,
                (
                    "The validator is the contract. A plan is only returned once every "
                    "check passes, or the request is refused with the arithmetic shown."
                ),
                True,
            )
        ],
        size=14,
        space=2,
    )
    place(body_of(slide), left=0.5, top=1.00, width=8.96, height=0.5)

    # left: the repair flowchart
    label(
        slide,
        0.55,
        1.60,
        4.6,
        0.25,
        "Repair loop (maximum eight iterations)",
        size=11,
        bold=True,
    )
    cx, w, h = 0.55, 2.60, 0.5
    steps = [
        ("Build the day", BLUE),
        ("Validate: 6 checks per day", BLUE),
        ("Any violation?", GREY),
    ]
    y = 1.95
    for text, colour in steps:
        shape = MSO_SHAPE.DIAMOND if text.endswith("?") else MSO_SHAPE.ROUNDED_RECTANGLE
        box(
            slide,
            cx,
            y,
            w,
            h if shape != MSO_SHAPE.DIAMOND else 0.62,
            text,
            line=colour,
            line_width=1.5,
            size=10,
            shape=shape,
            bold=True,
        )
        y += 0.86
    box(
        slide,
        cx,
        y + 0.06,
        w,
        0.62,
        "Drop the lowest-scoring flexible\nstop of the least-repaired day",
        line=RED,
        line_width=1.5,
        size=9.5,
        bold=True,
    )
    box(
        slide,
        cx + w + 0.35,
        3.67,
        1.45,
        0.5,
        "Plan returned",
        line=BLUE,
        fill=SAND,
        line_width=1.5,
        size=10,
        bold=True,
    )
    arrow(slide, cx + w / 2, 2.45, cx + w / 2, 2.81)
    arrow(slide, cx + w / 2, 3.31, cx + w / 2, 3.67)
    arrow(slide, cx + w, 3.98, cx + w + 0.35, 3.92)
    label(slide, cx + w + 0.02, 3.66, 0.35, 0.2, "no", size=9)
    arrow(slide, cx + w / 2, 4.29, cx + w / 2, 4.61)
    label(slide, cx + w / 2 + 0.06, 4.33, 0.4, 0.2, "yes", size=9)
    arrow(slide, cx, 4.90, cx - 0.30, 4.90, color=RED)
    arrow(slide, cx - 0.30, 4.90, cx - 0.30, 2.20, color=RED)
    arrow(slide, cx - 0.30, 2.20, cx, 2.20, color=RED)
    label(
        slide,
        0.55,
        5.30,
        4.5,
        0.75,
        "The fixed-time anchor of a day is never dropped. Only the day named by the "
        "violation is rebuilt; every other day is left byte-for-byte identical.",
        size=10,
        italic=True,
        color=RGBColor(0x33, 0x33, 0x33),
    )

    # right: why a solver
    label(
        slide,
        5.35,
        1.60,
        4.1,
        0.25,
        "Why a solver and not the model alone",
        size=11,
        bold=True,
    )
    label(
        slide,
        5.35,
        1.92,
        4.1,
        0.3,
        "Final pass rate on multi-constraint travel planning",
        size=9.5,
        color=RGBColor(0x33, 0x33, 0x33),
    )
    bar(slide, 5.35, 2.28, 0.30, 0.34, fill=RED, text="")
    label(
        slide,
        5.72,
        2.31,
        3.6,
        0.3,
        "~1%   Single LLM agent (GPT-4)",
        size=10,
        bold=True,
    )
    label(
        slide,
        5.35,
        2.66,
        4.1,
        0.25,
        "TravelPlanner, Xie et al., 2024 [1]",
        size=8.5,
        italic=True,
        color=GREY,
    )
    bar(slide, 5.35, 3.02, 3.55, 0.34, fill=BLUE, text="~97%")
    label(
        slide,
        5.35,
        3.42,
        4.1,
        0.25,
        "LLM paired with a solver — ChinaTravel, ICLR 2026 [2]",
        size=8.5,
        italic=True,
        color=GREY,
    )
    label(
        slide,
        5.35,
        3.80,
        4.1,
        1.9,
        "Both figures are as reported by those papers. They are the reason the "
        "planner in this project is a solver and the model is kept out of the "
        "decision: the failure mode being avoided is measured, not assumed.\n\n"
        "Our own constraint result on the demonstration trip — 37 of 37 checks "
        "passed — is reported on the results slide.",
        size=10.5,
        color=INK,
    )


# --------------------------------------------------------------------------- #
# demonstration
# --------------------------------------------------------------------------- #

SHOT_ROWS = [
    [
        (
            "01-landing.png",
            "Landing page. The Day 2 map is drawn from the live plan in the database — no mock data on any page.",
        ),
        (
            "04-form-step1.png",
            "Structured intake, step 1 of 3: origin, destinations, dates, departure window and local transport.",
        ),
        (
            "07-building.png",
            "Build trace, every figure read back from PlanMetrics: 27 candidates of 112, 3 clusters, 34.98 km listed to 30.9 km routed, 37/37 checks, 3 repairs.",
        ),
        (
            "08-chooser.png",
            "Three ranked plans from three scoring variants, each with its real entry-fee total and comfort verdict.",
        ),
    ],
    [
        (
            "09-plan-routed.png",
            "Plan view: day tabs, the timed rail with travel legs, and the day map. The filled pin is the fixed-time stop.",
        ),
        (
            "10-plan-day2-listed.png",
            "The same Day 2 drawn as listed — visiting the stops in candidate order costs 10.53 km.",
        ),
        (
            "11-plan-day2-trace.png",
            "The trace drawer: every stage of the computation for the day on screen, including the fixes made.",
        ),
        (
            "12-plan-chat-edit.png",
            "A chat edit rebuilds Day 2 only. Days 1 and 3 are byte-for-byte identical, and the reply says so.",
        ),
    ],
    [
        (
            "17-katha-city.png",
            "Katha player: segments typed hook, story, fact or taste, each carrying the source it was built from.",
        ),
        (
            "18-katha-playing.png",
            "Sarvam speech playing from the on-disk cache; the browser voice is the fallback when speech is unavailable.",
        ),
        (
            "19-doesnt-fit.png",
            "Mysuru and Hampi in one day: refused, with the arithmetic shown and three buildable alternatives.",
        ),
    ],
]


def slide_demo(slide, rows, part: int, total: int) -> None:
    set_title(
        slide,
        "DEMONSTRATION OF PROJECT EXECUTION"
        + ("" if part == 1 else f" (contd. {part}/{total})"),
    )
    place(title_of(slide), left=0.5, top=0.17, width=9.26, height=0.72)
    for run in title_of(slide).text_frame.paragraphs[0].runs:
        run.font.size = Pt(24)
    body = body_of(slide)
    body._element.getparent().remove(body._element)
    w = 3.95
    for i, (name, caption) in enumerate(rows):
        left = 0.55 + (i % 2) * (w + 0.5)
        top = 1.10 + (i // 2) * 2.92
        shot(slide, name, left, top, w, caption)


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #


def slide_results(prs) -> None:
    slide = prs.slides[T_RESULTS]
    head(slide, "Experimental Setup, Results & Analysis", size=28, height=0.72)
    set_body(
        slide,
        [
            (
                0,
                (
                    "Setup: Python 3.12 and FastAPI against Supabase PostgreSQL 17 with "
                    "pgvector and pg_trgm; embeddings computed locally with "
                    "multilingual-e5-small; speech from Sarvam bulbul:v3. Planner and "
                    "retrieval are measured by their own harnesses, offline where they "
                    "can be, so the numbers are reproducible."
                ),
                False,
            )
        ],
        size=12.5,
        space=2,
    )
    place(body_of(slide), left=0.5, top=0.92, width=8.96, height=0.85)

    label(
        slide,
        0.55,
        1.82,
        4.2,
        0.25,
        "Data the system was built on",
        size=11.5,
        bold=True,
    )
    table(
        slide,
        0.55,
        2.10,
        4.15,
        [
            ["Dataset", "Count"],
            ["Points of interest", "112"],
            ["Verified against live sources", "20"],
            ["Of those 20, corrected by verification", "16"],
            ["Live corpus paragraphs", "257"],
            ["Paragraphs marked legend", "24"],
        ],
        col_widths=[3.05, 1.10],
        size=10,
        head_size=10,
    )
    label(
        slide,
        0.55,
        3.92,
        4.15,
        0.75,
        "Sixteen of the twenty verified entries were wrong before we checked them. "
        "That ratio is the argument for verifying rather than trusting.",
        size=10,
        italic=True,
        color=RGBColor(0x33, 0x33, 0x33),
    )

    label(slide, 0.55, 4.72, 4.15, 0.25, "Module-wise status", size=11.5, bold=True)
    table(
        slide,
        0.55,
        5.00,
        4.15,
        [
            ["Module", "State"],
            ["Planner (cluster, route, validate, repair)", "Working"],
            ["Retrieval and Katha builder", "Working"],
            ["Narration with post-check", "Working"],
            ["Speech (Sarvam, cached)", "Working"],
            ["Web application and chat", "Working"],
        ],
        col_widths=[3.15, 1.00],
        size=9.5,
        head_size=9.5,
    )

    label(
        slide,
        5.10,
        1.82,
        4.35,
        0.25,
        "Planner, on the seeded demonstration trip",
        size=11.5,
        bold=True,
    )
    # One scale for all four bars (2.55 in = 34.98 km), so Day 2 cannot be read
    # as though it were the whole trip. Labels sit outside the short bars.
    scale = 2.55 / 34.98
    rows = [
        (2.34, "Whole trip, as listed", 34.98, RED),
        (2.70, "Whole trip, as routed", 30.90, BLUE),
        (3.16, "Day 2, as listed", 10.53, RED),
        (3.52, "Day 2, as routed", 6.45, BLUE),
    ]
    for y, name, value, colour in rows:
        bar(slide, 6.45, y, value * scale, 0.28, fill=colour, text="")
        label(slide, 5.10, y + 0.03, 1.30, 0.25, name, size=9.5, align=PP_ALIGN.RIGHT)
        label(
            slide,
            6.50 + value * scale,
            y + 0.02,
            1.05,
            0.25,
            f"{value:g} km",
            size=9.5,
            bold=True,
        )
    label(
        slide,
        5.10,
        3.86,
        4.35,
        0.22,
        "Same scale for all four bars.",
        size=8.5,
        italic=True,
        color=GREY,
    )
    table(
        slide,
        5.10,
        4.18,
        4.35,
        [
            ["Planner measure", "Result"],
            ["Constraint checks passed", "37 / 37"],
            ["Repairs applied", "3"],
            ["Candidates considered", "27 of 112"],
            ["Build time", "3 ms"],
        ],
        col_widths=[3.15, 1.20],
        size=10,
        head_size=10,
    )
    label(
        slide,
        5.10,
        5.68,
        4.35,
        0.85,
        "“As listed” is the same stops visited in candidate order — what an "
        "itinerary that never routes produces. It is the honest baseline, because "
        "nearest-neighbour was already optimal here.",
        size=10,
        italic=True,
        color=RGBColor(0x33, 0x33, 0x33),
    )


def slide_results_2(slide) -> None:
    head(slide, "Experimental Setup, Results & Analysis (contd.)", size=24, height=0.66)
    body = body_of(slide)
    body._element.getparent().remove(body._element)

    label(
        slide,
        0.55,
        1.00,
        5.6,
        0.25,
        "Retrieval — Recall@5 over the evaluation set",
        size=11.5,
        bold=True,
    )
    table(
        slide,
        0.55,
        1.30,
        5.55,
        [
            ["Method", "Recall@5", "Kannada-only", "p50 latency"],
            ["Dense (pgvector, e5)", "0.933", "0.833", "58 ms"],
            ["Lexical (tsvector)", "0.733", "0.333", "—"],
            ["Hybrid + RRF", "0.933", "—", "116 ms"],
        ],
        col_widths=[2.25, 1.05, 1.20, 1.05],
        size=10,
        head_size=10,
    )
    label(
        slide,
        0.55,
        2.60,
        5.55,
        1.5,
        "Reported honestly: hybrid retrieval tied dense rather than beating it, at "
        "twice the latency. We kept it for one measured reason — lexical retrieval is "
        "perfect on exact proper nouns (MRR 1.000 on name lookups), which is how a "
        "traveller actually searches for a monument. Dense retrieval dominates on "
        "Kannada, where the English index has almost nothing to match.",
        size=10.5,
    )
    label(
        slide,
        0.55,
        4.05,
        5.55,
        1.2,
        "Also reported: Recall@5 fell from 0.933 to 0.867 after we merged our "
        "hand-written corpus into the generated one, because three hand-written "
        "answers phrase things differently from the evaluation questions. We did not "
        "tune the benchmark back up. The number stands as measured.",
        size=10.5,
        bold=True,
    )

    label(slide, 6.35, 1.00, 3.1, 0.25, "Grounding and refusal", size=11.5, bold=True)
    table(
        slide,
        6.35,
        1.30,
        3.10,
        [
            ["Measure", "Result"],
            ["Narration segments passing", "14 / 14"],
            ["Refusal gate", "6 / 6"],
            ["Automated tests", "101"],
        ],
        col_widths=[2.05, 1.05],
        size=10,
        head_size=10,
    )
    label(
        slide,
        6.35,
        2.60,
        3.10,
        2.6,
        "Every narrated segment is checked after generation against the paragraphs "
        "it was given: any year, number or English proper name that is not in the "
        "source fails the check, and the segment is retried and then replaced by the "
        "corpus text itself.\n\n"
        "The refusal gate is the opposite test — six questions the corpus cannot "
        "answer, all six refused rather than answered.",
        size=10.5,
    )
    label(
        slide,
        0.55,
        5.45,
        8.9,
        0.8,
        "Analysis: the planner result is a constraint-satisfaction result, not an "
        "opinion — 37 of 37 checks on a trip with an elder, a child, a fixed-time "
        "palace slot and a 7 pm curfew. The retrieval result is reported as measured, "
        "including the regression, because a benchmark that only moves upward is not "
        "a benchmark.",
        size=11,
        italic=True,
    )


def slide_status(prs) -> None:
    slide = prs.slides[T_STATUS]
    head(slide, "PROJECT STATUS, CONCLUSION", size=28, height=0.72)
    body = body_of(slide)
    body._element.getparent().remove(body._element)

    columns = [
        (
            "Completed",
            BLUE,
            (
                "Database and schema\nDeterministic planner\nHybrid retrieval\nKatha builder\n"
                "Narration with fact-check\nSarvam speech, cached\nChat repair, one day\n"
                "Web application\nEvaluation harness"
            ),
        ),
        (
            "In progress",
            YELLOW,
            "Corpus breadth beyond\nthe five current regions\n\nInternal code review",
        ),
        (
            "Not started — Review 2",
            GREY,
            (
                "Objective 2: full five-\nlanguage support\n\nObjective 3: WhatsApp and\nvoice channels\n\n"
                "Objective 4: live booking\nand routing APIs"
            ),
        ),
    ]
    for i, (column, colour, items) in enumerate(columns):
        x = 0.55 + i * 3.03
        box(
            slide,
            x,
            1.00,
            2.85,
            0.40,
            column,
            fill=colour,
            color=WHITE if colour is not YELLOW else INK,
            line=None,
            size=11.5,
            bold=True,
            shape=MSO_SHAPE.RECTANGLE,
        )
        box(
            slide,
            x,
            1.40,
            2.85,
            2.30,
            items,
            fill=WHITE,
            line=colour,
            size=10.5,
            align=PP_ALIGN.LEFT,
            shape=MSO_SHAPE.RECTANGLE,
            anchor=MSO_ANCHOR.TOP,
        )

    label(
        slide,
        0.55,
        3.90,
        8.9,
        0.25,
        "Known limits, stated plainly",
        size=11.5,
        bold=True,
    )
    limits = [
        (
            "92 of the 112 points of interest are still unverified draft data; the "
            "interface labels them as estimated rather than hiding it."
        ),
        (
            "Coorg has a single midday food stop in our data, so a long Coorg day trips "
            "the meal-gap rule. The rule is right; the data is thin."
        ),
        (
            "Map routes are drawn as straight segments between stops, not road-shaped "
            "geometry. Distances use a detour factor, so the kilometres are honest but "
            "the drawing is schematic."
        ),
        (
            "The system runs on localhost for this review; deployment is a post-review "
            "decision recorded in the project log."
        ),
    ]
    y = 4.20
    for text in limits:
        box(
            slide,
            0.55,
            y,
            0.10,
            0.10,
            "",
            fill=RED,
            line=None,
            shape=MSO_SHAPE.RECTANGLE,
        )
        label(slide, 0.78, y - 0.05, 8.65, 0.5, text, size=10.5)
        y += 0.50

    label(
        slide,
        0.55,
        6.25,
        8.9,
        0.6,
        "Conclusion: two of six objectives are demonstrated in working software, "
        "measured rather than asserted. The planner computes and proves its "
        "itineraries; the guide speaks only what a source supports, and refuses when "
        "it has nothing.",
        size=11.5,
        bold=True,
    )


def slide_publication(prs) -> None:
    slide = prs.slides[T_PUB]
    head(slide, "PUBLICATION", size=30)
    set_body(
        slide,
        [
            (
                0,
                (
                    "Planned contribution: IndiaTravel — the first India-specific "
                    "benchmark for travel-planning AI agents."
                ),
                True,
            ),
            (
                1,
                (
                    "Modelled on ChinaTravel (ICLR 2026), which built the equivalent "
                    "benchmark for Chinese travel and showed that a language model paired "
                    "with a solver reaches roughly ninety-seven percent where a single "
                    "model reaches about one percent."
                ),
            ),
            (
                1,
                (
                    "The novelty is the constraint set. India-specific constraints have "
                    "no counterpart in the existing benchmarks: temple darshan windows and "
                    "midday closures, weekly closing days, festival and Dasara crowding, "
                    "monsoon access to hill roads, vegetarian and Jain food requirements, "
                    "multi-generational parties with an elder's walking limit, and "
                    "state-boundary transport changes."
                ),
            ),
            (
                1,
                (
                    "Our planner, its validator and the 112-place verified dataset are "
                    "the working reference implementation the benchmark would be released "
                    "alongside."
                ),
            ),
            (
                0,
                (
                    "Target: a Scopus-indexed conference or journal. Drafting begins "
                    "after Review 2, once the multilingual and multi-channel objectives "
                    "provide the second half of the evaluation."
                ),
                True,
            ),
            (
                0,
                (
                    "The report will be prepared in LaTeX and checked through Turnitin, "
                    "to remain under the fifteen percent similarity requirement."
                ),
            ),
        ],
        size=13,
        space=7,
    )
    place(body_of(slide), left=0.5, top=1.05, width=8.96, height=5.8)


REFERENCES = [
    (
        "J. Xie, K. Zhang, J. Chen, T. Zhu, R. Lou, Y. Tian, Y. Xiao and Y. Su, "
        "“TravelPlanner: A Benchmark for Real-World Planning with Language Agents,” in "
        "Proc. 41st Int. Conf. Machine Learning (ICML), 2024."
    ),
    (
        "X.-Y. Shao et al., “ChinaTravel: A Real-World Benchmark for Language Agents in "
        "Chinese Travel Planning,” in Proc. Int. Conf. Learning Representations (ICLR), 2026."
    ),
    (
        "P. Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive NLP "
        "Tasks,” in Adv. Neural Inf. Process. Syst. (NeurIPS), vol. 33, 2020, pp. 9459–9474."
    ),
    (
        "J. Gala et al., “IndicTrans2: Towards High-Quality and Accessible Machine "
        "Translation Models for all 22 Scheduled Indian Languages,” Trans. Machine "
        "Learning Research, 2023."
    ),
    (
        "L. Wang, N. Yang, X. Huang, L. Yang, R. Majumder and F. Wei, “Multilingual E5 "
        "Text Embeddings: A Technical Report,” arXiv:2402.05672, 2024."
    ),
    (
        "G. V. Cormack, C. L. A. Clarke and S. Buettcher, “Reciprocal Rank Fusion "
        "Outperforms Condorcet and Individual Rank Learning Methods,” in Proc. 32nd Int. "
        "ACM SIGIR Conf., 2009, pp. 758–759."
    ),
    (
        "G. A. Croes, “A Method for Solving Traveling-Salesman Problems,” Operations "
        "Research, vol. 6, no. 6, pp. 791–812, 1958."
    ),
    (
        "D. Arthur and S. Vassilvitskii, “k-means++: The Advantages of Careful Seeding,” "
        "in Proc. 18th ACM-SIAM Symp. Discrete Algorithms (SODA), 2007, pp. 1027–1035."
    ),
    (
        "S. P. Lloyd, “Least Squares Quantization in PCM,” IEEE Trans. Information "
        "Theory, vol. 28, no. 2, pp. 129–137, 1982."
    ),
    (
        "E. W. Dijkstra, “A Note on Two Problems in Connexion with Graphs,” Numerische "
        "Mathematik, vol. 1, pp. 269–271, 1959."
    ),
]


def slide_references(slide) -> None:
    head(slide, "REFERENCES (IEEE FORMAT)", size=28, height=0.70)
    set_body(
        slide,
        [(0, f"[{i}] {text}", False) for i, text in enumerate(REFERENCES, 1)],
        size=10,
        space=4,
    )
    place(body_of(slide), left=0.5, top=1.02, width=8.96, height=5.95)


def main() -> int:
    prs = Presentation(str(TEMPLATE))

    slide_title(prs)
    slide_content(prs)
    slide_abstract(prs)
    slide_introduction(prs)
    slide_problem(prs)
    slide_objectives(prs)
    slide_methodology(prs)
    slide_results(prs)
    slide_status(prs)
    slide_publication(prs)

    # Continuations, duplicated from the template slide of the same section.
    method_2 = duplicate(prs, T_METHOD)
    slide_methodology_2(method_2)
    demo_slides = [prs.slides[T_DEMO]] + [duplicate(prs, T_DEMO) for _ in range(2)]
    for i, (slide, rows) in enumerate(
        zip(demo_slides, SHOT_ROWS, strict=True), start=1
    ):
        slide_demo(slide, rows, i, len(SHOT_ROWS))
    results_2 = duplicate(prs, T_RESULTS)
    slide_results_2(results_2)
    references = duplicate(prs, T_PUB)
    slide_references(references)

    # Template order, with each continuation directly after its own section.
    reorder(prs, [0, 1, 2, 3, 4, 5, 6, 11, 7, 12, 13, 8, 14, 9, 10, 15])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"{OUT.relative_to(ROOT)}  —  {len(prs.slides)} slides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
