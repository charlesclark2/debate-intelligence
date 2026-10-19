"""Canonical URLs (`v1-e04-t01-url-canonicalization`, ac1 to ac3).

The variant table is the acceptance table of ac1: real public URL shapes from news sites, think
tanks, .gov sites, AMP pages and link wrappers, each with the canonical form written by hand from
the rules in `debate_core.retrieval.canonical_url`. Nothing here is fetched; the URLs are shapes.
Idempotence over generated URLs is in `test_canonical_url_properties.py`.

The rel=canonical tests carry `rel_canonical` in their names, so the plan's
`-k rel_canonical` selects exactly them.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from debate_core.retrieval.canonical_url import (
    LINK_WRAPPERS,
    InvalidUrlError,
    RelCanonicalRule,
    apply_rel_canonical,
    canonicalize_url,
)
from debate_core.retrieval.query_parameters import (
    AMP_QUERY_MARKERS,
    CONTENT_PARAMETERS,
    TRACKING_PARAMETERS,
    AmpQueryMarker,
    ContentParameter,
    TrackingParameter,
    is_amp_marker,
    is_tracking_parameter,
)

# ---------------------------------------------------------------------------------------------
# ac1: the variant table
# ---------------------------------------------------------------------------------------------

NEWS = [
    pytest.param(
        "HTTPS://WWW.NYTimes.com/2020/03/12/us/politics/coronavirus-trump.html?smid=tw-nytimes&smtyp=cur",
        "https://www.nytimes.com/2020/03/12/us/politics/coronavirus-trump.html",
        id="news-scheme-and-host-case-and-nyt-share-tags",
    ),
    pytest.param(
        "https://www.theguardian.com/world/2020/mar/12/coronavirus-live-updates?CMP=share_btn_tw",
        "https://www.theguardian.com/world/2020/mar/12/coronavirus-live-updates",
        id="news-guardian-cmp-share-tag",
    ),
    pytest.param(
        "https://www.reuters.com/article/us-health-coronavirus-usa-idUSKBN20Z3C1"
        "?utm_source=twitter&utm_medium=social&utm_campaign=reuters",
        "https://www.reuters.com/article/us-health-coronavirus-usa-idUSKBN20Z3C1",
        id="news-utm-tags",
    ),
    pytest.param(
        "https://www.reuters.com:443/world/us/biden-signs-bill-2022-08-16/#main-content",
        "https://www.reuters.com/world/us/biden-signs-bill-2022-08-16/",
        id="news-default-https-port-and-fragment",
    ),
    pytest.param(
        "http://www.npr.org:80/2020/03/12/814848960/trump-addresses-nation",
        "http://www.npr.org/2020/03/12/814848960/trump-addresses-nation",
        id="news-default-http-port-scheme-kept",
    ),
    pytest.param(
        "https://apnews.com/article/virus-outbreak-health-ap-top-news-1a2b3c4d?fbclid=IwAR0abcDEF123",
        "https://apnews.com/article/virus-outbreak-health-ap-top-news-1a2b3c4d",
        id="news-fbclid",
    ),
    pytest.param(
        "https://www.cnn.com/2020/03/12/politics/trump-address/index.html"
        "?utm_term=link&utm_content=2020-03-12T01%3A30%3A04&utm_medium=social&utm_source=twCNN",
        "https://www.cnn.com/2020/03/12/politics/trump-address/index.html",
        id="news-utm-with-encoded-value",
    ),
    pytest.param(
        "https://www.wsj.com/articles/fed-cuts-rates-11584057600?mod=hp_lead_pos1",
        "https://www.wsj.com/articles/fed-cuts-rates-11584057600?mod=hp_lead_pos1",
        id="news-unknown-parameter-kept",
    ),
    pytest.param(
        "https://foreignpolicy.com/?p=123456&utm_source=Sailthru&utm_medium=email&mc_cid=a1b2c3&mc_eid=d4e5f6",
        "https://foreignpolicy.com/?p=123456",
        id="news-wordpress-post-id-beside-tracking",
    ),
    pytest.param(
        "https://www.dailyprogress.com/news/article.cfm?article=59874&utm_source=facebook&fbclid=IwAR1",
        "https://www.dailyprogress.com/news/article.cfm?article=59874",
        id="news-article-parameter-beside-tracking",
    ),
    pytest.param(
        "https://www.npr.org/templates/story/story.php?storyId=124151519&ft=1&f=1001",
        "https://www.npr.org/templates/story/story.php?f=1001&ft=1&storyId=124151519",
        id="news-parameters-sorted",
    ),
    pytest.param(
        "https://www.economist.com/briefing/2020/03/12/the-pandemic?UTM_SOURCE=newsletter&UTM_MEDIUM=email",
        "https://www.economist.com/briefing/2020/03/12/the-pandemic",
        id="news-upper-case-utm",
    ),
    pytest.param(
        "https://www.bloomberg.com/news/articles/2020-03-12/stocks-plunge?#top",
        "https://www.bloomberg.com/news/articles/2020-03-12/stocks-plunge",
        id="news-empty-query-and-fragment",
    ),
]

AMP = [
    pytest.param(
        "https://amp.theguardian.com/world/2020/mar/12/coronavirus-live-updates",
        "https://www.theguardian.com/world/2020/mar/12/coronavirus-live-updates",
        id="amp-host",
    ),
    pytest.param(
        "https://www.washingtonpost.com/politics/2020/03/12/trump-oval-office-speech/?outputType=amp",
        "https://www.washingtonpost.com/politics/2020/03/12/trump-oval-office-speech/",
        id="amp-query-output-type",
    ),
    pytest.param(
        "https://www.vox.com/2020/3/12/21176783/coronavirus-trump-speech?amp",
        "https://www.vox.com/2020/3/12/21176783/coronavirus-trump-speech",
        id="amp-query-bare-flag",
    ),
    pytest.param(
        "https://www.independent.co.uk/news/world/americas/trump-speech-a9397231.html?amp=1",
        "https://www.independent.co.uk/news/world/americas/trump-speech-a9397231.html",
        id="amp-query-flag-one",
    ),
    pytest.param(
        "https://www.bbc.com/news/amp/world-us-canada-51846468",
        "https://www.bbc.com/news/world-us-canada-51846468",
        id="amp-path-segment-middle",
    ),
    pytest.param(
        "https://www.cbsnews.com/amp/news/coronavirus-update-2020-03-12/",
        "https://www.cbsnews.com/news/coronavirus-update-2020-03-12/",
        id="amp-path-segment-first",
    ),
    pytest.param(
        "https://thehill.com/policy/healthcare/487000-trump-address/amp/",
        "https://thehill.com/policy/healthcare/487000-trump-address/",
        id="amp-path-segment-last-wordpress",
    ),
    pytest.param(
        "https://www.foxnews.com/politics/trump-oval-office-address-coronavirus.amp",
        "https://www.foxnews.com/politics/trump-oval-office-address-coronavirus",
        id="amp-path-suffix",
    ),
    pytest.param(
        "https://www.nytimes.com/2020/03/12/us/politics/trump-coronavirus-address.amp.html",
        "https://www.nytimes.com/2020/03/12/us/politics/trump-coronavirus-address.html",
        id="amp-path-amp-html",
    ),
    pytest.param(
        "https://www-nytimes-com.cdn.ampproject.org/c/s/www.nytimes.com/2020/03/12/us/politics/"
        "trump-coronavirus-address.amp.html",
        "https://www.nytimes.com/2020/03/12/us/politics/trump-coronavirus-address.html",
        id="amp-cache-content",
    ),
    pytest.param(
        "https://www-cnbc-com.cdn.ampproject.org/v/s/www.cnbc.com/amp/2020/03/12/stock-market-today-live.html"
        "?amp_js_v=0.1&usqp=mq331AQFKAGwASA%3D",
        "https://www.cnbc.com/2020/03/12/stock-market-today-live.html",
        id="amp-cache-viewer-with-viewer-parameters",
    ),
    pytest.param(
        "https://www.google.com/amp/s/www.cnbc.com/amp/2020/03/12/stock-market-today-live.html",
        "https://www.cnbc.com/2020/03/12/stock-market-today-live.html",
        id="amp-google-viewer-https",
    ),
    pytest.param(
        "https://www.google.com/amp/www.sfgate.com/news/article/coronavirus-15124367.php",
        "http://www.sfgate.com/news/article/coronavirus-15124367.php",
        id="amp-google-viewer-http",
    ),
    pytest.param(
        "https://amp.dev/documentation/guides-and-tutorials/",
        "https://amp.dev/documentation/guides-and-tutorials/",
        id="amp-label-inside-registrable-domain-kept",
    ),
]

REDIRECTS = [
    pytest.param(
        "https://news.google.com/news/url?sa=t&fd=R&ct2=us&usg=AFQjCNHx7&clid=c3a7d30bb8a4878e06b80cf16b898331"
        "&url=https://www.nytimes.com/2016/01/01/us/politics/story.html",
        "https://www.nytimes.com/2016/01/01/us/politics/story.html",
        id="redirect-google-news-legacy",
    ),
    pytest.param(
        "https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=1"
        "&url=https%3A%2F%2Fwww.brookings.edu%2Fresearch%2Fthe-future-of-work%2F&usg=AOvVaw0abc",
        "https://www.brookings.edu/research/the-future-of-work/",
        id="redirect-google-search-url-parameter",
    ),
    pytest.param(
        "https://www.google.com/url?q=https://www.cato.org/blog/trade-deficit-myths?utm_source%3Dtwitter"
        "&sa=D&source=docs&ust=1600000000000000&usg=AOvVaw1xyz",
        "https://www.cato.org/blog/trade-deficit-myths",
        id="redirect-google-docs-q-parameter",
    ),
    pytest.param(
        "https://news.google.com/articles/CBMiTGh0dHBzOi8vd3d3LnJldXRlcnMuY29tL3dvcmxkL3VzL2V4YW1wbGUtc3RvcnktMjAy"
        "My0wMS0wMS_SAQA?hl=en-US&gl=US&ceid=US%3Aen",
        "https://news.google.com/articles/CBMiTGh0dHBzOi8vd3d3LnJldXRlcnMuY29tL3dvcmxkL3VzL2V4YW1wbGUtc3RvcnktMjAy"
        "My0wMS0wMS_SAQA?ceid=US%3Aen&gl=US&hl=en-US",
        id="redirect-google-news-article-id-not-decoded",
    ),
    pytest.param(
        "https://l.facebook.com/l.php?u=https%3A%2F%2Fwww.heritage.org%2Fdefense%2Freport%2Fthe-2020-index"
        "%3Ffbclid%3DIwAR2xyz&h=AT0abc",
        "https://www.heritage.org/defense/report/the-2020-index",
        id="redirect-facebook",
    ),
    pytest.param(
        "https://nam12.safelinks.protection.outlook.com/?url=https%3A%2F%2Fwww.rand.org%2Fpubs%2Fresearch_reports"
        "%2FRR2400.html&data=05%7C01%7C%7Cabc&sdata=xyz%3D&reserved=0",
        "https://www.rand.org/pubs/research_reports/RR2400.html",
        id="redirect-outlook-safe-links",
    ),
    pytest.param(
        "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fwww.csis.org%2Fanalysis%2Fsome-analysis"
        "&urlhash=abcd&trk=public_post",
        "https://www.csis.org/analysis/some-analysis",
        id="redirect-linkedin",
    ),
    pytest.param(
        "https://www.google.com/url?q=https://l.facebook.com/l.php?u%3Dhttps%253A%252F%252Fwww.aei.org"
        "%252Fop-eds%252Fsome-op-ed%252F&sa=D",
        "https://www.aei.org/op-eds/some-op-ed/",
        id="redirect-nested-wrappers",
    ),
    pytest.param(
        "https://www.google.com/url?sa=D&q=debate+topic+analysis",
        "https://www.google.com/url?q=debate+topic+analysis&sa=D",
        id="redirect-target-not-a-url-kept",
    ),
]

THINK_TANKS = [
    pytest.param(
        "https://www.brookings.edu/articles/how-to-fix-the-electoral-college/?utm_campaign=Brookings%20Brief"
        "&utm_medium=email&utm_content=123&utm_source=hs_email&_hsenc=p2ANqtz-abc&_hsmi=123",
        "https://www.brookings.edu/articles/how-to-fix-the-electoral-college/",
        id="think-tank-hubspot-email",
    ),
    pytest.param(
        "https://www.cfr.org/backgrounder/what-nato",
        "https://www.cfr.org/backgrounder/what-nato",
        id="think-tank-already-canonical",
    ),
    pytest.param(
        "https://www.heritage.org/node/123456?gclid=EAIaIQ&gclsrc=aw.ds",
        "https://www.heritage.org/node/123456",
        id="think-tank-google-ads",
    ),
    pytest.param(
        "https://www.csis.org/analysis/strategic-competition?mkt_tok=eyJpIjoiTVRBMU5ETT0ifQ",
        "https://www.csis.org/analysis/strategic-competition",
        id="think-tank-marketo",
    ),
    pytest.param(
        "https://carnegieendowment.org/2020/03/12/china-and-the-pandemic-pub-81234?lang=en",
        "https://carnegieendowment.org/2020/03/12/china-and-the-pandemic-pub-81234?lang=en",
        id="think-tank-language-parameter-kept",
    ),
    pytest.param(
        "https://www.rand.org/pubs/research_reports/RR2400.html?__hstc=1234.abc&__hssc=1234.1.1&__hsfp=987",
        "https://www.rand.org/pubs/research_reports/RR2400.html",
        id="think-tank-hubspot-cookies",
    ),
    pytest.param(
        "https://www.cato.org/policy-analysis/caf%c3%a9-society%7e2020%2dreport",
        "https://www.cato.org/policy-analysis/caf%C3%A9-society~2020-report",
        id="think-tank-percent-encoded-path",
    ),
    pytest.param(
        "https://www.aei.org/research-products/report/us%2Fchina-trade/",
        "https://www.aei.org/research-products/report/us%2Fchina-trade/",
        id="think-tank-encoded-slash-kept",
    ),
]

GOVERNMENT = [
    pytest.param(
        "https://WWW.CBO.GOV/publication/56073?utm_source=feedblitz&utm_medium=FeedBlitzRss",
        "https://www.cbo.gov/publication/56073",
        id="gov-host-case-and-feed-tags",
    ),
    pytest.param(
        "https://www.congress.gov/bill/116th-congress/house-bill/748/text"
        "?q=%7B%22search%22%3A%5B%22cares+act%22%5D%7D&r=1&s=1",
        "https://www.congress.gov/bill/116th-congress/house-bill/748/text"
        "?q=%7B%22search%22%3A%5B%22cares+act%22%5D%7D&r=1&s=1",
        id="gov-encoded-json-query-kept",
    ),
    pytest.param(
        "https://www.whitehouse.gov/briefing-room/statements-releases/2021/01/20/inaugural-address/#main",
        "https://www.whitehouse.gov/briefing-room/statements-releases/2021/01/20/inaugural-address/",
        id="gov-fragment",
    ),
    pytest.param(
        "https://www.gao.gov/products/gao-20-625?utm_medium=email&utm_source=govdelivery",
        "https://www.gao.gov/products/gao-20-625",
        id="gov-govdelivery-tags",
    ),
    pytest.param(
        "https://www.federalregister.gov/documents/2020/03/18/2020-05794/declaring-a-national-emergency",
        "https://www.federalregister.gov/documents/2020/03/18/2020-05794/declaring-a-national-emergency",
        id="gov-already-canonical",
    ),
    pytest.param(
        "https://www.state.gov/../reports/", "https://www.state.gov/reports/", id="gov-dot-dot-at-the-root"
    ),
    pytest.param(
        "https://www.state.gov/reports/../reports/2019-country-reports-on-human-rights-practices/./china/",
        "https://www.state.gov/reports/2019-country-reports-on-human-rights-practices/china/",
        id="gov-dot-segments",
    ),
    pytest.param("https://www.energy.gov", "https://www.energy.gov/", id="gov-empty-path"),
    pytest.param(
        "https://www.nasa.gov./news-release/nasa-artemis/",
        "https://www.nasa.gov/news-release/nasa-artemis/",
        id="gov-trailing-dot-host",
    ),
    pytest.param(
        "https://data.census.gov/table?y=2020&g=040XX00US06&g=040XX00US01",
        "https://data.census.gov/table?g=040XX00US06&g=040XX00US01&y=2020",
        id="gov-repeated-parameter-keeps-its-order",
    ),
    pytest.param(
        "https://www.c-span.org/video/?470440-1/president-trump-addresses-nation-coronavirus",
        "https://www.c-span.org/video/?470440-1/president-trump-addresses-nation-coronavirus",
        id="gov-bare-query-key-kept",
    ),
    pytest.param(
        "HTTP://www.SEC.gov:80/news/press-release/2020-63",
        "http://www.sec.gov/news/press-release/2020-63",
        id="gov-upper-case-scheme-and-default-port",
    ),
    pytest.param(
        "https://www.supremecourt.gov/opinions/slipopinion/19/",
        "https://www.supremecourt.gov/opinions/slipopinion/19/",
        id="gov-trailing-slash-kept",
    ),
    pytest.param(
        "https://www.supremecourt.gov/opinions/slipopinion/19",
        "https://www.supremecourt.gov/opinions/slipopinion/19",
        id="gov-no-trailing-slash-kept",
    ),
]

INTERNATIONAL = [
    pytest.param("https://例え.テスト/", "https://xn--r8jz45g.xn--zckzah/", id="idna-japanese-test-domain"),
    pytest.param(
        "https://faß.de/impressum", "https://xn--fa-hia.de/impressum", id="idna-sharp-s-nontransitional"
    ),
    pytest.param(
        "https://BÜCHER.example/Shop", "https://xn--bcher-kva.example/Shop", id="idna-upper-case-unicode-host"
    ),
    pytest.param(
        "https://XN--BCHER-KVA.example/Shop",
        "https://xn--bcher-kva.example/Shop",
        id="idna-upper-case-ace-host",
    ),
    pytest.param(
        "https://de.wikipedia.org/wiki/Außenpolitik_der_Vereinigten_Staaten",
        "https://de.wikipedia.org/wiki/Au%C3%9Fenpolitik_der_Vereinigten_Staaten",
        id="unicode-path-percent-encoded",
    ),
]

VARIANT_PAIRS = [*NEWS, *AMP, *REDIRECTS, *THINK_TANKS, *GOVERNMENT, *INTERNATIONAL]


def test_the_variant_table_has_at_least_forty_pairs() -> None:
    """ac1 asks for at least 40 real-world pairs."""
    assert len(VARIANT_PAIRS) >= 40


@pytest.mark.parametrize(("variant", "canonical"), VARIANT_PAIRS)
def test_a_variant_maps_to_its_canonical_form(variant: str, canonical: str) -> None:
    assert canonicalize_url(variant) == canonical


@pytest.mark.parametrize(("variant", "canonical"), VARIANT_PAIRS)
def test_a_canonical_form_is_its_own_canonical_form(variant: str, canonical: str) -> None:
    """Idempotence on the table; generated URLs are in the property suite."""
    assert canonicalize_url(canonical) == canonical


def test_a_trailing_slash_is_never_added_or_removed() -> None:
    """`/19/` and `/19` are kept apart: relative links resolve differently under each (RFC 3986
    §5.2.3), so the server may serve different documents, and only a page's own rel=canonical
    can say they are one."""
    assert canonicalize_url("https://www.supremecourt.gov/opinions/slipopinion/19/") != canonicalize_url(
        "https://www.supremecourt.gov/opinions/slipopinion/19"
    )


def test_a_deeper_amp_subdomain_loses_only_the_amp_label() -> None:
    assert canonicalize_url("https://amp.news.example.co.uk/story/1") == "https://news.example.co.uk/story/1"


def test_repeated_amp_markers_are_all_removed() -> None:
    assert (
        canonicalize_url("https://amp.amp.example.com/a/amp/b.amp.amp?amp=1&amp")
        == "https://www.example.com/a/b"
    )


def test_an_amp_parameter_with_another_value_is_kept() -> None:
    """Only the values AMP pages use are markers; `amp=4` may be content (an amplitude, a page)."""
    assert (
        canonicalize_url("https://www.example.com/calculator?amp=4")
        == "https://www.example.com/calculator?amp=4"
    )


def test_a_wrapper_whose_target_is_not_a_web_url_is_kept() -> None:
    assert (
        canonicalize_url("https://l.facebook.com/l.php?u=javascript%3Aalert(1)")
        == "https://l.facebook.com/l.php?u=javascript%3Aalert(1)"
    )


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://www.example.org/share?url=https%3A%2F%2Fwww.cato.org%2F", id="share-path"),
        pytest.param(
            "https://www.example.org/?url=https%3A%2F%2Fwww.cato.org%2F", id="root-path-like-safe-links"
        ),
    ],
)
def test_a_query_redirect_on_another_host_is_not_unwrapped(url: str) -> None:
    """The wrapper rules name their hosts; a `url=` parameter elsewhere is content."""
    assert canonicalize_url(url) == url


def test_a_wrapper_destination_with_no_public_host_is_kept() -> None:
    assert (
        canonicalize_url("https://www.google.com/url?q=http://intranet/report")
        == "https://www.google.com/url?q=http://intranet/report"
    )


def test_an_amp_cache_keeps_the_origins_own_query() -> None:
    assert (
        canonicalize_url(
            "https://www-example-com.cdn.ampproject.org/c/s/www.example.com/story.php?id=42&usqp=mq331AQ"
        )
        == "https://www.example.com/story.php?id=42"
    )


def test_a_url_the_amp_host_rule_turns_into_a_wrapper_is_unwrapped() -> None:
    """`amp.google.com` becomes `www.google.com`, a wrapper host; stopping there would not be a
    fixed point, since a second canonicalization would unwrap it."""
    assert canonicalize_url("https://amp.google.com/url?q=https://www.cato.org/x") == "https://www.cato.org/x"


def test_userinfo_is_kept_in_normalized_form() -> None:
    assert (
        canonicalize_url("https://reader:p%40ss@WWW.Example.org/a")
        == "https://reader:p%40ss@www.example.org/a"
    )


def test_empty_query_pieces_are_dropped() -> None:
    assert (
        canonicalize_url("https://www.example.org/read?&id=7&&page=2&")
        == "https://www.example.org/read?id=7&page=2"
    )


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/a/.amp", id="suffix-alone"),
        pytest.param("/a/..amp", id="would-become-dot"),
        pytest.param("/a/...amp", id="would-become-dot-dot"),
    ],
)
def test_an_amp_suffix_that_is_the_whole_name_is_kept(path: str) -> None:
    """Stripping it would leave an empty or dot segment, a different path."""
    assert canonicalize_url(f"https://www.example.org{path}") == f"https://www.example.org{path}"


def test_a_lone_percent_sign_is_encoded() -> None:
    assert canonicalize_url("https://www.example.org/100%-sure") == "https://www.example.org/100%25-sure"


def test_a_lone_surrogate_is_refused() -> None:
    with pytest.raises(InvalidUrlError):
        canonicalize_url("https://www.example.org/\ud800")


def test_deeply_nested_wrappers_are_refused_rather_than_unwound_forever() -> None:
    url = "https://www.cato.org/"
    for _ in range(40):
        url = "https://www.google.com/url?q=" + url.replace("%", "%25").replace("&", "%26").replace(
            "?", "%3F"
        )
    with pytest.raises(InvalidUrlError):
        canonicalize_url(url)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("ftp://ftp.example.org/report.pdf", id="ftp"),
        pytest.param("mailto:editor@example.org", id="mailto"),
        pytest.param("www.example.com/article", id="no-scheme"),
        pytest.param("https://", id="no-host"),
        pytest.param("https:///path", id="empty-host"),
        pytest.param("https://exa mple.com/", id="space-in-host"),
        pytest.param("https://example..com/", id="empty-label"),
        pytest.param("https://example.com:99999/", id="port-out-of-range"),
        pytest.param("https://example.com:http/", id="port-not-a-number"),
        pytest.param("https://[::1/", id="unclosed-ipv6"),
        pytest.param("", id="empty"),
    ],
)
def test_a_url_that_is_not_absolute_http_is_refused(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        canonicalize_url(url)


def test_the_refusal_is_a_value_error() -> None:
    """Callers that already catch ValueError for bad input keep working."""
    assert issubclass(InvalidUrlError, ValueError)


def test_an_ipv6_host_keeps_its_brackets_and_loses_its_case() -> None:
    assert canonicalize_url("http://[2001:DB8::1]:8080/a") == "http://[2001:db8::1]:8080/a"


def test_a_non_default_port_is_kept() -> None:
    assert canonicalize_url("https://www.example.org:8443/a") == "https://www.example.org:8443/a"


def test_surrounding_whitespace_is_ignored() -> None:
    assert (
        canonicalize_url("  https://www.cfr.org/backgrounder/what-nato\n")
        == "https://www.cfr.org/backgrounder/what-nato"
    )


# ---------------------------------------------------------------------------------------------
# ac2: the documented deny and allow lists
# ---------------------------------------------------------------------------------------------


def test_the_deny_list_names_the_parameters_the_spec_names() -> None:
    exact = {rule.name for rule in TRACKING_PARAMETERS if not rule.prefix}
    prefixes = {rule.name for rule in TRACKING_PARAMETERS if rule.prefix}
    assert {"fbclid", "gclid", "mc_cid"} <= exact
    assert "utm_" in prefixes


def test_the_allow_list_names_the_parameters_the_spec_names() -> None:
    assert {"id", "p", "article"} <= {rule.name for rule in CONTENT_PARAMETERS}


@pytest.mark.parametrize(
    "rules", [TRACKING_PARAMETERS, CONTENT_PARAMETERS, AMP_QUERY_MARKERS], ids=["deny", "allow", "amp"]
)
def test_every_list_entry_is_lower_case_unique_and_gives_a_reason(
    rules: Sequence[TrackingParameter | ContentParameter | AmpQueryMarker],
) -> None:
    names = [rule.name for rule in rules]
    assert names, "the list is empty"
    assert len(names) == len(set(names))
    for rule in rules:
        assert rule.name == rule.name.lower()
        assert len(rule.reason.split()) >= 3, rule


@pytest.mark.parametrize("content", CONTENT_PARAMETERS, ids=lambda rule: rule.name)
def test_no_deny_rule_or_amp_marker_matches_an_allow_listed_parameter(content: ContentParameter) -> None:
    """The allow list is the deny list's guard: a new prefix rule that swallowed `p` or `id`
    fails here, before it drops an article id from a stored URL."""
    name = content.name
    assert not is_tracking_parameter(name)
    assert not is_tracking_parameter(name.upper())
    for value in (None, "", "1", "true", "amp", "42"):
        assert not is_amp_marker(name, value)


def test_every_link_wrapper_destination_parameter_is_allow_listed() -> None:
    """A wrapper whose destination is not a web URL is kept, parameter and all."""
    destinations = {parameter for wrapper in LINK_WRAPPERS for parameter in wrapper.parameters}
    assert destinations <= {rule.name for rule in CONTENT_PARAMETERS}


@pytest.mark.parametrize("content", CONTENT_PARAMETERS, ids=lambda rule: rule.name)
def test_an_allow_listed_parameter_survives_beside_tracking_parameters(content: ContentParameter) -> None:
    name = content.name
    url = f"https://www.example.org/read?utm_source=x&{name}=4521&fbclid=y&gclid=z"
    assert canonicalize_url(url) == f"https://www.example.org/read?{name}=4521"


@pytest.mark.parametrize("tracking", TRACKING_PARAMETERS, ids=lambda rule: rule.name)
def test_every_deny_rule_strips_its_parameter(tracking: TrackingParameter) -> None:
    name = tracking.name + ("campaign" if tracking.prefix else "")
    assert (
        canonicalize_url(f"https://www.example.org/read?{name}=x&id=7") == "https://www.example.org/read?id=7"
    )


@pytest.mark.parametrize(
    "name", ["mod", "ref", "src", "source", "cid", "share", "s", "lang", "edition", "x_utm"]
)
def test_an_unknown_parameter_is_kept(name: str) -> None:
    """Unknown means kept: these look like tracking on some sites and select content on others."""
    assert not is_tracking_parameter(name)
    assert (
        canonicalize_url(f"https://www.example.org/read?{name}=1") == f"https://www.example.org/read?{name}=1"
    )


def test_a_prefix_rule_matches_only_at_the_start() -> None:
    assert is_tracking_parameter("utm_anything")
    assert not is_tracking_parameter("x_utm_source")


def test_a_percent_encoded_tracking_name_is_still_recognised() -> None:
    assert (
        canonicalize_url("https://www.example.org/read?utm%5Fsource=x&id=7")
        == "https://www.example.org/read?id=7"
    )


# ---------------------------------------------------------------------------------------------
# ac3: rel=canonical
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("declared", [None, "", "   "])
def test_rel_canonical_absent_keeps_the_fetched_url(declared: str | None) -> None:
    decision = apply_rel_canonical("https://www.cfr.org/backgrounder/what-nato?utm_source=x", declared)
    assert decision.rule is RelCanonicalRule.ABSENT
    assert decision.canonical_url == "https://www.cfr.org/backgrounder/what-nato"
    assert decision.declared_url is None
    assert not decision.accepted


def test_rel_canonical_on_another_subdomain_of_the_same_site_is_accepted() -> None:
    decision = apply_rel_canonical(
        "https://amp.theguardian.com/world/2020/mar/12/live",
        "https://www.theguardian.com/world/2020/mar/12/live?CMP=share_btn_tw",
    )
    assert decision.rule is RelCanonicalRule.SAME_SITE
    assert decision.accepted
    assert decision.canonical_url == "https://www.theguardian.com/world/2020/mar/12/live"
    assert decision.declared_url == "https://www.theguardian.com/world/2020/mar/12/live"


def test_rel_canonical_decides_a_trailing_slash() -> None:
    decision = apply_rel_canonical(
        "https://www.brookings.edu/articles/how-to-fix-it",
        "https://www.brookings.edu/articles/how-to-fix-it/",
    )
    assert decision.rule is RelCanonicalRule.SAME_SITE
    assert decision.canonical_url == "https://www.brookings.edu/articles/how-to-fix-it/"


@pytest.mark.parametrize(
    "declared",
    [
        pytest.param("/articles/how-to-fix-it/", id="path-relative"),
        pytest.param("//www.brookings.edu/articles/how-to-fix-it/", id="scheme-relative"),
        pytest.param("how-to-fix-it/", id="document-relative"),
    ],
)
def test_rel_canonical_relative_reference_is_resolved_against_the_fetched_url(declared: str) -> None:
    decision = apply_rel_canonical("https://www.brookings.edu/articles/how-to-fix-it", declared)
    assert decision.rule is RelCanonicalRule.SAME_SITE
    assert decision.canonical_url == "https://www.brookings.edu/articles/how-to-fix-it/"


def test_rel_canonical_with_the_other_scheme_on_the_same_site_is_accepted() -> None:
    decision = apply_rel_canonical(
        "http://www.npr.org/2020/03/12/814848960/x", "https://www.npr.org/2020/03/12/814848960/x"
    )
    assert decision.rule is RelCanonicalRule.SAME_SITE
    assert decision.canonical_url == "https://www.npr.org/2020/03/12/814848960/x"


@pytest.mark.parametrize(
    ("fetched", "declared"),
    [
        pytest.param(
            "https://news.yahoo.com/trump-speech-123.html",
            "https://www.reuters.com/article/us-health-coronavirus-idUSKBN20Z3C1",
            id="syndication-partner",
        ),
        pytest.param(
            "https://www.bbc.co.uk/news/x", "https://www.bbc.com/news/x", id="same-name-other-suffix"
        ),
        pytest.param(
            "https://www.example.co.uk/a",
            "https://www.other.co.uk/a",
            id="two-owners-under-one-public-suffix",
        ),
        pytest.param(
            "https://alice.github.io/post", "https://bob.github.io/post", id="two-owners-on-a-private-suffix"
        ),
        pytest.param("http://192.0.2.10/report", "http://192.0.2.11/report", id="two-ip-addresses"),
    ],
)
def test_rel_canonical_on_another_site_is_refused(fetched: str, declared: str) -> None:
    decision = apply_rel_canonical(fetched, declared)
    assert decision.rule is RelCanonicalRule.CROSS_SITE_REFUSED
    assert not decision.accepted
    assert decision.canonical_url == canonicalize_url(fetched)
    assert decision.declared_url == canonicalize_url(declared)


def test_rel_canonical_on_the_same_ip_address_is_accepted() -> None:
    decision = apply_rel_canonical("http://192.0.2.10/report", "http://192.0.2.10/report/")
    assert decision.rule is RelCanonicalRule.SAME_SITE
    assert decision.canonical_url == "http://192.0.2.10/report/"


@pytest.mark.parametrize(
    ("fetched", "declared", "canonical"),
    [
        pytest.param(
            "https://www-nytimes-com.cdn.ampproject.org/c/s/www.nytimes.com/2020/03/12/us/x.amp.html",
            "https://www.nytimes.com/2020/03/12/us/x.html",
            "https://www.nytimes.com/2020/03/12/us/x.html",
            id="amp-cache",
        ),
        pytest.param(
            "https://www.google.com/amp/s/www.cnbc.com/amp/2020/03/12/x.html",
            "https://www.cnbc.com/2020/03/12/x.html",
            "https://www.cnbc.com/2020/03/12/x.html",
            id="google-amp-viewer",
        ),
    ],
)
def test_rel_canonical_from_an_amp_cache_to_its_origin_site_is_accepted_by_the_allow_rule(
    fetched: str, declared: str, canonical: str
) -> None:
    decision = apply_rel_canonical(fetched, declared)
    assert decision.rule is RelCanonicalRule.AMP_CACHE_ORIGIN
    assert decision.accepted
    assert decision.canonical_url == canonical


def test_rel_canonical_from_an_amp_cache_to_a_third_site_is_refused() -> None:
    decision = apply_rel_canonical(
        "https://www-nytimes-com.cdn.ampproject.org/c/s/www.nytimes.com/2020/03/12/us/x.amp.html",
        "https://www.example.com/x",
    )
    assert decision.rule is RelCanonicalRule.CROSS_SITE_REFUSED
    assert decision.canonical_url == "https://www.nytimes.com/2020/03/12/us/x.html"


def test_rel_canonical_from_a_link_wrapper_is_not_an_allow_rule() -> None:
    """A wrapper's HTML is the wrapper's, not the publisher's, so its rel=canonical proves nothing."""
    decision = apply_rel_canonical(
        "https://www.google.com/url?q=https://www.cato.org/x", "https://www.cato.org/x"
    )
    assert decision.rule is RelCanonicalRule.CROSS_SITE_REFUSED


@pytest.mark.parametrize(
    "declared", ["javascript:void(0)", "mailto:editor@example.org", "https://", "http://exa mple.com/"]
)
def test_rel_canonical_that_is_not_a_web_url_is_unusable(declared: str) -> None:
    decision = apply_rel_canonical("https://www.cfr.org/backgrounder/what-nato", declared)
    assert decision.rule is RelCanonicalRule.UNUSABLE
    assert decision.canonical_url == "https://www.cfr.org/backgrounder/what-nato"
    assert decision.declared_url is None
    assert not decision.accepted


def test_rel_canonical_on_an_invalid_fetched_url_is_refused_loudly() -> None:
    with pytest.raises(InvalidUrlError):
        apply_rel_canonical("ftp://ftp.example.org/x", "https://www.example.org/x")


def test_rel_canonical_rules_are_stable_storable_values() -> None:
    """A later task stores the rule; the stored strings are the contract, not the member names."""
    assert {rule.value for rule in RelCanonicalRule} == {
        "absent",
        "unusable",
        "same_site",
        "amp_cache_origin",
        "cross_site_refused",
    }
    assert RelCanonicalRule("amp_cache_origin") is RelCanonicalRule.AMP_CACHE_ORIGIN
