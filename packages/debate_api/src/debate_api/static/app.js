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
//
// Download .docx and the cart (v1-e39-t08). The cart is a list of card references,
// "<caselist>/<cluster id>", kept in this tab's sessionStorage and nowhere else: the session cookie
// holds no cart (the PM's ruling of 2026-10-22). A download POSTs the references as `cards`, with the
// CSRF token and the body's hash like every POST, and the app checks every one again. The answer is
// the file, saved through a blob link, or JSON naming the cards it refused, which the student can drop
// to download the rest. Signing out, or any page without a session, empties the cart.
//
// The pocket name (v1-e39-t24). Beside each download button is a field for the file's pocket name; a
// download sends what it holds as `pocket`, unless it is blank, and the app gives the file's one
// pocket that name, or "Team evidence search". A name the app refuses is answered with a message.
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

  const CART_KEY = "tub-download-cart";
  const REFERENCE = /^(?:[a-z]+[0-9]{2}|openev)\/[0-9a-f]{64}$/;

  const readCart = () => {
    try {
      const kept = JSON.parse(window.sessionStorage.getItem(CART_KEY) || "[]");
      return Array.isArray(kept) ? kept.filter((one) => typeof one === "string" && REFERENCE.test(one)) : [];
    } catch (error) {
      return [];
    }
  };

  const writeCart = (cards) => {
    try {
      if (cards.length) {
        window.sessionStorage.setItem(CART_KEY, JSON.stringify(cards));
      } else {
        window.sessionStorage.removeItem(CART_KEY);
      }
    } catch (error) {
      return false;
    }
    showCart();
    return true;
  };

  const cartBar = () => document.querySelector("[data-tub-cart]");

  const cartCap = () => {
    const bar = cartBar();
    const cap = bar ? Number.parseInt(bar.getAttribute("data-tub-cart-cap") || "", 10) : Number.NaN;
    return Number.isInteger(cap) && cap > 0 ? cap : 1;
  };

  const cardWords = (count) => (count === 1 ? "1 card" : `${count} cards`);

  function showCart() {
    const cards = readCart();
    const bar = cartBar();
    if (bar) {
      bar.hidden = cards.length === 0;
      const count = bar.querySelector("[data-tub-cart-count]");
      if (count) {
        count.textContent = cardWords(cards.length);
      }
    }
    for (const button of document.querySelectorAll("button[data-tub-cart-add]")) {
      button.textContent = cards.includes(button.getAttribute("data-tub-cart-add")) ? "Remove from cart" : "Add to cart";
    }
  }

  const place = (selector) => document.querySelector(selector);

  const tell = (where, text, refused, retry) => {
    if (!where) {
      return;
    }
    where.replaceChildren();
    const sentence = document.createElement("p");
    sentence.textContent = text;
    where.append(sentence);
    if (refused.length) {
      const list = document.createElement("ul");
      for (const card of refused) {
        const item = document.createElement("li");
        const name = typeof card.name === "string" && card.name ? `, ${card.name}` : "";
        item.textContent = `Card ${card.position}${name}: ${card.reason}`;
        list.append(item);
      }
      where.append(list);
    }
    if (retry) {
      const again = document.createElement("button");
      again.type = "button";
      again.textContent = "Remove these from the cart and download the rest";
      again.addEventListener("click", retry);
      where.append(again);
    }
  };

  const savedName = (response) => {
    const named = /filename="([A-Za-z0-9._-]+)"/.exec(response.headers.get("Content-Disposition") || "");
    return named ? named[1] : "team-evidence-cards.docx";
  };

  const pocketName = (fromCart) => {
    const field = place(fromCart ? "[data-tub-cart-pocket]" : "[data-tub-download-pocket]");
    return field instanceof HTMLInputElement ? field.value : "";
  };

  async function download(cards, where, button, fromCart) {
    if (button) {
      button.disabled = true;
    }
    tell(where, cards.length === 1 ? "Building the file…" : `Building the file of ${cardWords(cards.length)}…`, []);
    try {
      const fields = { cards: cards.join(",") };
      const pocket = pocketName(fromCart);
      if (pocket.trim()) {
        fields.pocket = pocket;
      }
      const body = new TextEncoder().encode(new URLSearchParams(fields).toString());
      const digest = hex(await crypto.subtle.digest("SHA-256", body));
      const response = await fetch("/download", {
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
      if (response.ok) {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(await response.blob());
        link.download = savedName(response);
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 60000);
        tell(where, `Downloaded ${cardWords(cards.length)}. Open the file in Word.`, []);
        return;
      }
      let answer = {};
      try {
        answer = await response.json();
      } catch (error) {
        answer = {};
      }
      const refused = Array.isArray(answer.refused) ? answer.refused : [];
      const dropped = new Set(refused.map((card) => card.card));
      const rest = cards.filter((card) => !dropped.has(card));
      const retry =
        fromCart && refused.length && rest.length
          ? () => {
              writeCart(readCart().filter((card) => !dropped.has(card)));
              download(rest, where, button, true);
            }
          : null;
      tell(where, typeof answer.message === "string" ? answer.message : "The file was not made. Try again.", refused, retry);
    } catch (error) {
      tell(where, "The pilot did not answer. Check the connection and try again.", []);
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  }

  function addToCart(button) {
    const card = button.getAttribute("data-tub-cart-add");
    const cards = readCart();
    const where = place("[data-tub-download-message]");
    if (!REFERENCE.test(card || "")) {
      return;
    }
    if (cards.includes(card)) {
      writeCart(cards.filter((one) => one !== card));
      tell(where, "Removed from the cart.", []);
      return;
    }
    if (cards.length >= cartCap()) {
      tell(where, `The cart holds up to ${cardWords(cartCap())}. Download it or remove one first.`, []);
      return;
    }
    if (!writeCart(cards.concat([card]))) {
      tell(where, "This browser cannot keep a cart. Download the card on its own.", []);
      return;
    }
    tell(where, "Added to the cart.", []);
  }

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target ? target.closest("button[data-tub-copy]") : null;
    if (button) {
      event.preventDefault();
      copyCard(button);
      return;
    }
    const single = target ? target.closest("button[data-tub-download]") : null;
    if (single) {
      event.preventDefault();
      download([single.getAttribute("data-tub-download")], place("[data-tub-download-message]"), single, false);
      return;
    }
    const adding = target ? target.closest("button[data-tub-cart-add]") : null;
    if (adding) {
      event.preventDefault();
      addToCart(adding);
      return;
    }
    const whole = target ? target.closest("button[data-tub-cart-download]") : null;
    if (whole) {
      event.preventDefault();
      download(readCart(), place("[data-tub-cart-message]"), whole, true);
      return;
    }
    if (target && target.closest("button[data-tub-cart-empty]")) {
      event.preventDefault();
      writeCart([]);
      tell(place("[data-tub-cart-message]"), "", []);
    }
  });

  if (!csrfToken()) {
    writeCart([]);
  }
  showCart();

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "post") {
      return;
    }
    event.preventDefault();
    if (form.getAttribute("action") === "/auth/sign-out") {
      writeCart([]);
    }
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
