// CloudFront Function, viewer request: map a page URL to the object that holds it.
//
// The site is a Next.js App Router export with `trailingSlash: true`
// (v1-e36-t03-site-scaffold), so the page at /parents/faq/ is the object parents/faq/index.html.
// S3's REST endpoint has no notion of a directory index — that behaviour belongs to the S3
// *website* endpoint, which is plain HTTP and cannot be kept private, so ADR-0012 does not use
// it. These few lines are what replaces it.
//
//   /parents/faq/           -> /parents/faq/index.html
//   /parents/faq            -> /parents/faq/index.html
//   /_next/static/a1b2.js   -> unchanged (the last segment has an extension)
//   /                       -> unchanged (default_root_object serves index.html)
//
// Written for the cloudfront-js-2.0 runtime without ES6 string helpers: a syntax error here is
// only reported when the function is published, and a broken viewer-request function takes every
// page down at once.

function handler(event) {
  var request = event.request;
  var uri = request.uri;

  if (uri.charAt(uri.length - 1) === '/') {
    request.uri = uri + 'index.html';
    return request;
  }

  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
  if (lastSegment.indexOf('.') === -1) {
    request.uri = uri + '/index.html';
  }

  return request;
}
