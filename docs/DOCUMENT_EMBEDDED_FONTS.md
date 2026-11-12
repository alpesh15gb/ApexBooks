# Embedded document fonts

Follow-up to 625400d, local only. Earlier document PDFs used unembedded Helvetica/Helvetica-Bold. Poppler substituted local fonts and the reviewed output had uneven/colliding letter spacing. Report PDFs already used bundled DejaVu fonts.

Document A4 and thermal renderers now register and embed the existing licensed DejaVuSans regular/bold files under document-specific names. Paragraph bold mapping, footer text and raw legacy table cells use those fonts. No font downloads, external font service, tax/total or book changes. The existing font license remains included.

Embedding changes text metrics. The first experimental version moved the nine-line Minimal fixture to three pages; adjusting Minimal body text to 8pt/11pt leading and row padding to 5pt restores two readable pages. Other layouts retain their sizes. This is not a guarantee that arbitrary long content always has two pages.

Final evidence: `docs/evidence/document-fonts-tests.log`, 11 targeted tests passed. A new test visits every visible text run in all 11 layouts and requires an embedded TrueType FontFile2 descriptor and DejaVu base font. An unused default Helvetica resource may remain in the PDF; the test checks actual text, not merely resource names. Source references, regular/unregistered totals, discount disclosure, settlement labels, cancelled exports, repeated restore and the 18 quotation/invoice PDFs pass existing regressions.

Rendered and visually inspected the 58mm supplier partial-refund note, Minimal quotation page 2 and Evergreen quotation page 1. Previously colliding Latin lettering is resolved in these samples. Reference/date, INR 25 used and INR 75 remaining, totals/terms and ROLL are readable without observed clipping. Files: `/workspace/shared/apex-note-embedded` and `/workspace/shared/apex-quotation-embedded`.

Still open: other viewers/physical printers/native acceptance, complex-script shaping and font glyph coverage, tagged-PDF accessibility. No general multilingual or statutory certification. Larger embedded-font PDFs are expected. No publication or deployment.
