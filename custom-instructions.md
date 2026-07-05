<!--
Optional user-provided guidance appended to the model prompt on every run.

When this file has any real content outside of HTML comments, the whole
file (raw, without stripping comments) is injected into the prompt as a
"Custom instructions (user-provided)" section - AFTER the built-in Per-
field rules. The built-in rules always win; use this file to add
preferences and nuances, not to override the guardrails (no fabrication,
verbatim enums, no frontmatter, plain hyphens, etc.).

If this file contains only HTML comments and blank lines (like the
default state), the injection is skipped and the prompt runs unchanged.

Good things to put here (delete this comment and add your own):
  - Naming preferences: "Prefer 'Microsoft Entra ID' over 'Azure AD'."
  - Audience nudges: "Content on https://lab.example.com/* is beginner
    tutorial - always include 'Student' in Target Audience."
  - Voice: "Direct, practical, no filler adjectives. Never start
    Description with 'This blog post explores'."
  - Exclusions: "Skip mentioning employer-specific product names in the
    Description or Private Description."
  - Rules that apply to specific sources or Activity Types.

Bad things to put here (these will fight the guardrails and produce
broken output):
  - "Fill Additional Technology Areas with 'Microsoft 365' by default."
  - "Add a YAML frontmatter block with source_url and detected_on."
  - "Make up a Number of Views based on the topic popularity."
-->
