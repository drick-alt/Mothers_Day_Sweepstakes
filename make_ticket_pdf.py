#!/usr/bin/env python3
"""Render printed raffle stubs onto Avery 16795 ticket stock.

AVERY 16795 -- "Tickets With Tear-Away Stubs", 1-3/4" x 5-1/2", 10 per sheet.
Source: https://www.avery.com/templates/16795
Compatible stock numbers: 16154, 76154, 95288, 99154.

GEOMETRY NOTE (important -- read before printing a full run)

  Avery's published numbers do not close arithmetically. Ten tickets at a
  true 1.75 x 5.5 need 96.25 sq in of ink area; a Letter sheet has 93.50.
  The layout that DOES close exactly is:

      5 columns x 1.70 in  =  8.50 in  (Letter width,  exact)
      2 rows    x 5.50 in  = 11.00 in  (Letter height, exact)

  So the real die is ~1.70" x 5.50" and Avery rounds it to "1-3/4".
  The sheet feeds PORTRAIT with tickets standing VERTICAL, 5 across and
  2 down. Tear one out, turn it 90 degrees, and you are holding a
  5.5" x 1.7" horizontal raffle ticket.

  Therefore: the PDF page is portrait Letter and each ticket design is
  drawn ROTATED 90 degrees into a 5.50 x 1.70 design canvas.

  TICKET_W_IN is the one number to nudge if your sheets mis-register.
  Run with --calibrate first and check against a real sheet.

Usage:
  python make_ticket_pdf.py avail.csv out.pdf
  python make_ticket_pdf.py --calibrate out.pdf
"""
import csv
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------- geometry
PAGE_W, PAGE_H = letter          # 8.5 x 11 portrait

TICKET_W_IN = 1.70               # across the sheet; 5 x 1.70 = 8.50 exact
TICKET_H_IN = 5.50               # down the sheet;   2 x 5.50 = 11.00 exact
COLS, ROWS = 5, 2                # = 10 per sheet, per Avery

CELL_W = TICKET_W_IN * inch
CELL_H = TICKET_H_IN * inch

# Sheet is edge-to-edge by design, so origin is 0,0 with no outer margin.
ORIGIN_X = (PAGE_W - COLS * CELL_W) / 2.0
ORIGIN_Y = (PAGE_H - ROWS * CELL_H) / 2.0

# Rotated design canvas: long axis horizontal.
DES_W, DES_H = CELL_H, CELL_W    # 5.50in wide x 1.70in tall

# Safety inset so ink never rides the die cut.
BLEED = 0.055 * inch

# Tear-away stub, right end. Widened from 0.265 to give the three
# write-in lines comfortable row spacing once rotated.
STUB_W = DES_W * 0.295

# Resolve assets relative to this file so the script works from any
# checkout and any working directory.
ASSETS = Path(__file__).resolve().parent / "static" / "prizes"

ART = str(ASSETS / "ticket_art_clean_v1.jpg")

# Prize thumbnails shown on the holder half.
PRIZE_IMGS = [
    str(ASSETS / "thumb_ao.jpg"),
    str(ASSETS / "thumb_mcm.jpg"),
]

TITLE_ORG = "TRAINED TO GO M.C."
# Hyphen, not slash: matches how JB writes it and the live campaign record
# ("Mother's Day- Father's Day Sweepstakes Drawing"), spacing normalised.
TITLE_EVENT = "Mother's Day - Father's Day Sweepstakes Drawing"

# Front of ticket. The NO PURCHASE NECESSARY / free-entry disclosure and
# the rules URL moved to the BACK (see draw_back_design / --backs), so the
# front carries only the eligibility line.
ELIGIBILITY = "Must be 18yrs or older to enter"
CLAIM = "Retain this half to claim."

