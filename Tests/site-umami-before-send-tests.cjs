"use strict";

// Self-check of the Umami before-send filter (site/umami-before-send.js).
// The same vectors are in VooZ2/terento-internal
// lab/web-installer/tests/umami-before-send.test.mjs for its copy of the file.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const file = path.resolve(__dirname, "..", "site", "umami-before-send.js");
const window = {};
vm.runInNewContext(fs.readFileSync(file, "utf8"), {window});
const beforeSend = window.terentoUmamiBeforeSend;
assert.equal(typeof beforeSend, "function", "window.terentoUmamiBeforeSend must be defined");
const clean = beforeSend.clean;

const vectors = [
  ["/Users/jonas/Library/Logs/x.log failed", "~/Library/Logs/x.log failed"],
  ["at file:///Users/jonas/Desktop/page.html:3:9", "at file://~/Desktop/page.html:3:9"],
  ["C:\\Users\\Jonas\\Downloads\\map.img not found", "~/Downloads\\map.img not found"],
  ["C:/Users/Jonas/AppData/x.js", "~/AppData/x.js"],
  ["open /home/jonas/maps/a.img", "open ~/maps/a.img"],
  ["https://terento.app/home/x.js", "https://terento.app/home/x.js"],
  ["mail jonas.p+test@example.co.uk now", "mail [email] now"],
  ["GET /download/?utm_source=reddit&utm_campaign=x failed", "GET /download/ failed"],
  ["at blob:https://terento.app/x?id=1:2:3", "at blob:https://terento.app/x:2:3"],
  ["at https://terento.app/map-styles/map-styles.js?v=20261113-map-styles-v16:120:14", "at https://terento.app/map-styles/map-styles.js:120:14"],
  ["Is this a question? Yes.", "Is this a question? Yes."],
  ["serial: 3K1234567 refused", "serial: [id] refused"],
  ["serialNumber=ABC123", "serialNumber=[id]"],
  ["Unit ID 3998765432 busy", "Unit ID [id] busy"],
  ["device_id: 'xy-1234'", "device_id: [id]"],
  ["A stable local device identity is required", "A stable local device identity is required"],
  ["watch 3998765432 stopped", "watch [id] stopped"],
  ["code 12345678 and 20261114-au", "code [id] and 20261114-au"],
  ["job 0b6f2c1e-8d1a-4c55-9b0e-3f7a2d9c1e44 gone", "job [id] gone"],
  ["hash 9f86d081884c7d659a2feaa0c55ad015 differs", "hash [id] differs"],
  ["device 5KE012345 not ready", "device [id] not ready"],
  ["MTP refused operation 0x100c (transaction 12): response 0x201e", "MTP refused operation 0x100c (transaction 12): response 0x201e"],
  ["Reported watch model is not in the current policy: fenix 8 - 47mm", "Reported watch model is not in the current policy: fenix 8 - 47mm"],
  ["TypeError: Cannot read properties of undefined (reading 'info')", "TypeError: Cannot read properties of undefined (reading 'info')"],
  ["at prepare (https://terento.app/install/app.mjs:282:3)", "at prepare (https://terento.app/install/app.mjs:282:3)"],
];
for (const [input, expected] of vectors) assert.equal(clean(input), expected, input);

const error = (fields) => ({
  website: "d8097a98-ffe4-478e-b212-9f06b5bcccbe", name: "Error", handled: true,
  url: "/install/", release: "20261114-au", environment: "production", tags: {}, ...fields,
});

// Error payloads are cleaned; every other field stays.
const cleaned = beforeSend("error", error({
  message: "Could not open /Users/jonas/x.img for jonas@example.com",
  stack: "Error: serial 3K1234567\n    at run (https://terento.app/install/app.mjs:10:2)",
  tags: {step: "write-files", installer: "20261114-au", model: "fenix 8 - 47mm", note: "/home/jonas/a"},
}));
assert.equal(cleaned.message, "Could not open ~/x.img for [email]");
assert.equal(cleaned.stack, "Error: serial [id]\n    at run (https://terento.app/install/app.mjs:10:2)");
assert.deepEqual({...cleaned.tags}, {step: "write-files", installer: "20261114-au", model: "fenix 8 - 47mm", note: "~/a"});
assert.equal(cleaned.website, "d8097a98-ffe4-478e-b212-9f06b5bcccbe");
assert.equal(cleaned.release, "20261114-au");
assert.equal(cleaned.handled, true);

// Browser extension errors and cross-origin "Script error." are dropped.
for (const stack of [
  "Error\n    at chrome-extension://abcdefghijklmnop/content.js:1:2",
  "x@moz-extension://0b6f2c1e/inject.js:3:4",
  "x@safari-web-extension://ABC/script.js:1:1",
]) assert.equal(beforeSend("error", error({message: "boom", stack})), null, stack);
assert.equal(beforeSend("error", error({message: "Script error.", stack: ""})), null);
assert.equal(beforeSend("error", error({message: "Script error", stack: "   "})), null);
assert.notEqual(beforeSend("error", error({message: "Script error.", stack: "at x (https://terento.app/a.js:1:1)"})), null);
assert.equal(beforeSend("error", null), null);

// Page views, events and performance metrics pass unchanged (same object).
for (const type of ["event", "performance", "identify"]) {
  const payload = {url: "/download/?utm_source=x", name: "download-click", data: {email: "a@b.cc"}};
  assert.equal(beforeSend(type, payload), payload, type);
  assert.equal(payload.url, "/download/?utm_source=x");
}

// A failure while cleaning drops the report instead of sending it raw.
const hostile = error({});
Object.defineProperty(hostile, "message", {enumerable: true, get() { throw new Error("no"); }});
assert.equal(beforeSend("error", hostile), null);

console.log(`PASS: Umami before-send filter (${vectors.length} text vectors, error drop rules, pass-through)`);
