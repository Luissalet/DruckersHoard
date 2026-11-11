# Drucker's Hoard

The professional engagement office of the Hoard family (Spanish UI name: «Oficina de encargos»). It keeps one file per engagement and helps with the five jobs around it: scope changes, proposals, deliverable review and delivery packages.

It is not a CRM. Contacts stay in People, money movements in Ledger and files in Atlas. This app stores references to them (`{app, id}`, a path or a URL), never copies. A payment entered here without a Ledger reference is marked `manual`.

## Run

Python 3.11 or later.

```
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows; use .venv/bin/python elsewhere
python -m drucker                                    # http://127.0.0.1:5246/
python -m pytest -q
```

`--port` changes the port. `DRUCKER_DATA` (or `--data-dir`) selects the data folder; default is `data/` in the repository, ignored by Git. The folder holds `drucker.db` (SQLite), `mcp-token` and `packages/`.

## What it does

| Page | Job |
| --- | --- |
| Engagements | List and file per engagement. Tabs: Scope, Milestones, Materials, Decisions, Real hours, Deliverables, Payments, Change orders, References, History. Every change is written to the history with old and new values. |
| Compare scope | Initial request vs agreement vs new request (text or items). Each item is added, removed, ambiguous, already included or unchanged. Effort is an hours range with its reason; three options: include, change order with a range, defer; each option can be chosen and is logged as a decision. Bands can be proposed from real hours and synonyms edited. |
| Proposal | Draft in Markdown, HTML or DOCX, with an optional template by engagement type. Every sentence is tagged verified (with its source fact), assumption or question. Export is refused while the text contains a deny-listed internal name. |
| Review | Deliverable versions (file reference and SHA-256), comments anchored to a version and optionally to a page, region, time range or object. Status open / fixed in version N / won't fix. One version is marked to deliver. Feedback on an older version is shown as stale. |
| Package | Verifies a version's delivery package (files exist, hashes match, exports open, data sources authorised, instructions and limitations present), then writes `manifest.json` and `package.zip`. Not ready if any check fails. |

UI text is in Spanish (Spain) and English (switch in the header; the choice is remembered).

## Real hours, live references, decisions

- **Bands from real hours.** Each closed engagement can record `effort` items (kind of work, measure, hours, units). `GET /api/bands/suggest` / `drucker_bands_suggest` turns them into a proposed range per band part (10th to 90th percentile with three or more samples, observed minimum to maximum with fewer) and reports mean, standard deviation, min, max and a word: `ok`, `scattered` (standard deviation above 60 % of the mean) or `insufficient`. Nothing is applied by itself; "Apply the reliable proposals" in Compare scope saves them through `drucker_settings`.
- **Live references.** `GET /api/engagements/{id}/refs` / `drucker_refs_resolve` ask People (`get_person`), Ledger (`list_entries` / `search_entries` around the payment date) and Atlas (`atlas_file_resolve`) through the family hub for the current name, amount and file path, and whether it still matches what was stored. Read only: nothing is copied or saved. If the hub or the other app is not running each reference says `unavailable` and stays as it was.
- **Atlas pointers in packages.** An export or editable file may be `atlas:<id>` (or `{atlas, path}`): the package asks Atlas for the current path and SHA-256, checks the bytes against that revision, and uses the recorded path only as a fallback when Atlas is down.
- **More formats.** DOCX, XLSX, SVG and MP4/M4V are validated structurally (OOXML parts and relationships, sheets, viewBox and shapes, moov / media tracks / mdat). PDF checks the xref table, trailer, page tree and EOF; GLB checks chunks, accessors and buffer ranges and, when Vulcan is running, adds its Khronos validator (`gltf_validate`) result: errors fail the package, warnings do not.
- **Templates and DOCX.** An engagement has a type (`general`, `report`, `data`, `design`, `training`). The proposal adds the standing method, terms and questions of that type, always tagged `assumption` or `question`, never `verified`; `general` adds nothing. `format: docx` writes `proposal.docx` / `propuesta.docx` (deterministic bytes) under `data/proposals/<id>/`; the same deny-list refusal applies.
- **Synonyms.** Groups such as `informe = reporte` can be shared (`drucker_settings` with `synonyms`) or per engagement (`drucker_synonyms`, `PUT /api/engagements/{id}/synonyms`). Matches made through a synonym are marked `via_synonyms`.
- **Decisions and change orders.** `drucker_scope_decide` / `POST /api/engagements/{id}/decide` records the option chosen for a request (`include`, `change_order` with hours, `defer`, `specify`) in the decision log with its hours and money range, and adds an agreed scope item marked as a change for include and change order. `drucker_change_orders` / `GET /api/engagements/{id}/change-orders` (`.md` for Markdown) lists the change orders in force, with totals and the budget; if a request was decided twice only the latest counts.

## Scope comparison, in short

Matching is deterministic: accent-folded tokens with light stemming, Jaccard overlap and difflib sequence ratio. When a match is uncertain the item is `ambiguous`, never forced. A changed number ("5" to "8 templates") or a flipped negation ("with" to "without annexes") is ambiguous on purpose.

Effort comes from editable rule bands and from which deliverables and milestones an item touches:

- `format`: output format of existing deliverables. Last stage only. Default 1-4 h per deliverable.
- `pipeline`: changes how the work is produced. Earlier stage, so everything after it is redone. Default 16-40 h plus 4-10 h for each extra deliverable or open milestone.
- `quantity`: more of the same, per extra unit.
- `content`: only an ambiguous overlap with an agreed item that asks for more (default 4-12 h, min forced to 0).
- `given`: the hours you supply on the item (`{text, hours}` with a number, `[min,max]` or `{min,max}`) are used as given.

New work with no counterpart in the agreement ("a mobile app for sales reps") gets no hours at all: it is `added`, effort `unestimated` (needs specification), listed separately and left out of the totals, which show "+ N items without estimate". Options: `specify` (specify and estimate separately) or `defer`. A default band would grossly understate a whole new product.

### Language

Every text the server writes for people (reasons, options, notes, review warnings, package checks, history lines, errors) is rendered in `lang` (`es` Spanish of Spain, `en`). Tools and the proposal route take `lang`; the UI sends its current language in an `X-Lang` header on every call. Without either, the answer is English (proposals default to Spanish). Machine fields (`class`, `effort.kind`, option codes, check ids, numbers) never change with the language. The history keeps a message key, so old lines can be read in either language. Text that comes from the user's own data, and the validation wording of the underlying schema library outside the common cases, is not translated.

The result is always a range plus the reason. Money appears only if you give an hourly-rate range. The bands are a starting point to calibrate, not a quote.

Saved bands: Compare scope > Effort bands edits every [min, max] pair and saves it for all engagements (`GET`/`PUT /api/settings` with `bands`, MCP `drucker_settings`). Only the parts you change are stored; "Back to defaults" (`bands: {}`) clears them. A call's own `bands` still override the saved ones part by part, and every comparison returns the `bands` it used.

## Surfaces

- REST: `/api/...` (OpenAPI at `/docs`). Writes from another origin are refused.
- MCP (stdio): `python -m drucker.mcp_server`. Twenty-four tools prefixed `drucker_`: `drucker_engagements`, `drucker_engagement_get`, `drucker_engagement_save`, `drucker_item_save`, `drucker_item_delete`, `drucker_history`, `drucker_scope_compare`, `drucker_proposal`, `drucker_review`, `drucker_deliverable_save`, `drucker_version_add`, `drucker_comment_add`, `drucker_comment_status`, `drucker_deliver_select`, `drucker_package_verify`, `drucker_package`, `drucker_settings`, `drucker_example`, `drucker_bands_suggest`, `drucker_refs_resolve`, `drucker_synonyms`, `drucker_proposal_templates`, `drucker_scope_decide`, `drucker_change_orders`. Read-only tools declare `readOnlyHint`; `drucker_item_delete` declares `destructiveHint`; `drucker_proposal` writes a file for `docx` and is not read-only. The bridge lists tools without the app running. Calls go to the running app on 127.0.0.1 with the token in `data/mcp-token` (`POST /api/agent/call`, bearer token).
- Copilot: the common family panel and launcher, mounted at `/api/copilot/*`. The page exposes what is on screen through `window.hoardCopilot`.

## Data

SQLite tables: `engagements`, `items` (scope, milestone, material, decision, payment, assumption, question, effort), `history`, `deliverables`, `versions`, `comments`, `packages`, `settings`. Example data is invented and marked as such («Cooperativa Ejemplo S. L. (ficticia)»); load it from the Engagements page.

## Tests

`python -m pytest -q`: 137 tests covering real-hours calibration, live references with the other apps replaced by a fake hub, Atlas pointers, DOCX/XLSX/SVG/MP4/PDF/GLB validation, templates and DOCX, synonyms, decisions and the change-order report, plus engagement CRUD and history, scope classes and ranges, saved effort bands, proposal tagging and the deny-list, stale-feedback detection, package verification (missing file, bad hash, broken PNG/PDF/GLB/STL/JSON/CSV/ZIP, unauthorised source), deterministic zip bytes, REST, the token-protected agent route and the stdio bridge against a live server.

## Limits

- Hours are rule-based ranges. No model is used, so wording the rules do not know is either `ambiguous` or, when nothing in the agreement resembles it, an item without estimate.
- Package checks prove a file opens and matches its hash, not that it is good. Remote URLs cannot be verified, so a package that lists them is not ready until a local path is given. Atlas pointers are verified only while Atlas answers (otherwise the recorded path is used and the check says so).
- Format checks are structure checks (zip, JSON, CSV, PDF, PNG, GLB, STL, DOCX, XLSX, SVG, MP4), not full parsers; the Khronos validation of a GLB needs Vulcan running.
- Live references need the family hub and the owner app running; the Ledger entry is found by date window or title because Ledger has no read-by-id tool.
- No authentication on the UI (local 127.0.0.1 app, like the rest of the family).

## Skills for the agents that connect

This app carries procedures from the skill library of the family's workspace for the agents that connect to it: `engagement-proposal-and-delivery`, `writing-plans`, `pretask-interview`, `docs-release-review`. They are named in what an agent reads on connecting, read with `skills_list` and `skill_read`, searched and assigned with `skills_library` and `skills_assign`, and offered as prompts. The person chooses them on the skills page (`/api/agent/skills/page`) or in the hub's Skills tab; the `skills` block of `faustus-plugin.json` holds what the app asks for by default.
