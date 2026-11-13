"""Backfile seasons on the pilot, one index per season (`v1-e39-t18`, ac2; the PM's shape 4).

Through the real app and the real holders. The world offers two invented seasons, `hsxx25` and
`hsyy24`, each its own index at its own pointer, beside the search pages' usual corpus at
`current.json` (`conftest.season_corpus`). Expected values are written by hand from that corpus:
only season A's featured card (doc 9001) holds `obsidian`; every season card holds `pumice` and no
current card does. Season A's featured card has two occurrences, 0 (Maple Grove QX, its
representative) and 1 (Riverbend ZT); an occurrence's source digest is `f"{doc:032x}{ordinal:032x}"`
and its disclosure digest `f"{ordinal:032x}{doc:032x}"`.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Final

import pytest

from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.season_indexes import season_pointer_key
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY
from debate_core.integrations.s3 import S3SearchIndexSource

SEASON_A: Final = "hsxx25"
SEASON_B: Final = "hsyy24"
SEASON_A_CARD: Final = 9001
SEASON_B_CARD: Final = 9101
JUST_UNDER: Final = timedelta(minutes=5) - timedelta(seconds=1)
SEASON_A_LINE: Final = (
    "[Disclosed: hsxx25 2026-09-15 — Maple Grove QX, Neg vs. Invented Invitational Round 4]"
)
"""Season A's featured card's representative's provenance line, as every disclosed card's is written."""


@pytest.fixture
def world(season_world: Any) -> Any:
    season_world.signed_in_student()
    return season_world


def result_paths(page: str) -> list[str]:
    return re.findall(r'<h3 class="result-tag"><a href="([^"?]+)[^"]*">', page)


def season_reads(world: Any) -> list[str]:
    return [key for key in world.index_source.reads if key.startswith("reports/tub/search/seasons/")]


def suppress_representative(world: Any) -> None:
    world.index_source.append_suppression(
        SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=f"{SEASON_A_CARD:032x}{0:032x}",
            disclosure=f"{0:032x}{SEASON_A_CARD:032x}",
            recorded_at=world.clock(),
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id="RM-2026-18",
        )
    )


# ------------------------------------------------------------------------------------------------
# A backfile card is found, with its season and its provenance line
# ------------------------------------------------------------------------------------------------


def test_a_backfile_card_is_found_in_its_seasons_search_with_its_season_and_provenance_line(
    world: Any,
) -> None:
    page = world.browser.get(f"/search?q=obsidian&season={SEASON_A}")

    assert page.status_code == 200
    assert result_paths(page.text) == [world.season_card_path(SEASON_A, SEASON_A_CARD)]
    assert "Searching hsxx25 (2025-26)." in page.text
    assert SEASON_A_LINE in page.text


def test_a_backfile_cards_page_names_its_season_above_its_provenance_line(world: Any) -> None:
    page = world.browser.get(world.season_card_path(SEASON_A, SEASON_A_CARD))

    assert page.status_code == 200
    season_at = page.text.index("Earlier season: hsxx25 (2025-26)")
    assert season_at < page.text.index(f'<p class="provenance">{SEASON_A_LINE}</p>')
    assert "Riverbend ZT" in page.text


def test_a_backfile_cards_copy_is_read_from_its_seasons_index(world: Any) -> None:
    copied = world.browser.get(world.season_card_path(SEASON_A, SEASON_A_CARD) + "/copy")

    assert copied.status_code == 200
    assert "Pumice and obsidian prices rose" in copied.json()["text"]


def test_the_way_back_from_a_season_card_keeps_the_season(world: Any) -> None:
    page = world.browser.get(f"/search?q=obsidian&season={SEASON_A}").text
    card_link = re.search(r'<h3 class="result-tag"><a href="([^"]+)">', page)
    assert card_link is not None

    card = world.browser.get(card_link.group(1).replace("&amp;", "&")).text

    assert f'href="/search?q=obsidian&amp;season={SEASON_A}"' in card


# ------------------------------------------------------------------------------------------------
# Removal reaches a backfile card within five minutes (gate item 1)
# ------------------------------------------------------------------------------------------------


def test_a_removed_backfile_card_is_gone_from_its_season_within_five_minutes(world: Any) -> None:
    path = world.season_card_path(SEASON_A, SEASON_A_CARD)
    assert result_paths(world.browser.get(f"/search?q=obsidian&season={SEASON_A}").text) == [path]
    suppress_representative(world)

    world.clock.advance(JUST_UNDER)
    still = result_paths(world.browser.get(f"/search?q=obsidian&season={SEASON_A}").text)
    world.clock.advance(timedelta(seconds=1))
    gone = result_paths(world.browser.get(f"/search?q=obsidian&season={SEASON_A}").text)

    assert still == [path]
    assert gone == []
    assert world.browser.get(path).status_code == 404
    assert world.browser.get(path + "/copy").status_code == 404


def test_a_season_first_loaded_after_a_removal_hides_the_card_at_once(world: Any) -> None:
    suppress_representative(world)

    page = world.browser.get(f"/search?q=obsidian&season={SEASON_A}")

    assert page.status_code == 200
    assert result_paths(page.text) == []
    assert world.browser.get(world.season_card_path(SEASON_A, SEASON_A_CARD)).status_code == 404


# ------------------------------------------------------------------------------------------------
# The shape: default search untouched, one season held at a time
# ------------------------------------------------------------------------------------------------


def test_a_default_search_never_reads_a_season_pointer_or_finds_a_season_card(world: Any) -> None:
    page = world.browser.get("/search?q=pumice")

    assert page.status_code == 200
    assert result_paths(page.text) == []
    assert season_reads(world) == []
    assert world.season_holders == []
    assert world.season_files() == []


def test_a_season_search_never_reads_the_current_index(world: Any) -> None:
    page = world.browser.get(f"/search?q=pumice&season={SEASON_B}")

    assert result_paths(page.text) == [world.season_card_path(SEASON_B, SEASON_B_CARD)]
    assert SEARCH_INDEX_POINTER_KEY not in world.index_source.reads
    assert world.services.search_index.loaded_index_id is None
    assert season_reads(world)[0] == season_pointer_key(SEASON_B)


def test_one_season_is_held_at_a_time(world: Any) -> None:
    world.browser.get(f"/search?q=pumice&season={SEASON_A}")
    held_a = world.season_files()
    world.browser.get(f"/search?q=pumice&season={SEASON_B}")
    held_b = world.season_files()
    world.browser.get(world.season_card_path(SEASON_A, SEASON_A_CARD))
    held_again = world.season_files()

    index_a = world.season_indexes[SEASON_A].manifest.index_id
    index_b = world.season_indexes[SEASON_B].manifest.index_id
    assert [name[:16] for name in held_a] == [index_a]
    assert [name[:16] for name in held_b] == [index_b]
    assert [name[:16] for name in held_again] == [index_a]


def test_the_current_index_stays_loaded_while_seasons_come_and_go(world: Any) -> None:
    world.browser.get("/search?q=zephyr")
    current = world.services.search_index.loaded_index_id

    world.browser.get(f"/search?q=pumice&season={SEASON_A}")
    world.browser.get(f"/search?q=pumice&season={SEASON_B}")

    assert current == world.index.manifest.index_id
    assert world.services.search_index.loaded_index_id == current
    assert world.browser.get(world.card_path("featured")).status_code == 200


# ------------------------------------------------------------------------------------------------
# What the student sees: the choice, the season searched, the loading line
# ------------------------------------------------------------------------------------------------


def season_options(page: str) -> dict[str, bool]:
    """Each season option's value, and whether it carries the loading sentence."""
    options = re.findall(r'<option value="(hs[a-z]+[0-9]{2})"([^>]*)>', page)
    return {value: "data-tub-loading" in rest for value, rest in options}


