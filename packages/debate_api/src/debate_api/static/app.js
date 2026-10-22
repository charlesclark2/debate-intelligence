// The pilot's one script (ADR-0019 (a) 3 and (b) 1): first-party, served from a content-hashed
// path under /static/, with no inline script and nothing from another origin.
//
// It sends every state-changing request with fetch, because two things refuse one that arrives any
// other way. CloudFront's origin access control refuses a POST to the function URL without the
// SHA-256 of its body in x-amz-content-sha256, and the app refuses one without the session's CSRF
// token in X-CSRF-Token. A plain form post, sent with this script off, is refused at the origin.
//
// Every <form method="post"> on a page is sent this way. The app answers with JSON: a `location`
// to go to next, or a `message` to show in the form's [data-tub-message] element.
//
// Copy card (v1-e39-t06). A card page's [data-tub-copy] button names the card's copy path on the
// pilot. On the click, the script fetches that path and writes text/html and text/plain to the
// clipboard with the Clipboard API. The write is made inside the click, while its user activation
// lasts: the ClipboardItem is given Promises of the fetch, and the browser waits for them itself.
// Awaiting the fetch first and writing after would lose the activation (Safari on a phone at once,
// Chrome once the fetch is slow), and the copy would be refused.
"use strict";

(() => {
  const csrfToken = () => {
    const meta = document.querySelector('meta[name="tub-csrf"]');
    return meta ? meta.getAttribute("content") || "" : "";
  };

  const hex = (buffer) =>
    Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");

  const say = (form, text) => {
    const place = form.querySelector("[data-tub-message]") || document.querySelector("[data-tub-message]");
    if (place) {
      place.textContent = text;
    }
  };

  const isPlaceToGo = (location) =>
    typeof location === "string" &&
    ((location.startsWith("/") && !location.startsWith("//")) || location.startsWith("https://"));

  async function send(form) {
    const body = new TextEncoder().encode(new URLSearchParams(new FormData(form)).toString());
    const digest = hex(await crypto.subtle.digest("SHA-256", body));
    const response = await fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRF-Token": csrfToken(),
        "x-amz-content-sha256": digest,
      },
      body,
    });
    let answer = {};
    try {
      answer = await response.json();
    } catch (error) {
      answer = {};
    }
    if (isPlaceToGo(answer.location)) {
      window.location.assign(answer.location);
      return;
    }
    say(form, typeof answer.message === "string" ? answer.message : "That did not work. Reload the page and try again.");
  }

  const isOwnPath = (path) => typeof path === "string" && path.startsWith("/") && !path.startsWith("//");

  const sayCopied = (button, text) => {
    const place = button.parentElement ? button.parentElement.querySelector("[data-tub-copy-message]") : null;
    if (place) {
      place.textContent = text;
    }
  };

  function copyCard(button) {
    const path = button.getAttribute("data-tub-copy");
    if (!isOwnPath(path) || button.getAttribute("aria-busy") === "true") {
      return;
    }
    if (!navigator.clipboard || typeof navigator.clipboard.write !== "function" || typeof ClipboardItem === "undefined") {
      sayCopied(button, "This browser cannot copy a formatted card. Select the card's text and copy that.");
      return;
    }
    const copied = fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { Accept: "application/json" },
    }).then((response) =>
      response.json().then((answer) => {
        if (!response.ok || typeof answer.html !== "string" || typeof answer.text !== "string") {
          throw new Error(typeof answer.message === "string" ? answer.message : "");
        }
        return answer;
      }),
    );
    const item = new ClipboardItem({
      "text/html": copied.then((answer) => new Blob([answer.html], { type: "text/html" })),
      "text/plain": copied.then((answer) => new Blob([answer.text], { type: "text/plain" })),
    });
    button.setAttribute("aria-busy", "true");
    sayCopied(button, "Copying the card…");
    navigator.clipboard
      .write([item])
      .then(() => sayCopied(button, "Copied. Paste it into Google Docs or Word."))
      .catch(() =>
        copied.then(
          () => sayCopied(button, "The card was not copied. Try again."),
          (error) => sayCopied(button, error.message || "The card was not copied. Try again."),
        ),
      )
      .finally(() => button.removeAttribute("aria-busy"));
  }

  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-tub-copy]") : null;
    if (button) {
      event.preventDefault();
      copyCard(button);
    }
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "post") {
      return;
    }
    event.preventDefault();
    const button = form.querySelector("button");
    if (button) {
      button.disabled = true;
    }
    send(form)
      .catch(() => say(form, "The pilot did not answer. Check the connection and try again."))
      .finally(() => {
        if (button) {
          button.disabled = false;
        }
      });
  });
})();
