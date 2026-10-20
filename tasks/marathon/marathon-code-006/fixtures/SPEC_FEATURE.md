# Spec: markdown table of contents

`generate_toc(markdown)` returns nested markdown bullets linking to heading anchors. Indentation is relative to the shallowest heading level in the document (two spaces per extra level). Headings inside fenced code blocks are ignored. Slugs: lowercase, strip punctuation other than hyphens, spaces become hyphens (GitHub style, e.g. "What's New: v2.0!" becomes whats-new-v20).