def test_the_search_form_offers_each_season_and_says_loading_until_it_is_loaded(world: Any) -> None:
    before = season_options(world.browser.get("/search").text)
    world.browser.get(f"/search?q=pumice&season={SEASON_A}")
    after = season_options(world.browser.get("/search").text)

    assert before == {SEASON_A: True, SEASON_B: True}
    assert after == {SEASON_A: False, SEASON_B: True}
    assert 'data-tub-loading="Loading hsyy24 (2024-25). The first search' in world.browser.get("/search").text


def test_the_empty_search_page_with_seasons_offered_waits_for_no_index(world: Any) -> None:
    page = world.browser.get("/search")

    assert page.status_code == 200
    assert 'name="season"' in page.text
    assert world.index_source.reads == []


def test_a_season_the_pilot_does_not_offer_is_refused(world: Any) -> None:
    unoffered = world.browser.get("/search?q=pumice&season=hszz23")
    malformed = world.browser.get("/search?q=pumice&season=hsxx")

    assert unoffered.status_code == 400
    assert "That season is not one this search offers." in unoffered.text
    assert malformed.status_code == 400
    assert season_reads(world) == []


def test_a_pilot_offering_no_season_shows_no_season_choice(search_world: Any) -> None:
    search_world.signed_in_student()

    page = search_world.browser.get("/search")
    refused = search_world.browser.get(f"/search?q=pumice&season={SEASON_A}")

    assert 'name="season"' not in page.text
    assert refused.status_code == 400


