# The native profile

How finished agent products get on the native board (docs/plan/15 §1).
Native profile v1 is vendor-driven: the bench org does not build product
drivers. If a vendor will not implement the protocol, their product is not
on the native board, and the board is honest about the absence.

## Path A: the vendor implements the protocol (preferred)

The vendor runs the harness protocol (docs/plan/01 §5) against their own
agent infrastructure: `POST /run`, `GET /run/{id}/status`,
`GET /run/{id}/transcript`, `POST /run/{id}/deliver`. The bench org replays
the deterministic checks from the transcript; the vendor's harness is their
product, the transcript format is the contract.

Requirements:

- Transcripts use the standard JSONL event schema (docs/plan/09 §1),
  including per-step tool calls.
- The vendor discloses the method: which product surface, and what tools
  the agent had.
- External-mode submissions are graded by the server with the standard
  checks. Vendor-reported scores are ignored.

The reference implementation of the server side is `longrun.server`
(slice 3), including the external mode this path depends on.

## Path B: bench drives the public interface (fallback)

A community volunteer runs a scripted session: the task prompt is pasted
into the product's chat UI via automation, the session is recorded
(screenshots plus exported transcript), and the transcript is reconstructed
by hand into the JSONL schema, marked `method: ui_driven`, with the
reconstruction notes public.

- Path B scores are labeled `native (ui-driven)` and never mixed with
  Path A rows.
- Path B is labor-intensive and does not scale. It exists so the board is
  not empty while vendors decide: two Path B scores maximum per product,
  then the vendor implements Path A or the product stays off the board.
