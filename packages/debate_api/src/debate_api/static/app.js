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
// v1-e39-t06 extends this file for Copy card.
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
