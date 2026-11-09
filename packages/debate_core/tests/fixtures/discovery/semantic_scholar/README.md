# Semantic Scholar fixtures

Recordings for `SemanticScholarProvider`
(`packages/debate_core/src/debate_core/integrations/discovery/semantic_scholar.py`), used by
`packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py` and its binding of the
shared search provider contract kit.

Nothing here was captured from the live API. Every body was written by hand from Semantic
Scholar's public Academic Graph API documentation (the OpenAPI description behind
api.semanticscholar.org/api-docs/graph, read 2026-11-09): `GET /graph/v1/paper/search` answers
`total`, `offset`, `next` (absent on the last batch) and `data`, a list of papers carrying the
`fields=` asked for, and `paperId` always. So the papers, venues, people and identifiers are
invented. DOIs use Crossref's `10.5555` test prefix, except the arXiv DOI, which has arXiv's
`10.48550` prefix as such DOIs do. No file holds an API key: the adapter sends a key as the
`x-api-key` header, never in a URL, so the recorded URLs are the same with a key and without one.

* `paper_search.json` records a `carbon capture subsidies` search between 2020-01-01 and
  2024-12-31 for six results (`publicationDateOrYear=2020-01-01:2024-12-31`, `limit=6`). Its body,
  `paper_search.body.json`, is a page whose papers have open-access PDFs, four in all:
  * a `JournalArticle` with a full `publicationDate` (2022-05-17) and every identifier a paper can
    carry that the adapter reads or ignores: an upper-case `DOI`, `PubMed`, `PubMedCentral`, `MAG`
    and `CorpusId`; one author's name with runs of spaces, an abstract with a line break and a run
    of spaces, and a Creative Commons PDF;
  * a `Conference` preprint with an `ArXiv` id and arXiv's DOI for it, a `DBLP` id, an empty
    `venue`, no abstract and an arXiv PDF;
  * a paper with **no DOI** (`ArXiv` and `CorpusId` only), a `publicationDate` of `null` and a
    `year` of 2021 (a **year-only date**), no `publicationTypes`, one author with no `authorId`
    and one with an empty name;
  * an `Editorial` whose `title` is `null`.
* `paper_search.expected.json` is what that body must map to, written by hand: the paper id as the
  record id and as `identifiers.semantic_scholar_id`; bare lower-case DOIs; the PubMed and arXiv ids;
  the DOI resolver URL, or Semantic Scholar's paper page when there is no DOI; the first two dated to
  the day, the third at 2021-01-01 with `date_precision` `year`; names and the abstract with their
  whitespace collapsed and the empty name dropped; an empty venue as none; every one `scholarly`
  (a paper Semantic Scholar gives no type is still a paper); the PDF's URL as the open copy; the
  citation count. The fourth paper has no title and is not a candidate.
* `paper_search_without_pdfs.json` records a `direct air-capture costs` search since 2019-01-01 for
  three results. The hyphen is sent as a space (`query=direct+air+capture+costs`), as the
  documentation asks, and the window is open-ended (`publicationDateOrYear=2019-01-01:`). Its body,
  `paper_search_without_pdfs.body.json`, is a page with no open-access PDF:
  * a `Review` and `JournalArticle` with a `DOI` and a `PubMed` id, `isOpenAccess` false and
    `openAccessPdf` `null`;
  * a `Dataset` that is open access (`isOpenAccess` true) but whose `openAccessPdf.url` is an empty
    string, as Semantic Scholar sends when it knows of no PDF, with a disclaimer;
  * a `News` item with only a `CorpusId`, a year-only date (2020), and `citationCount` `null`.
* `paper_search_without_pdfs.expected.json` maps them, by hand: no open copy for any of them; open
  access false, true and false as stated; `scholarly`, `other` and `news`; the third at the Semantic
  Scholar paper page with an unknown citation count.
* `paper_search_empty.json` is a search with no results (`total` 0 and an empty `data`).
* `paper_search_rate_limited.json` is a `429` with `Retry-After: 30` for the carbon capture search.
  It must be `ProviderRateLimited` for 30 seconds, and the key must appear nowhere it is reported.
* `paper_search_errors.expected.json` and `paper_search_empty.expected.json` are the empty lists the
  failure and the empty search expect.
