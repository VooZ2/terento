// Umami before-send filter for terento.app and terento.app/install/.
// The same file is in VooZ2/terento site/umami-before-send.js and in
// VooZ2/terento-internal lab/web-installer/public/umami-before-send.js:
// change both together (each repository has the same test vectors).
//
// The Umami tracker calls window.terentoUmamiBeforeSend(type, payload) for
// every send (data-before-send="terentoUmamiBeforeSend"). Page views, events
// and performance metrics pass unchanged. An error report is cleaned before it
// leaves the browser: the tracker already reduces http(s) URLs to origin and
// path and hides e-mail addresses; this also removes local user folders,
// device serial numbers and IDs, e-mail addresses and query strings of any
// other URL. Errors from browser extensions and cross-origin "Script error."
// reports without a stack are dropped. If cleaning fails the report is dropped,
// never sent as it was.
(function (root) {
  "use strict";

  var EXTENSION = /\b(?:chrome|moz|safari-web|safari|ms-browser)-extension:\/\//i;
  var RULES = [
    // Local user folders: /Users/<name>/, /home/<name>/, C:\Users\<name>\ (also
    // C:/Users/<name>/ and file:///Users/<name>/) become ~/.
    [/(^|[^\w.-])(?:[A-Za-z]:)?[\\/](?:Users|home)[\\/][^\\/\s:'"()<>]+(?:[\\/]|(?=[\s:'"()<>]|$))/gi, "$1~/"],
    // E-mail addresses.
    [/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, "[email]"],
    // Query strings of URLs and paths; a stack position (:line:column) stays.
    [/((?:[a-z][a-z0-9+.-]*:\/\/|\/)[^\s?#'"()<>]*)\?[^\s#'"()<>]*?(?=:\d+:\d+(?=[\s)'"]|$)|[\s#'"()<>]|$)/gi, "$1"],
    // A named serial number or ID with its value.
    [/\b(serial(?:[ _-]?(?:number|no))?|s\/n|unit[ _-]?id|device[ _-]?id|imei|esn)\b(\s*[:=#]?\s*)["']?[\w-]{3,}["']?/gi, "$1$2[id]"],
    // Values shaped like IDs: UUIDs, 8+ digits (not a YYYYMMDD date, as in a
    // release name), 12+ hex characters, 8+ capitals with digits (serials).
    [/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "[id]"],
    [/\b(?!20\d\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\b)\d{8,}\b/g, "[id]"],
    [/\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12,}\b/gi, "[id]"],
    [/\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,}\b/g, "[id]"]
  ];

  function clean(value) {
    if (typeof value !== "string") return value;
    var text = value;
    for (var i = 0; i < RULES.length; i += 1) text = text.replace(RULES[i][0], RULES[i][1]);
    return text;
  }

  function cleanError(payload) {
    var message = typeof payload.message === "string" ? payload.message : "";
    var stack = typeof payload.stack === "string" ? payload.stack : "";
    if (EXTENSION.test(stack) || EXTENSION.test(message)) return null;
    if (/^\s*Script error\.?\s*$/i.test(message) && !stack.trim()) return null;
    var result = {};
    for (var key in payload) if (Object.prototype.hasOwnProperty.call(payload, key)) result[key] = payload[key];
    result.name = clean(payload.name);
    result.message = clean(payload.message);
    result.stack = clean(payload.stack);
    if (payload.tags && typeof payload.tags === "object") {
      result.tags = {};
      for (var tag in payload.tags) {
        if (Object.prototype.hasOwnProperty.call(payload.tags, tag)) result.tags[tag] = clean(payload.tags[tag]);
      }
    }
    return result;
  }

  function terentoUmamiBeforeSend(type, payload) {
    if (type !== "error") return payload;
    try {
      return payload && typeof payload === "object" ? cleanError(payload) : null;
    } catch (error) {
      return null;
    }
  }

  terentoUmamiBeforeSend.clean = clean;
  root.terentoUmamiBeforeSend = terentoUmamiBeforeSend;
})(typeof window !== "undefined" ? window : globalThis);