# ------------------------------------------------------------------------------------------------
# Which seasons are offered: TUB_EARLIER_SEASONS
# ------------------------------------------------------------------------------------------------

REQUIRED_ENVIRONMENT: Final = {
    "TUB_ENVIRONMENT": "dev",
    "TUB_PUBLIC_ORIGIN": "https://tub.example.test",
    "TUB_LOGIN_ORIGIN": "https://auth.tub.example.test",
    "TUB_USER_POOL_ID": "us-east-1_SyntheticPool",
    "TUB_CLIENT_ID": "synthetic-client-id",
    "TUB_CLIENT_SECRET_PARAMETER": "/debate-dev-tub/client-secret",
    "TUB_COOKIE_KEYS_PARAMETER": "/debate-dev-tub/cookie-keys",
    "TUB_AUDIT_LOG_GROUP": "debate-dev-tub-audit",
    "TUB_EVIDENCE_BUCKET": "debate-dev-evidence-synthetic",
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ()),
        ("", ()),
        (" , ", ()),
        ("hsxx25", ("hsxx25",)),
        (" hsxx25 , hsyy24 ", ("hsxx25", "hsyy24")),
    ],
)
def test_the_offered_seasons_are_read_from_the_environment(
    value: str | None, expected: tuple[str, ...]
) -> None:
    from debate_api.configuration import PilotConfiguration

    environ = dict(REQUIRED_ENVIRONMENT)
    if value is not None:
        environ["TUB_EARLIER_SEASONS"] = value

    assert PilotConfiguration.from_environment(environ).earlier_seasons == expected


@pytest.mark.parametrize("value", ["hsxx", "hsxx25,../current", "hsxx25,hsxx25", "HSXX25"])
def test_a_season_setting_the_app_cannot_read_stops_its_cold_start(value: str) -> None:
    from debate_api.configuration import ConfigurationMissing, PilotConfiguration

    with pytest.raises(ConfigurationMissing, match="TUB_EARLIER_SEASONS"):
        PilotConfiguration.from_environment({**REQUIRED_ENVIRONMENT, "TUB_EARLIER_SEASONS": value})


def test_the_functions_container_gives_each_season_its_pointer_its_own_directory_and_the_one_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The composition root as the function runs it: its clients and its two parameters stubbed, so no
    AWS code runs, and `/tmp` this test's. A season's holder is built here by hand, as a student's
    first pick of the season builds it, and fetches nothing until it is leased.
    """
    import base64
    import json
    import tempfile

    import debate_api.container as container

    keys = json.dumps(
        {
            name: base64.b64encode(bytes([number]) * 32).decode()
            for number, name in enumerate(("current", "previous"))
        }
    )
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    for builder in (
        "build_ssm_client",
        "build_s3_client",
        "build_logs_client",
        "build_cognito_self_service_client",
    ):
        monkeypatch.setattr(container, builder, lambda **_named: object())
    monkeypatch.setattr(container, "build_ssm_client", lambda region: object())
    monkeypatch.setattr(
        container,
        "read_secure_parameter",
        lambda _client, name: keys if "cookie" in name else "synthetic-secret",
    )

    services = container.build_pilot_services(
        {**REQUIRED_ENVIRONMENT, "TUB_EARLIER_SEASONS": "hsxx25,hsyy24"}
    )
    holder = services.seasons._holder_for(SEASON_A)

    assert services.seasons.offered == (SEASON_A, SEASON_B)
    season_source, current_source = holder._source, services.search_index._source
    assert isinstance(season_source, S3SearchIndexSource)
    assert isinstance(current_source, S3SearchIndexSource)
    assert season_source.pointer_key == season_pointer_key(SEASON_A)
    assert current_source.pointer_key == SEARCH_INDEX_POINTER_KEY
    assert holder._suppression_source is services.search_index._suppression_source
    assert holder._directory == tmp_path / container.SEASON_DIRECTORY_NAME
    assert services.search_index._directory == tmp_path / container.INDEX_DIRECTORY_NAME
    assert services.card_download._seasons is services.seasons