# Back of ticket -- the AMOE disclosure that used to sit on the front.
BACK_HEAD = "NO PURCHASE NECESSARY"
# Flowed, not hand-wrapped: hand-wrapped lines left the right 60% of the
# ticket empty because they were measured against the old narrow column.
BACK_BODY = (
    "A purchase or payment of any kind will not increase your chances of "
    "winning. Void where prohibited by law. Open to legal residents of the "
    "United States who are 18 years of age or older."
)
BACK_AMOE = (
    "FREE METHOD OF ENTRY: hand print your full name, complete mailing "
    "address, email address, daytime phone number, date of birth and the "
    "words \"FREE ENTRY REQUEST\" on a 3\" x 5\" card and mail it in a "
    "hand-addressed envelope with proper postage to:"
)
BACK_ADDR = [
    "Mother's Day- Father's Day Sweepstakes Drawing, ATTN: Free Entry",
    "5456 Peachtree Blvd, Suite 134, Atlanta, GA 30341",
]
BACK_TAIL = (
    "Limit one (1) entry per outer mailing envelope. Mail-in entries "
    "receive one (1) entry at no cost and have the SAME chance of winning "
    "as entries obtained by purchase."
)
BACK_RULES = "Full Official Rules: mothers-day-sweepstakes.onrender.com/rules/6"

INK = HexColor("#111111")
MUTED = HexColor("#5b5b5b")
GOLD = HexColor("#c9a227")
WINE = HexColor("#7a1f3d")
# Cream plate the burgundy org name sits on. True burgundy on the near-black
# title bar measures 1.87:1 contrast -- effectively invisible in print. The
# plate keeps the colour authentically deep AND legible.
CREAM = HexColor("#f0e6d2")
RULE = HexColor("#cccccc")

PAD = 0.085 * inch


# ---------------------------------------------------------------- helpers
def fit(c, text, font, size, max_w):
    while size > 2.8 and c.stringWidth(text, font, size) > max_w:
        size -= 0.1
    return size


def draw_fitted(c, text, x, y, font, size, max_w, centred=False):
    s = fit(c, text, font, size, max_w)
    c.setFont(font, s)
    if centred:
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)
    return s


