# Reconstructed quotation PDF polish

The former local commit 61658e2 was unavailable after workspace replacement. These are new changes on published PR #56, independently reproduced and retested; the original commit's exact bytes were not recovered.

Widen Evergreen's Per column from 6 to 8 relative units and reduce Item by the corresponding amount, preserving table width. Reduce Minimal row padding from 10 to 7 points. The synthetic nine-line quotation/invoice now retains ROLL in one piece and fits notes and terms on its second page.

The new assertions fail on published #56 (both quotation and invoice, Evergreen wrapping and Minimal three-page output) and pass with these changes. All 18 PDF variants retain line text, units, totals, warranty, terms and conversion results. Rendered Evergreen pages 1–2 and Minimal page 2 were inspected without observed clipping. No Windows/Android PDF-viewer or physical-device acceptance was performed in this reconstructed environment. These layout changes do not establish statutory completeness.
