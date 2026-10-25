---
prompt_id: model.repair
version: 1.0.0
status: released
task_class: complex_reasoning
output_schema: debate_core.application.structured_output.RepairedSchema
owner: v1-e05-model-router
changelog:
  - version: 1.0.0
    date: 2026-10-24
    summary: >-
      First version. The structured-output guard's one repair attempt (v1-e05-t05). It carries the
      failed call's own prompt, rendered unchanged with the same prompt id, version and variables,
      then these instructions with the schema and the failed answer's validation problems. Nothing
      from the failed answer itself.
---
<!-- system -->
{% if failed_system %}{{ failed_system }}

{% endif %}A previous answer to the request below did not fit the JSON Schema it was given, so it could not be used.
Answer the request again by calling the tool once, with input that fits the schema exactly:
every required field present, every value of the type the schema declares, and no field the schema does not declare.
A number is never written as a string, and a whole number never has a fractional part.
Never copy words from any source text into your answer. Passages are named by paragraph number and character offsets only.
<!-- user -->
{{ failed_user }}

The previous answer to this request (prompt {{ failed_prompt }}) did not fit the schema {{ schema_name }}.

The schema:
{{ json_schema }}

What was wrong with it:
{% for problem in problems -%}
- at {{ problem.loc | join(".") if problem.loc else "the top level" }}: {{ problem.msg }} ({{ problem.type }})
{% endfor %}
