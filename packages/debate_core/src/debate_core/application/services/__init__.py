"""Application services: the use cases the CLI, API and workers call.

Each service takes the ports it needs as constructor arguments and holds no other state. The
services the platform actually runs — SearchService, ArticleService, CardService and the rest of
the table in architecture proposal §6 — arrive with their own epics;
:mod:`debate_core.application.services.article_registration` is here now as the worked example of
the pattern they all follow.
"""

from debate_core.application.services.article_registration import ArticleRegistrationService

__all__ = ["ArticleRegistrationService"]
