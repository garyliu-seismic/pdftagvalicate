# pdftagvalicate — improvement plan

From the 2026-09-22 code review (5 parallel review passes + comparison against
[speedata/pdfa11y](https://github.com/speedata/pdfa11y)). 13 confirmed findings,
prioritized below. Check items off as they're done.

## P0 — correctness bugs (fix before this touches anything real)

- [x] **Direct (non-indirect) Link annotations silently skipped.**
      `link_nesting_repair.py:64` — `objgen == (0, 0)` is used to mean both
      "not an indirect object" and "already tagged," so a Link annotation
      stored as a bare dict in `/Annots` is treated as already-handled and
      never gets a `<Link>` struct element.
      Fix: `pdf.make_indirect(annot)` first if not already indirect, then
      proceed with tagging; don't treat non-indirect as "skip."

- [x] **`/MarkInfo /Marked = true` set with no struct tree behind it.**
      `metadata_repairs.py:25` (`fix_mark_info`) — unconditionally sets
      `Marked=true` even on a fully untagged, structure-less PDF. Worse than
      doing nothing: the file now falsely claims to be tagged.
      Fix: only set `Marked=true` if a `/StructTreeRoot` exists (or is being
      created in the same run by another selected repair) — otherwise skip
      with a clear report message.

- [x] **Fake-table dissolution leaves dangling ParentTree references.**
      `tbody_repair.py:70` (`_try_fix_fake_table`) — re-parents the cell's
      children but never touches `/ParentTree`/`/StructParent` for the
      discarded TD/TR/TBody/Table elements. If the cell's content is a bare
      MCID, the page's ParentTree entry for that MCID still points at the
      now-detached, unreachable TD/TH object.
      Fix: when discarding a struct element, walk `/ParentTree` for any MCID
      entries pointing at it and repoint them at the new parent (or at
      minimum, detect and report this case instead of silently increasing
      `fixed`).

- [x] **Stale `/ParentTreeNextKey` trusted blindly.**
      `link_nesting_repair.py:138` (`_next_parent_tree_key`) — uses the hint
      as-is without cross-checking the actual max key in `/Nums`, risking
      key collision with an existing entry.
      Fix: `max(hint, actual_max_key_in_nums + 1)`.

- [x] **ParentTree `/Kids` (paginated number tree) not handled.**
      `link_nesting_repair.py:122` (`_ensure_parent_tree` / `_ensure_nums`) —
      only the flat `/Nums` shape is supported. Real multi-page tagged PDFs
      commonly partition ParentTree via `/Kids`. Currently would bolt a
      conflicting `/Nums` onto a dict that already has `/Kids` (spec requires
      `/Kids` XOR `/Nums` on a number-tree node) — silent structural
      corruption.
      Fix: detect `/Kids` and either (a) locate/extend the correct child
      node, or (b) refuse this repair with a clear "unsupported ParentTree
      shape" report rather than corrupting it.

- [x] **Shared/aliased `/A` attribute dict mutated in place.**
      `th_scope_repair.py:93` (`_apply_scope`) — if two TH cells share one
      indirect `/A` object (common producer optimization), fixing the second
      cell overwrites the first cell's just-written `/Scope`.
      Fix: before mutating, check whether the attribute object is referenced
      by more than one struct element (or just always clone per-element
      rather than reusing a found "owner" dict) when scopes differ.

- [x] **`fix_pdf_ua_identifier` not idempotent.**
      `metadata_repairs.py:13` — always writes and always reports `fixed=1`,
      unlike its two sibling metadata repairs, which breaks
      `total_fixed`-based exit-code semantics (dry-run / re-run always shows
      a phantom fix).
      Fix: read the existing `pdfuaid:part` value first; report `fixed=0`
      if already `"1"`.

- [x] **In-place repair (`input.pdf` == `output.pdf`) always fails.**
      `cli.py` `_run()` — opens with `pikepdf.open()` then saves to the same
      path without `allow_overwriting_input=True`; pikepdf raises, surfaced
      as a generic `Error: ...` (exit 2).
      Fix: detect `input == output` and pass
      `allow_overwriting_input=True`, or reject explicitly with a clear
      message (decide which — probably support it, since it's a natural CLI
      usage pattern).

## P1 — robustness gaps (silent no-ops on realistic malformed input)

- [x] **No cycle/visited-set guard in `link_nesting_repair._collect_tagged`
      or the `th_scope_repair` walkers** (tbody's walker has one via
      `_visit_key`). On a cyclic/malformed struct tree — exactly the input
      class this tool targets — these hit `RecursionError`, caught generically
      by `repairs.py` as "0 fixed / unexpected error," with no real repair
      and no actionable diagnosis.

- [x] **Only one exact flat shape is recognized** in both
      `th_scope_repair._walk_table` (direct THead/TBody/TFoot/TR children
      only) and `tbody_repair._try_fix_fake_table` (exactly one
      TBody→one TR→one TD/TH). Nested tables, wrapper elements
      (`Part`/`Div`), and multi-row fake tables all silently no-op with a
      false "nothing to fix" report instead of an error or a
      partially-applied fix.

## P2 — refactor for maintainability (do after P0/P1 land, to avoid rebasing fixes across a refactor)

- [x] **Consolidate the three duplicated struct-tree walkers**
      (`tbody_repair._collect_by_role`, `th_scope_repair._collect_missing_scopes`,
      `link_nesting_repair._collect_tagged`) into one `walk_struct_tree()`
      helper in `pdfutil.py` (with the P1 cycle guard baked in once, not three
      times). Also fixes the inconsistent `get_kids` vs `get_struct_kids` use
      inside `th_scope_repair.py` itself.

- [x] **Consolidate `tbody_repair._visit_key` into `pdfutil.same_object`**
      (or a shared `object_key()`) — currently two independent
      implementations of "PDF object identity" that could silently diverge.

- [x] *(optional, lower priority)* Combine the three full-tree walks
      `--all` currently does into a single pass that dispatches per-node to
      whichever collectors are needed — matters only at large-document scale.

## P3 — port `Seismic.CTS.PdfUaChecker` as `pdftagvalicate --validate`

Source: `content-transformation-service-v2` (`personal/gary/MergeTagTree`,
`src/CTS/Seismic.CTS.PdfUaChecker/`) — a PAC-like, read-only PDF/UA validator
(iText-based) with a `CheckTypes.cs` / `PdfUaChecks.cs` / `Program.cs` /
`Reporters.cs` / `TagTreeDumper.cs` shape. Port as `pdftagvalicate --validate`
(read-only, no PDF written). Report shape: per-check `Severity` enum
(`Pass / Info / Warning / Fail / Error`) plus Matterhorn clause ID, mirroring
the C# original. Borrow `--strict` (warnings count as failures) and WCAG
mapping from [speedata/pdfa11y](https://github.com/speedata/pdfa11y) for
output-format conventions.

### Step 0 — shared helpers (add to `pdfutil.py` before any check lands)

The C# code duplicates several patterns 3–4 times across checks. Build each
helper once here; every check that needs it imports from `pdfutil`.

- [x] **`resolve_role(role, struct_root) -> str`** — transitive, cycle-guarded
      walk of `StructTreeRoot/RoleMap` against the ~40 standard PDF 1.7 roles
      (Document, Part, Art, Sect, Div, BlockQuote, Caption, TOC, TOCI, Index,
      NonStruct, Private, H, H1–H6, P, L, LI, Lbl, LBody, Table, TR, TH, TD,
      THead, TBody, TFoot, Span, Quote, Note, Reference, BibEntry, Code,
      Link, Annot, Ruby, Warichu, Figure, Formula, Form). ~15 lines.
      Shared by: **14-001**, **09-007**.

- [x] **`find_page_index(struct_elem, pdf) -> int | None`** — resolve which
      page a struct element's content lives on: check `/Pg` on the element
      itself, then walk its first MCR/OBJR descendant's `/Pg`, then fall back
      to the page's position in `pdf.pages`. The C# `FindPage()` is duplicated
      4+ times (09-004, 14-002, 14-003, 14-004).
      Shared by: **09-004**, **14-002**, **14-003**, **14-004**.

- [x] **`iter_font_resources(pdf) -> Iterator[Dictionary]`** — walk every
      page's `/Resources/Font` dict (and inherited resources) and yield each
      font dictionary. New domain (no struct tree), but plain dict-walking.
      Used only by: **31-001**.

- [x] **`read_pdfuaid_part(pdf) -> str | None`** — attempt
      `pikepdf.open_metadata()` first (free if it works); fall back to raw
      `lxml` parse of the XMP stream only if the namespace prefix isn't
      exposed by pikepdf's accessor. Verify the easy path before assuming
      `lxml` is required.
      Used only by: **06-001**.

- [x] **`tokenize_content_stream(page, pdf) -> Iterator[tuple[str, list]]`** —
      wrap `pikepdf.parse_content_stream`, recurse into Form XObjects, track
      the BDC/BMC/EMC marked-content stack, and yield `(operator, operands)`
      tuples with an attached `in_marked_content: bool` flag. **Do this last**
      — it is the most involved piece and 09-006 can be left as a documented
      gap if the effort isn't justified.
      Used only by: **09-006**.

### Step 1 — CLI scaffold (`--validate` flag + `CheckResult` type)

- [x] Add `CheckResult(id: str, name: str, severity: Severity, detail: str)`
      dataclass to `types.py`; add `Severity` enum
      (`Pass / Info / Warning / Fail / Error`).
- [x] Add `--validate` flag to `cli.py` (mutually exclusive with repair flags);
      wire to a new `run_checks(pdf, options) -> list[CheckResult]` in a new
      `checks.py` orchestrator (mirrors `repairs.py`).
- [x] Output: human-readable `[PASS] 01-005  MarkInfo /Marked` lines plus
      `--json` schema `{"checks": [{"id", "name", "severity", "detail"}]}`,
      `--strict` makes Warnings count as failures for the exit code.

### Step 2 — trivial checks (start here; 7 checks, ~5 min each)

All read a single catalog/trailer key; no struct-tree walk needed.

- [x] **01-005** `MarkInfo /Marked is true`
      `catalog.get(Name.MarkInfo, {}).get(Name.Marked)` — Fail if absent/false.

- [x] **11-001** `Document /Lang set`
      `catalog.get(Name.Lang)` — Fail if absent or empty string.

- [x] **06-003** `Document Title set`
      `pdf.docinfo.get("/Title")` (trailer DocInfo, not XMP) — Fail if absent
      or empty.

- [x] **07-001** `ViewerPreferences /DisplayDocTitle true`
      `catalog.get(Name.ViewerPreferences, {}).get(Name.DisplayDocTitle)` —
      Fail if absent/false.

- [x] **13-004** `<Figure>/<Formula> alt text`
      Walk the full struct tree (reuse `walk_struct_tree` from `pdfutil`);
      for every node whose resolved role is `Figure` or `Formula`, check that
      at least one of `/Alt`, `/ActualText`, `/E` is present and non-empty.
      Fail per missing element.

- [x] **14-002** `<TBody> contains only <TR> rows`  ★ reuses repair logic
      Read-only mirror of `tbody_repair._try_fix_fake_table`: walk tables,
      report any TBody whose direct struct children include non-TR elements.
      Reuse `tbody_repair._collect_by_role` + `get_struct_kids`; no mutation.

- [x] **14-003** `TH cells have /Scope`  ★ reuses repair logic
      Read-only mirror of `th_scope_repair`: call `_collect_missing_scopes`
      (already imported) and report each TH that lacks `/Scope`. Zero new
      logic — literally wrap the existing finder in a `CheckResult`.

### Step 3 — trivial-to-moderate checks (need one shared helper each)

- [x] **09-001** `Single <Document> at struct tree root`
      Walk `StructTreeRoot/K` (via `get_kids` + `resolve_role`); count nodes
      whose resolved role is `Document`. Fail if count ≠ 1.
      *Needs*: `resolve_role` (Step 0).

- [x] **14-001** `Role map resolves to standard roles`
      For each entry in `StructTreeRoot/RoleMap`, call `resolve_role`; Fail if
      the chain is cyclic or terminates at an unrecognised name.
      *Needs*: `resolve_role` (Step 0).

- [x] **09-007** `First heading is on level 1`
      Document-order walk (reuse `walk_struct_tree`); find the first node
      whose resolved role is `H` or `H1`–`H6`; Fail if it resolves to
      anything other than `H1` (or unlevelled `H` when no H1–H6 are present).
      *Needs*: `resolve_role` (Step 0).

- [x] **14-004** `Table rows are regular`
      Per table, collect TR children of each TBody/THead/TFoot; compare cell
      count of every row against the first non-empty row. Emit Warning (not
      Fail) for irregular rows.
      *Needs*: `find_page_index` (Step 0) for location context in the report.

- [x] **28-001** `Link annotations nested inside <Link>`  ★ reuses repair logic
      Wire together `link_nesting_repair._collect_tagged` (already exists) and
      the page `/Annots` walk. Annotations with `Subtype=Link` whose obj-number
      is *not* in `tagged_obj_nums` → Fail.
      *Needs*: no new helper — reuses both traversals already in
      `link_nesting_repair.py`.

- [x] **31-001** `All fonts embedded`
      For each font dict from `iter_font_resources`: follow
      `/FontDescriptor` (or `/DescendantFonts[0]/FontDescriptor` for
      composite fonts); Fail if none of `FontFile` / `FontFile2` / `FontFile3`
      is present.
      *Needs*: `iter_font_resources` (Step 0).

- [x] **09-004** `No untagged page content`
      Collect the set of page-indices touched by the struct tree (via
      `find_page_index` on every MCR/OBJR leaf); diff against `pdf.pages`
      index range. Fail for any page index absent from the struct-tree set.
      *Needs*: `find_page_index` (Step 0).

### Step 4 — hard checks (do last; may be left as documented gaps)

- [x] **06-001** `PDF/UA identifier in XMP`
      Try `pikepdf.open_metadata()` → `meta["pdfuaid:part"] == "1"` first.
      Only if that fails, fall back to raw `lxml` parse of the XMP stream
      looking for `pdfuaid:part` as element text or RDF attribute in either
      the `http://www.aiim.org/pdfua/ns/id/` namespace or a remapped prefix.
      *Needs*: `read_pdfuaid_part` (Step 0).
      Difficulty: **Hard** if `open_metadata()` doesn't expose the prefix;
      verify the easy path first.

- [x] **09-006** `No untagged real content in page streams`
      Parse each page's content stream with `pikepdf.parse_content_stream`;
      track the BDC/BMC/EMC marked-content stack; recurse into Form XObjects;
      flag any painting operator (`Tj`, `TJ`, `f`, `S`, `Do`, …) executed
      outside any marked-content layer.
      *Needs*: `tokenize_content_stream` (Step 0).
      Difficulty: **Hardest** — consider leaving as a documented gap and
      shipping the other 14 checks first.

### Recommended porting order

```
Step 0 helpers (resolve_role, find_page_index)   ← unblock Steps 2+3
Step 1 scaffold (CheckResult, --validate, checks.py)
Step 2 trivial  (01-005, 11-001, 06-003, 07-001, 13-004, 14-002★, 14-003★)
Step 3 moderate (09-001, 14-001, 09-007, 14-004, 28-001★, 31-001, 09-004)
Step 0 helpers (iter_font_resources, read_pdfuaid_part)   ← needed by 31-001/06-001
Step 4 hard     (06-001, then 09-006 if warranted)
```

Checks marked ★ are read-only mirrors of already-ported repair logic —
almost zero new code, start with those for quick wins.
09-006 is the only check that needs content-stream tokenization; all others
are pure struct-tree / catalog / font-resource dict walking.

---
*Source: code review conducted 2026-09-22 via 5 parallel subagent passes
(correctness, reuse/simplification/efficiency, altitude/conventions,
removed-behavior audit, cross-file tracer) on commit `f4c5a50`, plus a
follow-up read of `Seismic.CTS.PdfUaChecker` (content-transformation-service-v2,
`personal/gary/MergeTagTree`) for the P3 validator port.*

## P4 — Extend toward full PAC equivalence (2026-09-26)

Goal: match PAC 3's full Matterhorn Protocol coverage. Gap analysis against PAC 3
identified ~30 uncovered failure conditions. Organized by tier (effort + value).

### Tier 1 — Implemented (2026-09-26): high value, low effort

- [x] **08-001** `Encryption allows AT access`
      Check `/P` permissions bitfield; bit 0x200 must be set.

- [x] **01-002** `All struct tags standard or role-mapped`
      Walk struct tree; any `/S` value that is neither a standard PDF 1.7 role
      nor a key in `RoleMap` → Fail. (Distinct from 14-001 which validates the
      *destination* of mappings.)

- [x] **06-004** `XMP dc:title matches DocInfo /Title`
      Compare `meta["dc:title"]` vs `pdf.docinfo["/Title"]`; mismatch → Warning.

- [x] **11-002** `/Lang values are valid BCP-47 tags`
      Validate every `/Lang` value (catalog, pages, struct elements) against
      BCP-47 regex.

- [x] **09-008** `Heading levels not skipped`
      Track H1-H6 sequence in document order; skip of more than 1 level → Fail.

- [x] **15-001** `List structure valid (L > LI > LBody)`
      Every `<LI>` child of `<L>`; every `<LI>` has `<LBody>`; `<Lbl>`/`<LBody>`
      only inside `<LI>`.

- [x] **15-002** `<L> contains only <LI> or <Caption>`
      Direct struct children of `<L>` must be `LI` or `Caption`.

- [x] **17-001** `Widget annotations nested inside <Form>`
      Mirror of 28-001 for Widget annotations → `<Form>` struct elements.

- [x] **17-002** `Form fields have tooltip (/TU)`
      Walk `AcroForm/Fields` recursively; every terminal field (has `/FT`) must
      have a non-empty `/TU`.

- [x] **22-001** `Document outline present (>21 pages)`
      `/Outlines` with at least one entry required for documents > 21 pages.

- [x] **24-001** `Annotations have /Contents`
      Non-Link, non-Widget, non-exempt annotations must have non-empty `/Contents`.

- [x] **24-002** `No prohibited annotation types (TrapNet, Movie)`
      `TrapNet` and `Movie` subtypes are prohibited by PDF/UA-1.

- [x] **28-002** `<Link> annotation has /Contents`
      Every Link annotation inside a `<Link>` struct OBJR must have `/Contents`.

### Tier 2 — Planned: medium effort

- [ ] **22-002** `Outline entries have valid titles and destinations`
      Walk `/Outlines` linked list; verify each item has a non-empty `/Title`
      and that any `/Dest` references a real page.

- [ ] **14-005** `Table /Headers IDs resolve within the same table`
      When TH/TD uses the `/Headers` array model, each referenced ID must
      exist on another cell in the same table.

- [ ] **14-006** `Table has Caption or /Summary`
      Each `<Table>` should have a `<Caption>` child or a `/Summary` attribute.

- [ ] **09-002 / 09-003** `Structure element parent-child containment rules`
      Validate that elements only appear under permitted parent roles per
      ISO 32000-1 §14.8.4 (e.g., TD under TR, TR under THead/TBody/Table, …).

### Tier 3 — Stretch: requires font/CMap parsing

- [ ] **10-001** `Character codes mappable to Unicode`
      For each font: verify ToUnicode CMap or standard Encoding covers the
      glyphs in use. Consider optional `fonttools` dependency.

- [ ] **31-002** `All used glyphs have Unicode mappings`
      Cross-reference content-stream glyph codes against the font's CMap;
      flag codes with no Unicode mapping that are not covered by `/ActualText`.

- [ ] **01-003** `No duplicate MCR (MCID on a page) in struct tree`
      Collect (pg_objgen, mcid) tuples from all MCR leaves; fail on duplicates.

- [ ] **10-002** `PUA characters covered by /ActualText`
      Fonts whose ToUnicode maps codes to Private Use Area codepoints must have
      `/ActualText` on the enclosing struct element.

### PAC checks explicitly out of scope (not statically checkable)

- 13-002: Decorative content incorrectly tagged as Figure (semantic judgment)
- 26-001: Flickering content
- 27-001: Flashing content
- 29-001: Keyboard traps via JavaScript
