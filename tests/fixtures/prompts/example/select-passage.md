---
prompt_id: example.select-passage
version: 1.0.0
status: released
task_class: high_volume
output_schema: debate_core.testing.contracts.model_router.ContractPassage
owner: v1-e05-model-router
changelog:
  - version: 1.0.0
    date: 2026-10-17
    summary: The worked example of the prompt file format. Only tests load it.
---
<!-- system -->
You choose one passage from a numbered list of paragraphs.
Answer with the paragraph's number and the character offsets where the passage starts and ends.
Never copy any of the paragraph's words into your answer.
<!-- user -->
Choose the passage that best supports this tag: {{ tag }}
