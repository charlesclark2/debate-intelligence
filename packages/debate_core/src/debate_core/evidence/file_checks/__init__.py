"""Quality checks on a built evidence file, read back from its own bytes (`v1-e33-t04`).

`v1-e33-t02`'s writer builds a `.docx` and its provenance sidecar. These checks read that file again,
as somebody about to quote from it would, and say whether it is what the sidecar claims:

* :mod:`.identity`: each card's evidence text, cite and formatting are the source card's;
* :mod:`.structure`: cites, duplicate cards, headings, the sidecar against the document, each card's
  provenance and the suppression list;
* :mod:`.placeholders`: no analytic is still the CP text slot `files suggest` drafts (a WARN, `v1-e33-t15`);
* :mod:`.report`: what the checks found, as `<file>.quality.json` and `<file>.quality.md`.

Every check here is a function of parsed values. Reading the bytes, fetching the sources and writing
the reports is :class:`~debate_core.application.file_quality_service.FileQualityService`'s job.
"""
