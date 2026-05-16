# Synthesizer Prompt

You are tasked with producing a coherent synthesis across multiple
documents on a given topic.

## Inputs

- **Topic:** {{TOPIC}}
- **Sources (markdown, each prefixed with its index_id):**

{{SOURCES}}

## Task

Produce a unified prose synthesis that:
- Identifies the through-line(s) across sources.
- Notes contradictions or tensions explicitly.
- Cites sources by their index_id in inline brackets, e.g., [idx-s1].
- Stays grounded — do not introduce claims not present in the sources.
- Length: 2-6 paragraphs.

Output the synthesis text only — no JSON wrapper, no headers, no commentary.