def wrap(c, text, font, size, max_w):
    """Greedy word-wrap into lines that each fit max_w."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and c.stringWidth(trial, font, size) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def draw_art(c, x, y, w, h, img):
    """Cover-fit artwork into the box, cropping overflow."""
    iw, ih = img.getSize()
    scale = max(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    c.saveState()
    p = c.beginPath()
    p.rect(x, y, w, h)
    c.clipPath(p, stroke=0, fill=0)
    # Bias the crop so the faces land in the upper band of the strip and
    # the dark top of the frame -- not a face -- falls under the scrim.
    c.drawImage(img, x - (dw - w) / 2, y - (dh - h) * 0.46, dw, dh,
                preserveAspectRatio=False, mask="auto")
    c.restoreState()


def draw_thumb(c, path_img, x, y, w, h):
    """Contain-fit a prize thumbnail: whole image, never cropped.

    A dark plate is drawn behind it so the product reads against the photo,
    and the gold hairline is drawn around the IMAGE, not the nominal box --
    otherwise a portrait product floats inside a square frame.
    """
    iw, ih = path_img.getSize()
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    ox, oy = x + (w - dw) / 2, y + (h - dh) / 2

    pad = 0.022 * inch
    c.saveState()
    c.setFillColor(black)
    c.setFillAlpha(0.55)
    c.rect(ox - pad, oy - pad, dw + 2 * pad, dh + 2 * pad, stroke=0, fill=1)
    c.restoreState()

    c.drawImage(path_img, ox, oy, dw, dh,
                preserveAspectRatio=True, mask="auto")
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.45)
    c.rect(ox - pad, oy - pad, dw + 2 * pad, dh + 2 * pad, stroke=1, fill=0)


def draw_design(c, number, code, img, prize_imgs):
    """Draw one ticket into a DES_W x DES_H box with origin at (0, 0)."""
    body_w = DES_W - STUB_W

    # ---- artwork across the holder body ----
    draw_art(c, 0, 0, body_w, DES_H, img)

    # ---- title bar across the top ----
    # Scrim first so the title reads over the photo regardless of crop.
    # 0.33in (was 0.30in) to carry the larger event line without its
    # descenders riding the bar edge.
    title_h = 0.33 * inch
    c.saveState()
    c.setFillColor(black)
    c.setFillAlpha(0.74)
    c.rect(0, DES_H - title_h, body_w, title_h, stroke=0, fill=1)
    c.restoreState()

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.7)
    c.line(0, DES_H - title_h, body_w, DES_H - title_h)

    # Event name is the dominant line; the org sits above it as a smaller
    # burgundy presenter credit on a cream plate.
    org_size = fit(c, TITLE_ORG, "Helvetica-Bold", 6.0, body_w - 2 * PAD)
    org_w = c.stringWidth(TITLE_ORG, "Helvetica-Bold", org_size)
    plate_pad_x, plate_pad_y = 0.05 * inch, 0.022 * inch
    plate_y = DES_H - 0.118 * inch - plate_pad_y
    c.setFillColor(CREAM)
    c.roundRect(body_w / 2 - org_w / 2 - plate_pad_x, plate_y,
                org_w + 2 * plate_pad_x,
                org_size / 72.0 * inch + 2 * plate_pad_y - 0.012 * inch,
                0.028 * inch, stroke=0, fill=1)
    c.setFillColor(WINE)
    c.setFont("Helvetica-Bold", org_size)
    c.drawCentredString(body_w / 2, DES_H - 0.118 * inch, TITLE_ORG)

    c.setFillColor(white)
    draw_fitted(c, TITLE_EVENT, body_w / 2, DES_H - 0.272 * inch,
                "Helvetica-Bold", 9.5, body_w - 2 * PAD, centred=True)

    # ---- legibility scrim along the bottom ----
    # Deepened from 0.40in to 0.52in so the prize thumbnails can live
    # INSIDE this block alongside the ticket number. Sitting them up in
    # the photo covered the man on the right.
    band_h = 0.52 * inch
    c.saveState()
    c.setFillColor(black)
    c.setFillAlpha(0.78)
    c.rect(0, 0, body_w, band_h, stroke=0, fill=1)
    c.restoreState()

    # ---- prize thumbnails: bottom-right, inside the scrim block ----
    th_h = band_h - 0.09 * inch
    th_gap = 0.04 * inch
    widths = []
    for pim in prize_imgs:
        iw, ih = pim.getSize()
        widths.append(th_h * (iw / ih))
    row_w = sum(widths) + th_gap * (len(prize_imgs) - 1)
    tx = body_w - row_w - PAD
    ty = (band_h - th_h) / 2
    for pim, w in zip(prize_imgs, widths):
        draw_thumb(c, pim, tx, ty, w, th_h)
        tx += w + th_gap

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.7)
    c.line(0, band_h, body_w, band_h)

    # ---- ticket identity ----
    # Text must stop before the thumbnail row, not run under it.
    text_w = (body_w - row_w - PAD) - PAD - 0.05 * inch

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(PAD, band_h - 0.195 * inch, number)

    nw = c.stringWidth(number, "Helvetica-Bold", 11)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 7.6)
    c.drawString(PAD + nw + 0.075 * inch, band_h - 0.193 * inch, code)

    # ---- eligibility line (AMOE now lives on the back) ----
    c.setFillColor(white)
    draw_fitted(c, ELIGIBILITY, PAD, band_h - 0.335 * inch,
                "Helvetica-Bold", 5.6, text_w)
    c.setFillColor(HexColor("#cfcfcf"))
    draw_fitted(c, CLAIM, PAD, band_h - 0.435 * inch,
                "Helvetica-Oblique", 4.6, text_w)

    # ---- perforation ----
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.5)
    c.setDash(1.7, 1.7)
    c.line(body_w, BLEED, body_w, DES_H - BLEED)
    c.setDash()

    # ---- tear-away stub (contents rotated 90deg) ----
    #
    # The stub block is 1.46in wide x 1.70in tall in reading orientation.
    # Laying the write-in lines HORIZONTALLY caps them at ~1.29in. Rotating
    # the stub's contents 90deg runs them along the 1.70in axis instead,
    # giving ~1.53in of writing length -- about 19% more -- which is what
    # makes room for a third line (email).
    #
    # Line length is bounded by the ticket HEIGHT, so 1.53in is the hard
    # ceiling here; widening the stub buys row spacing, not line length.
    c.saveState()
    c.translate(body_w + STUB_W, 0)
    c.rotate(90)
    # Local frame: x runs UP the stub (len DES_H), y runs LEFT (len STUB_W).
    s_len, s_thick = DES_H, STUB_W
    sp = 0.075 * inch
    write_w = s_len - 2 * sp

    # header
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 5.1)
    c.drawCentredString(s_len / 2, s_thick - 0.145 * inch, "DRUM COPY")

    # number + code on one row, so the three write-in lines get the space
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 13)
    nw = c.stringWidth(number, "Helvetica-Bold", 13)
    cw = c.stringWidth(code, "Helvetica-Bold", 8)
    gap = 0.07 * inch
    x0 = (s_len - (nw + gap + cw)) / 2
    c.drawString(x0, s_thick - 0.345 * inch, number)
    c.setFillColor(WINE)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + nw + gap, s_thick - 0.335 * inch, code)

    # three write-in lines: Name / Email / Phone
    c.setFillColor(MUTED)
    label_f, label_s = "Helvetica", 4.9
    rows = ("Name", "Email", "Phone")
    # Lower bound sits above the "Deposit in drum" footer -- at 0.135in the
    # Phone rule collided with it. Upper bound keeps clear of the number row.
    top = s_thick - 0.52 * inch
    bottom = 0.225 * inch
    step = (top - bottom) / (len(rows) - 1) if len(rows) > 1 else 0
    for i, lab in enumerate(rows):
        ly = top - i * step
        c.setFont(label_f, label_s)
        c.drawString(sp, ly, lab)
        lw = c.stringWidth(lab, label_f, label_s)
        c.setStrokeColor(HexColor("#999999"))
        c.setLineWidth(0.35)
        c.line(sp + lw + 0.035 * inch, ly - 0.012 * inch,
               sp + write_w, ly - 0.012 * inch)

    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 4.2)
    c.drawCentredString(s_len / 2, 0.072 * inch, "Deposit in drum")
    c.restoreState()


def place(c, col, row, number, code, img, prize_imgs):
    """Rotate the design into the vertical die-cut cell at (col, row)."""
    x = ORIGIN_X + col * CELL_W
    y = PAGE_H - ORIGIN_Y - (row + 1) * CELL_H
    c.saveState()
    # Move to the cell's bottom-right, then rotate 90deg CCW so the
    # design's +x runs UP the sheet and +y runs LEFT.
    c.translate(x + CELL_W, y)
    c.rotate(90)
    draw_design(c, number, code, img, prize_imgs)
    c.restoreState()


def draw_back_design(c):
    """Back of one ticket: the AMOE disclosure moved off the front."""
    m = 0.13 * inch
    tw = DES_W - 2 * m
    x = m
    fs = 5.0

    c.setFillColor(INK)
    draw_fitted(c, BACK_HEAD, DES_W / 2, DES_H - 0.175 * inch,
                "Helvetica-Bold", 8.0, tw, centred=True)

    c.setStrokeColor(HexColor("#999999"))
    c.setLineWidth(0.4)
    c.line(x, DES_H - 0.215 * inch, x + tw, DES_H - 0.215 * inch)

    y = DES_H - 0.325 * inch
    lead = 0.093 * inch

    def block(text, font="Helvetica", size=fs, gap_after=0.055 * inch,
              indent=0.0):
        nonlocal y
        c.setFillColor(HexColor("#2b2b2b"))
        for ln in wrap(c, text, font, size, tw - indent):
            c.setFont(font, size)
            c.drawString(x + indent, y, ln)
            y -= lead
        y -= gap_after

    block(BACK_BODY)
    block(BACK_AMOE)
    c.setFillColor(INK)
    for ln in BACK_ADDR:
        c.setFont("Helvetica-Bold", fs)
        c.drawString(x + 0.14 * inch, y, ln)
        y -= lead
    y -= 0.055 * inch
    block(BACK_TAIL, gap_after=0.0)

    c.setFillColor(INK)
    draw_fitted(c, BACK_RULES, DES_W / 2, 0.085 * inch,
                "Helvetica-Oblique", 4.8, tw, centred=True)


def place_back(c, col, row):
    """Mirror the column so backs register with fronts on a duplex flip.

    Long-edge duplex on a portrait sheet mirrors LEFT-RIGHT, so back cell
    for front column `col` must be drawn at column (COLS-1-col).
    """
    mcol = (COLS - 1) - col
    x = ORIGIN_X + mcol * CELL_W
    y = PAGE_H - ORIGIN_Y - (row + 1) * CELL_H
    c.saveState()
    c.translate(x + CELL_W, y)
    c.rotate(90)
    draw_back_design(c)
    c.restoreState()


def draw_cut_guides(c):
    """Faint die-cut guides -- alignment aid, not part of the artwork."""
    c.setStrokeColor(RULE)
    c.setLineWidth(0.25)
    c.setDash(2, 3)
    for i in range(COLS + 1):
        x = ORIGIN_X + i * CELL_W
        c.line(x, ORIGIN_Y, x, PAGE_H - ORIGIN_Y)
    for j in range(ROWS + 1):
        y = ORIGIN_Y + j * CELL_H
        c.line(ORIGIN_X, y, PAGE_W - ORIGIN_X, y)
    c.setDash()


# ---------------------------------------------------------------- outputs
def calibration(out_path):
    """One plain-paper sheet to hold against real Avery stock."""
    c = canvas.Canvas(out_path, pagesize=letter)
    c.setTitle("Avery 16795 calibration")
    draw_cut_guides(c)

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 0.30 * inch,
                        "AVERY 16795 CALIBRATION -- print at 100%, "
                        "do NOT 'fit to page'")
    c.setFont("Helvetica", 7.6)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H - 0.46 * inch,
        f"cells {COLS} x {ROWS} = {COLS*ROWS} | "
        f"{TICKET_W_IN:.2f}in x {TICKET_H_IN:.2f}in each | "
        "hold against a real sheet; lines must sit on the die cuts")

    for row in range(ROWS):
        for col in range(COLS):
            x = ORIGIN_X + col * CELL_W
            y = PAGE_H - ORIGIN_Y - (row + 1) * CELL_H
            n = row * COLS + col + 1
            c.setFillColor(HexColor("#999999"))
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(x + CELL_W / 2, y + CELL_H / 2, str(n))
            # corner ticks
            c.setStrokeColor(INK)
            c.setLineWidth(0.5)
            t = 0.12 * inch
            for (cx0, cy0, dx, dy) in [
                    (x, y, 1, 1), (x + CELL_W, y, -1, 1),
                    (x, y + CELL_H, 1, -1), (x + CELL_W, y + CELL_H, -1, -1)]:
                c.line(cx0, cy0, cx0 + dx * t, cy0)
                c.line(cx0, cy0, cx0, cy0 + dy * t)

    c.showPage()
    c.save()
    print(f"calibration sheet : {out_path}")


def backs(out_path, n=1100):
    """One-page back design, repeated for every front sheet.

    Pages are column-mirrored so a long-edge duplex flip lands each back
    on its own front. Print this as the reverse pass, or interleave.
    """
    c = canvas.Canvas(out_path, pagesize=letter)
    c.setTitle("Sweepstakes ticket backs -- Avery 16795")
    per_page = COLS * ROWS
    pages = -(-n // per_page)
    for _ in range(pages):
        draw_cut_guides(c)
        for slot in range(per_page):
            place_back(c, slot % COLS, slot // COLS)
        c.showPage()
    c.save()
    print(f"backs             : {out_path}")
    print(f"pages             : {pages} (column-mirrored for duplex)")


def main(csv_path, out_path):
    with open(csv_path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("ticket_number")]
    if not rows:
        raise SystemExit("no ticket rows found in " + csv_path)

    img = ImageReader(ART)
    prize_imgs = [ImageReader(p) for p in PRIZE_IMGS]
    c = canvas.Canvas(out_path, pagesize=letter)
    c.setTitle("Sweepstakes tickets -- Avery 16795")
    per_page = COLS * ROWS

    for i, r in enumerate(rows):
        slot = i % per_page
        if i and slot == 0:
            c.showPage()
        if slot == 0:
            draw_cut_guides(c)
        place(c, slot % COLS, slot // COLS,
              r["ticket_number"], r.get("check_code", ""), img, prize_imgs)

    c.showPage()
    c.save()

    pages = -(-len(rows) // per_page)
    print(f"stock             : Avery 16795 "
          f"({TICKET_W_IN:.2f}in x {TICKET_H_IN:.2f}in, "
          f"{COLS}x{ROWS}={per_page}/sheet)")
    print(f"tickets rendered  : {len(rows)}")
    print(f"pages             : {pages}")
    print(f"output            : {out_path}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--calibrate":
        calibration(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--backs":
        backs(sys.argv[2])
    elif len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        raise SystemExit(
            "usage: make_ticket_pdf.py <csv|--calibrate|--backs> <out.pdf>")
