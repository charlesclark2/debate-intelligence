"""The query parameters canonicalization strips, and the ones it must keep, each with its reason.

This module is the one place these lists live (v1-e04-t01 ac2). `canonical_url.canonicalize_url`
reads the first and third; the second guards the first.

* **`TRACKING_PARAMETERS`, the deny list.** Parameters that record how a reader arrived (a
  campaign, a click, a share button, an email) and never what they read. Each is stripped. Names
  are compared case-insensitively, because `UTM_SOURCE` is seen in the wild; `utm%5Fsource` is
  caught too, since the syntax rules decode it to `utm_source` first. A rule is an exact name
  unless it is marked as a prefix; `utm_` is the only prefix, since the Urchin convention reserves
  the whole family.
* **`CONTENT_PARAMETERS`, the allow list.** Parameters known to select what is read: an article or
  post id, a page, a video, a search, a wrapped destination. Since an unknown parameter is kept
  anyway, this list changes nothing at run time. It is the deny list's guard: the test suite fails
  if any deny rule or AMP marker matches one of these names, so a new rule cannot quietly drop an
  article id from every stored URL.
* **`AMP_QUERY_MARKERS`.** Parameters that only ask for the AMP rendering of the same article,
  stripped with the other AMP rules. Each matches only the values AMP uses: `amp=4` could be an
  amplitude, `outputType=print` a different rendering.

**Anything on none of these lists is kept.** A parameter that looks like tracking on one site
(`mod`, `ref`, `src`, `cid`) selects content on another, and dropping it would merge two articles
into one; keeping a tracking parameter only costs a duplicate Article that rel=canonical can merge
later. Extend the deny list only with a name that tracks on every site that uses it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AMP_QUERY_MARKERS",
    "CONTENT_PARAMETERS",
    "TRACKING_PARAMETERS",
    "AmpQueryMarker",
    "ContentParameter",
    "TrackingParameter",
    "is_amp_marker",
    "is_tracking_parameter",
]


@dataclass(frozen=True, slots=True)
class TrackingParameter:
    """A deny-list entry: a lower-case name, or a name prefix when `prefix` is set."""

    name: str
    reason: str
    prefix: bool = False


@dataclass(frozen=True, slots=True)
class ContentParameter:
    """An allow-list entry: a lower-case name that selects content and must survive."""

    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class AmpQueryMarker:
    """A parameter that asks for the AMP rendering.

    `values` are the lower-case values that make it a marker, `None` among them meaning the bare
    name with no `=`.
    """

    name: str
    values: frozenset[str | None]
    reason: str


_GOOGLE_ADS = "Google Ads click identifier, added to the landing page URL by auto-tagging."
_HUBSPOT = "HubSpot email and analytics tracking, added to links in HubSpot emails."
_FACEBOOK_SHARE = "Facebook share and Open Graph action tracking, added to shared links."
_AMP_VIEWER = "Google AMP viewer and cache state, added when an AMP page is served from the cache."
_ELOQUA = "Oracle Eloqua email campaign tracking."

TRACKING_PARAMETERS: tuple[TrackingParameter, ...] = (
    TrackingParameter(
        "utm_",
        "Urchin Tracking Module campaign tags, used by Google Analytics and most mailers.",
        prefix=True,
    ),
    TrackingParameter("fbclid", "Facebook click identifier, added to every outbound link."),
    TrackingParameter("gclid", _GOOGLE_ADS),
    TrackingParameter("gclsrc", _GOOGLE_ADS),
    TrackingParameter("dclid", "Google Display & Video 360 click identifier."),
    TrackingParameter("gbraid", _GOOGLE_ADS),
    TrackingParameter("wbraid", _GOOGLE_ADS),
    TrackingParameter("gad_source", _GOOGLE_ADS),
    TrackingParameter("msclkid", "Microsoft Advertising click identifier."),
    TrackingParameter("twclid", "X (Twitter) Ads click identifier."),
    TrackingParameter("ttclid", "TikTok Ads click identifier."),
    TrackingParameter("li_fat_id", "LinkedIn Ads first-party click identifier."),
    TrackingParameter("yclid", "Yandex Direct click identifier."),
    TrackingParameter("igshid", "Instagram share identifier, added by the share sheet."),
    TrackingParameter("igsh", "Instagram share identifier, the newer short form."),
    TrackingParameter("mc_cid", "Mailchimp campaign identifier, added to links in Mailchimp emails."),
    TrackingParameter("mc_eid", "Mailchimp subscriber identifier, added to links in Mailchimp emails."),
    TrackingParameter("_hsenc", _HUBSPOT),
    TrackingParameter("_hsmi", _HUBSPOT),
    TrackingParameter("__hstc", _HUBSPOT),
    TrackingParameter("__hssc", _HUBSPOT),
    TrackingParameter("__hsfp", _HUBSPOT),
    TrackingParameter("hsctatracking", _HUBSPOT),
    TrackingParameter("mkt_tok", "Marketo email tracking token."),
    TrackingParameter("elqtrackid", _ELOQUA),
    TrackingParameter("elqtrack", _ELOQUA),
    TrackingParameter("elqaid", _ELOQUA),
    TrackingParameter("elqat", _ELOQUA),
    TrackingParameter("elqcampaignid", _ELOQUA),
    TrackingParameter("_ga", "Google Analytics cross-domain linker, carries the reader's client id."),
    TrackingParameter("_gl", "Google Analytics cross-domain linker, carries the reader's client id."),
    TrackingParameter("_branch_match_id", "Branch deep-link attribution identifier."),
    TrackingParameter("oly_anon_id", "Omeda audience tracking, added to newsletter links."),
    TrackingParameter("oly_enc_id", "Omeda audience tracking, added to newsletter links."),
    TrackingParameter("vero_id", "Vero email tracking."),
    TrackingParameter("vero_conv", "Vero email conversion tracking."),
    TrackingParameter("wickedid", "Wicked Reports attribution identifier."),
    TrackingParameter("s_kwcid", "Adobe Advertising keyword and campaign tracking."),
    TrackingParameter("ef_id", "Adobe Advertising click identifier."),
    TrackingParameter("s_cid", "Adobe Analytics campaign identifier."),
    TrackingParameter("smid", "New York Times social share identifier (smid=tw-nytimes)."),
    TrackingParameter("smtyp", "New York Times social share type, sent beside smid."),
    TrackingParameter("cmp", "Guardian campaign code (CMP=share_btn_tw), added by share buttons."),
    TrackingParameter(
        "cmpid", "Campaign identifier added to shared and syndicated links by several publishers."
    ),
    TrackingParameter("ncid", "Yahoo and HuffPost newsletter and syndication campaign identifier."),
    TrackingParameter("ocid", "Microsoft Start (MSN) syndication campaign identifier."),
    TrackingParameter("xtor", "AT Internet campaign tag, used by many European publishers."),
    TrackingParameter("at_medium", "AT Internet / Piano campaign medium, used by the BBC."),
    TrackingParameter("at_campaign", "AT Internet / Piano campaign name, used by the BBC."),
    TrackingParameter("ref_src", "X (Twitter) embed and share referral source."),
    TrackingParameter("ref_url", "X (Twitter) embed referral page."),
    TrackingParameter("__twitter_impression", "X (Twitter) impression flag on embedded links."),
    TrackingParameter("fb_action_ids", _FACEBOOK_SHARE),
    TrackingParameter("fb_action_types", _FACEBOOK_SHARE),
    TrackingParameter("fb_ref", _FACEBOOK_SHARE),
    TrackingParameter("fb_source", _FACEBOOK_SHARE),
    TrackingParameter("action_object_map", _FACEBOOK_SHARE),
    TrackingParameter("action_type_map", _FACEBOOK_SHARE),
    TrackingParameter("action_ref_map", _FACEBOOK_SHARE),
    TrackingParameter("guccounter", "Yahoo consent interstitial counter, added after the consent redirect."),
    TrackingParameter("guce_referrer", "Yahoo consent interstitial referrer."),
    TrackingParameter("guce_referrer_sig", "Yahoo consent interstitial referrer signature."),
    TrackingParameter("usqp", _AMP_VIEWER),
    TrackingParameter("amp_js_v", _AMP_VIEWER),
    TrackingParameter("amp_gsa", _AMP_VIEWER),
    TrackingParameter("amp_ct", _AMP_VIEWER),
    TrackingParameter("amp_tf", _AMP_VIEWER),
    TrackingParameter("aoh", _AMP_VIEWER),
)

CONTENT_PARAMETERS: tuple[ContentParameter, ...] = (
    ContentParameter("id", "Generic record or article id (?id=8675309), the most common content selector."),
    ContentParameter("p", "WordPress post id: /?p=123456 is the post itself."),
    ContentParameter("page_id", "WordPress page id."),
    ContentParameter("article", "Article id in many news CMSes (article.cfm?article=59874)."),
    ContentParameter("articleid", "Article id in many news CMSes."),
    ContentParameter("story", "Story id in many news CMSes."),
    ContentParameter("storyid", "Story id (NPR story.php?storyId=124151519)."),
    ContentParameter("page", "Page of a multi-page article or report."),
    ContentParameter("v", "YouTube video id (watch?v=...)."),
    ContentParameter("doi", "DOI of the work a landing page shows."),
    ContentParameter("docid", "Document id in report and filing repositories."),
    ContentParameter("q", "Search query of a results page, and the destination of a Google link wrapper."),
    ContentParameter("url", "Destination of a link wrapper, which canonicalization reads."),
    ContentParameter("u", "Destination of the Facebook link wrapper, which canonicalization reads."),
)

AMP_QUERY_MARKERS: tuple[AmpQueryMarker, ...] = (
    AmpQueryMarker(
        "amp",
        frozenset({None, "", "1", "true"}),
        "AMP rendering flag (?amp, ?amp=1) on Vox Media, Independent and many WordPress sites.",
    ),
    AmpQueryMarker("outputtype", frozenset({"amp"}), "Washington Post AMP rendering (?outputType=amp)."),
)

_EXACT = frozenset(rule.name for rule in TRACKING_PARAMETERS if not rule.prefix)
_PREFIXES = tuple(rule.name for rule in TRACKING_PARAMETERS if rule.prefix)
_AMP_MARKERS = {marker.name: marker.values for marker in AMP_QUERY_MARKERS}


def _comparable(text: str) -> str:
    # No percent-decoding: the canonicalizer's syntax rules have already decoded every unreserved
    # character, and every name and value on these lists is made of unreserved characters only.
    return text.lower()


def is_tracking_parameter(name: str) -> bool:
    """True if the name, as the syntax rules leave it, is on the deny list."""
    name = _comparable(name)
    return name in _EXACT or name.startswith(_PREFIXES)


def is_amp_marker(name: str, value: str | None) -> bool:
    """True if the parameter only asks for the AMP rendering; `value` is None for a bare name."""
    name = _comparable(name)
    if name not in _AMP_MARKERS:
        return False
    return (None if value is None else _comparable(value)) in _AMP_MARKERS[name]
