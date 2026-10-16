# Rustproofing source review

Reviewed 25 September 2026. Research only; not yet enabled in the running agent.

The official public Store API returns 103 unique entries in category 126, across two pages. All 103 have corresponding sourced Markdown captures in `rustproofing/`. This includes equipment, kit variants and accessories. It is not 103 different pump models, and does not establish a complete replacement-parts inventory.

Sources:

- Category: https://lemmer.com/en/product-category-2/rustproofing/
- Public API: https://lemmer.com/en/wp-json/wc/store/v1/products?category=126&per_page=100
- Second page: https://lemmer.com/en/wp-json/wc/store/v1/products?category=126&per_page=100&page=2

## Initial manual checks

RP-460HD sales item L015-201:

- Product: https://lemmer.com/en/product-2/rp-460hd-professional-air-rust-remover-125-psi/
- Parts sheet: https://lemmer.com/wp-content/uploads/2026/01/Parts-Book-Complete-43-1.pdf
- Manual: https://lemmer.com/wp-content/uploads/2026/01/Manual-RP-460HD.pdf

Selected identifiers verified against the parts sheet, not a complete transcription:

| Part | Name |
| --- | --- |
| L015-288 | Packing spring |
| L015-289 | Packing washer |
| L015-291 | Packing |
| L015-292 | Packing nut |
| L015-258 | Needle |
| L015-259 | Needle spring |
| L015-295 | Seal kit |
| L015-296 | Overhaul kit |

The sheet identifies RP-460HD kit and pressure-feed variants. Version-specific applicability must be retained; part names alone do not authorize ordering. The sheet shows a September 2018 update and the manual a March 2019 date. The 2026 upload path is not the document revision.

RP-1202 kit L033-207:

- Product: https://lemmer.com/en/product-2/air-atomized-rustproofing-kit-for-20-liters-5g-pneumatic-pump-rp-1202-gun-rp-460-and-25-hose/
- Linked diagram: https://lemmer.com/wp-content/uploads/2026/01/Parts-Book-Complete-43.pdf
- Linked manual: https://lemmer.com/wp-content/uploads/2026/01/Manual-RP-1202-L033-207814-L500-006.pdf

The product page's pump-diagram and gun-diagram buttons resolve to the same RP-460HD gun sheet. Do not treat it as the RP-1202 pump bill of materials. Record this as a coverage gap and obtain the correct pump diagram.

## Remaining coverage work

- Review product-page manual buttons for the remaining catalogue entries; the public API descriptions do not contain these PDF links.
- Verify each PDF's printed model, revision and variant before extracting parts.
- Distinguish a complete kit sales number from the replacement parts inside it.
- Review translation/unit inconsistencies rather than silently repairing specifications.
- Keep old product manuals for existing assets, but remove old products from the new sales-catalogue presentation during the application migration.
- Use the project owner's actual repair data and experience notes for troubleshooting; marketing descriptions do not establish problem/solution evidence.

## Implementation update · 26 September 2026

The 103 catalogue captures are now active for matching product facts. Twenty-six distinct official PDFs were collected; three product pages failed retrieval (L090-089, L090-210, L090-211). Their catalogue records remain available. Raw PDF extraction is research material, not automatically trusted agent instructions.

The correct RP-1202 pump diagram was subsequently obtained at https://lemmer.com/wp-content/uploads/2026/01/part-diagram-RP-1202.pdf and visually checked. Reviewed component references for RP-1115, RP-1202, F-1001 and LX-17 are in `knowledge/components/lemmer/`, in addition to selected RP-460HD parts. Printed revisions and variant limits are preserved. These replace the earlier coverage-gap status for those diagrams, but do not establish complete compatibility or troubleshooting coverage for every catalogue entry.
