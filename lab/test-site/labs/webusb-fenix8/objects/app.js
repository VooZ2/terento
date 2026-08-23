(() => {
  "use strict";

  const GARMIN_VENDOR_ID = 0x091e;
  const MTP_PRODUCT_ID = 0x51b8;
  const EXPECTED_CONFIGURATION = 1;
  const EXPECTED_INTERFACE = 0;
  const BULK_IN = 1;
  const BULK_OUT = 3;
  const STEP_TIMEOUT_MS = 9000;
  const MAX_CONTAINER_LENGTH = 32768;
  const MAX_STREAM_CONTAINER_LENGTH = 0xffffffff;
  const MAX_ARRAY_COUNT = 4096;
  const MAX_OBJECT_HANDLES = 65536;
  const MAX_OBJECT_INFO = 512;
  const MAX_RECURSION_DEPTH = 5;
  const MAX_DISCOVERED_OBJECTS = 500;
  const CONTAINER_COMMAND = 1;
  const CONTAINER_DATA = 2;
  const CONTAINER_RESPONSE = 3;
  const RESPONSE_OK = 0x2001;
  const RESPONSE_SESSION_ALREADY_OPEN = 0x201e;
  const OP_OPEN_SESSION = 0x1002;
  const OP_CLOSE_SESSION = 0x1003;
  const OP_GET_STORAGE_IDS = 0x1004;
  const OP_GET_STORAGE_INFO = 0x1005;
  const OP_GET_OBJECT_HANDLES = 0x1007;
  const OP_GET_OBJECT_INFO = 0x1008;
  const OP_GET_OBJECT = 0x1009;
  const MAP_TARGET_NAMES = ["freizeitkarte-lithuania.img"];
  const ALL_OBJECTS = 0xffffffff;
  const ALL_FORMATS = 0x0000;

  const dom = {
    consent: document.querySelector("#consent"),
    runButton: document.querySelector("#runButton"),
    flowStatus: document.querySelector("#flowStatus"),
    flowMessage: document.querySelector("#flowMessage"),
    runProgress: document.querySelector("#runProgress"),
    runProgressLabel: document.querySelector("#runProgressLabel"),
    runProgressPercent: document.querySelector("#runProgressPercent"),
    runProgressDetail: document.querySelector("#runProgressDetail"),
    runProgressElapsed: document.querySelector("#runProgressElapsed"),
    gateStatus: document.querySelector("#gateStatus"),
    gateMessage: document.querySelector("#gateMessage"),
    errorMessage: document.querySelector("#errorMessage"),
    apiResult: document.querySelector("#apiResult"),
    requestResult: document.querySelector("#requestResult"),
    identityResult: document.querySelector("#identityResult"),
    pidResult: document.querySelector("#pidResult"),
    descriptorResult: document.querySelector("#descriptorResult"),
    configurationResult: document.querySelector("#configurationResult"),
    claimResult: document.querySelector("#claimResult"),
    openSessionResult: document.querySelector("#openSessionResult"),
    storageIdsResult: document.querySelector("#storageIdsResult"),
    storageInfoResult: document.querySelector("#storageInfoResult"),
    objectHandlesResult: document.querySelector("#objectHandlesResult"),
    objectInfoResult: document.querySelector("#objectInfoResult"),
    getObjectResult: document.querySelector("#getObjectResult"),
    closeSessionResult: document.querySelector("#closeSessionResult"),
    releaseResult: document.querySelector("#releaseResult"),
    closeResult: document.querySelector("#closeResult"),
    browserValue: document.querySelector("#browserValue"),
    platformValue: document.querySelector("#platformValue"),
    vendorValue: document.querySelector("#vendorValue"),
    productValue: document.querySelector("#productValue"),
    usbNameValue: document.querySelector("#usbNameValue"),
    usbSerialValue: document.querySelector("#usbSerialValue"),
    configurationValue: document.querySelector("#configurationValue"),
    usbPresenceValue: document.querySelector("#usbPresenceValue"),
    usbModeValue: document.querySelector("#usbModeValue"),
    storageCount: document.querySelector("#storageCount"),
    storageTable: document.querySelector("#storageTable"),
    objectCount: document.querySelector("#objectCount"),
    objectSummary: document.querySelector("#objectSummary"),
    hierarchyTree: document.querySelector("#hierarchyTree"),
    discoveryResult: document.querySelector("#discoveryResult"),
    cycleProgress: document.querySelector("#cycleProgress"),
    mapSummary: document.querySelector("#mapSummary"),
    mapTable: document.querySelector("#mapTable"),
    mapProgress: document.querySelector("#mapProgress"),
    objectTable: document.querySelector("#objectTable"),
    protocolTable: document.querySelector("#protocolTable"),
    downloadReport: document.querySelector("#downloadReport"),
    downloadAnchor: document.querySelector("#downloadAnchor")
  };

  const state = {
    busy: false,
    device: null,
    opened: false,
    claimed: false,
    sessionOpen: false,
    reader: null,
    transactionId: 1,
    current: null,
    runs: [],
    firstProductId: null,
    progressStartedAt: null,
    progressTimer: null,
    mode: document.body?.dataset.stage === "2b1" ? "recursive" : document.body?.dataset.stage === "2c" ? "map-read" : new URLSearchParams(window.location.search).get("method") === "recursive" ? "recursive" : "flat"
  };

  class StopError extends Error {
    constructor(message) {
      super(message);
      this.name = "StoppedSafely";
    }
  }

  class ProtocolError extends Error {
    constructor(message) {
      super(message);
      this.name = "ProtocolError";
    }
  }

  function setText(element, value) {
    if (element) element.textContent = value === null || value === undefined ? "" : String(value);
  }

  function setStatus(element, value) {
    if (!element) return;
    element.textContent = value;
    element.className = "status status--" + String(value).toLowerCase().replaceAll(" ", "-");
  }

  function formatElapsed(milliseconds) {
    const seconds = Math.max(0, Math.floor(milliseconds / 1000));
    const minutes = Math.floor(seconds / 60);
    return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function updateProgress(percent, label, detail = "") {
    const bounded = Math.max(0, Math.min(100, Number(percent) || 0));
    if (dom.runProgress) dom.runProgress.value = bounded;
    setText(dom.runProgressLabel, label);
    setText(dom.runProgressPercent, `${Math.round(bounded)}%`);
    setText(dom.runProgressDetail, detail);
    if (dom.runProgressElapsed && state.progressStartedAt !== null) setText(dom.runProgressElapsed, formatElapsed(performance.now() - state.progressStartedAt));
  }

  function startProgressTimer() {
    state.progressStartedAt = performance.now();
    clearInterval(state.progressTimer);
    state.progressTimer = setInterval(() => {
      if (dom.runProgressElapsed && state.progressStartedAt !== null) setText(dom.runProgressElapsed, formatElapsed(performance.now() - state.progressStartedAt));
    }, 1000);
  }

  function stopProgressTimer() {
    clearInterval(state.progressTimer);
    state.progressTimer = null;
  }

  function markStep(name, value) {
    const map = {
      request: dom.requestResult,
      identity: dom.identityResult,
      pid: dom.pidResult,
      descriptor: dom.descriptorResult,
      configuration: dom.configurationResult,
      claim: dom.claimResult,
      openSession: dom.openSessionResult,
      storageIds: dom.storageIdsResult,
      storageInfo: dom.storageInfoResult,
      objectHandles: dom.objectHandlesResult,
      objectInfo: dom.objectInfoResult,
      getObject: dom.getObjectResult,
      closeSession: dom.closeSessionResult,
      release: dom.releaseResult,
      close: dom.closeResult
    };
    if (state.current) state.current.steps[name] = value;
    setStatus(map[name], value);
  }

  function hexValue(value, width = 4) {
    return Number.isFinite(value) ? `0x${value.toString(16).padStart(width, "0")}` : "UNKNOWN";
  }

  function decimalHex(value, width = 4) {
    return Number.isFinite(value) ? `${value} / ${hexValue(value, width)}` : "UNKNOWN";
  }

  function safeError(error) {
    return { name: error?.name || "Error", message: error?.message || String(error) };
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function withTimeout(promise, label, timeout = STEP_TIMEOUT_MS) {
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new ProtocolError(`${label} timed out.`)), timeout);
    });
    return Promise.race([Promise.resolve(promise), deadline]).finally(() => clearTimeout(timer));
  }

  function identityFromDevice(device) {
    return {
      vendorId: Number.isFinite(device.vendorId) ? device.vendorId : null,
      vendorIdHex: hexValue(device.vendorId),
      productId: Number.isFinite(device.productId) ? device.productId : null,
      productIdHex: hexValue(device.productId),
      manufacturerName: device.manufacturerName || "",
      productName: device.productName || "",
      serialNumberPresent: Boolean(device.serialNumber)
    };
  }

  function captureTopology(device) {
    return [...(device.configurations || [])].map(configuration => ({
      configurationValue: configuration.configurationValue,
      interfaces: [...(configuration.interfaces || [])].map(iface => ({
        interfaceNumber: iface.interfaceNumber,
        alternates: [...(iface.alternates || [])].map(alternate => ({
          alternateSetting: alternate.alternateSetting,
          interfaceClass: alternate.interfaceClass,
          interfaceSubclass: alternate.interfaceSubclass,
          interfaceProtocol: alternate.interfaceProtocol,
          endpoints: [...(alternate.endpoints || [])].map(endpoint => ({
            endpointNumber: endpoint.endpointNumber,
            direction: endpoint.direction,
            type: endpoint.type,
            packetSize: endpoint.packetSize
          }))
        }))
      }))
    }));
  }

  function descriptorCheck(topology) {
    if (topology.length !== 1 || topology[0].configurationValue !== EXPECTED_CONFIGURATION) return { ok: false, reason: "Expected exactly configuration 1." };
    const interfaces = topology[0].interfaces;
    if (interfaces.length !== 1 || interfaces[0].interfaceNumber !== EXPECTED_INTERFACE) return { ok: false, reason: "Expected exactly interface 0." };
    const alternates = interfaces[0].alternates;
    if (alternates.length !== 1 || alternates[0].alternateSetting !== 0) return { ok: false, reason: "Expected exactly alternate setting 0." };
    const alternate = alternates[0];
    if (alternate.interfaceClass !== 0xff || alternate.interfaceSubclass !== 0xff || alternate.interfaceProtocol !== 0x00) return { ok: false, reason: "Expected the observed fēnix 8 MTP class tuple 0xff / 0xff / 0x00." };
    const expected = [[1, "in", "bulk", 512], [2, "in", "interrupt", 64], [3, "out", "bulk", 512]];
    const actual = alternate.endpoints;
    const same = actual.length === expected.length && expected.every(item => actual.some(endpoint => endpoint.endpointNumber === item[0] && endpoint.direction === item[1] && endpoint.type === item[2] && endpoint.packetSize === item[3]));
    return same ? { ok: true, reason: "Observed the fēnix 8 MTP descriptor target." } : { ok: false, reason: "Expected bulk IN 1, interrupt IN 2 and bulk OUT 3." };
  }

  function buildCommand(code, transactionId, parameters = []) {
    const bytes = new Uint8Array(12 + parameters.length * 4);
    const view = new DataView(bytes.buffer);
    view.setUint32(0, bytes.length, true);
    view.setUint16(4, CONTAINER_COMMAND, true);
    view.setUint16(6, code, true);
    view.setUint32(8, transactionId, true);
    parameters.forEach((parameter, index) => view.setUint32(12 + index * 4, parameter >>> 0, true));
    return bytes;
  }

  function parseContainer(bytes) {
    if (bytes.length < 12) throw new ProtocolError("Container is shorter than the 12-byte header.");
    const header = parseContainerHeader(bytes);
    const length = header.length;
    if (length < 12 || length > MAX_CONTAINER_LENGTH || length !== bytes.length) throw new ProtocolError("Container length is invalid.");
    return { ...header, payload: bytes.slice(12) };
  }

  function parseContainerHeader(bytes, allowLarge = false) {
    if (bytes.length < 12) throw new ProtocolError("Container header is shorter than 12 bytes.");
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const length = view.getUint32(0, true);
    const maximum = allowLarge ? MAX_STREAM_CONTAINER_LENGTH : MAX_CONTAINER_LENGTH;
    if (length < 12 || length > maximum) throw new ProtocolError("Container length is outside the safe bound.");
    return { length, type: view.getUint16(4, true), code: view.getUint16(6, true), transactionId: view.getUint32(8, true) };
  }

  function makeReader(device) {
    let pending = new Uint8Array(0);
    let emptyBulkInTransfers = 0;
    async function pull(deadline) {
      const remaining = Math.max(100, deadline - performance.now());
      const transfer = await withTimeout(device.transferIn(BULK_IN, 512), "Bulk IN transfer", remaining);
      if (transfer.status && transfer.status !== "ok") throw new ProtocolError(`Bulk IN status: ${transfer.status}.`);
      if (!transfer.data) throw new ProtocolError("Bulk IN returned no data view.");
      if (transfer.data.byteLength === 0) {
        emptyBulkInTransfers += 1;
        return false;
      }
      const incoming = new Uint8Array(transfer.data.buffer, transfer.data.byteOffset, transfer.data.byteLength);
      const joined = new Uint8Array(pending.length + incoming.length);
      joined.set(pending);
      joined.set(incoming, pending.length);
      pending = joined;
      return true;
    }
    return {
      async readBytes(count, deadline = performance.now() + STEP_TIMEOUT_MS) {
        if (!Number.isInteger(count) || count < 0) throw new ProtocolError("Requested byte count is invalid.");
        while (pending.length < count) await pull(deadline);
        const bytes = pending.slice(0, count);
        pending = pending.slice(count);
        return bytes;
      },
      async readAvailable(deadline = performance.now() + STEP_TIMEOUT_MS) {
        while (pending.length === 0) await pull(deadline);
        const bytes = pending;
        pending = new Uint8Array(0);
        return bytes;
      },
      async readSome(maxCount, deadline = performance.now() + STEP_TIMEOUT_MS) {
        if (!Number.isInteger(maxCount) || maxCount <= 0) throw new ProtocolError("Requested chunk size is invalid.");
        while (pending.length === 0) await pull(deadline);
        const count = Math.min(maxCount, pending.length);
        const bytes = pending.slice(0, count);
        pending = pending.slice(count);
        return bytes;
      },
      getStats() {
        return { emptyBulkInTransfers };
      },
      async nextHeader(allowLarge = false) {
        const headerBytes = await this.readBytes(12);
        return parseContainerHeader(headerBytes, allowLarge);
      },
      async next() {
        const deadline = performance.now() + STEP_TIMEOUT_MS;
        const headerBytes = await this.readBytes(12, deadline);
        const header = parseContainerHeader(headerBytes);
        const payload = await this.readBytes(header.length - 12, deadline);
        const bytes = new Uint8Array(header.length);
        bytes.set(headerBytes);
        bytes.set(payload, 12);
        return parseContainer(bytes);
      }
    };
  }

  function cursorFor(bytes) {
    let offset = 0;
    function take(count, label) {
      if (!Number.isInteger(count) || count < 0 || offset + count > bytes.length) throw new ProtocolError(`Malformed ${label} dataset.`);
      const part = bytes.slice(offset, offset + count);
      offset += count;
      return part;
    }
    function u16(label) {
      const part = take(2, label);
      return new DataView(part.buffer, part.byteOffset, 2).getUint16(0, true);
    }
    function u32(label) {
      const part = take(4, label);
      return new DataView(part.buffer, part.byteOffset, 4).getUint32(0, true);
    }
    function text(label) {
      const count = take(1, label)[0];
      if (count === 0) return "";
      const raw = take(count * 2, label);
      return new TextDecoder("utf-16le").decode(raw.subarray(0, (count - 1) * 2)).replace(/\u0000+$/g, "");
    }
    return { u16, u32, text, remaining: () => bytes.length - offset };
  }

  const SHA256_K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ]);

  class StreamingSha256 {
    constructor() {
      this.state = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
      this.buffer = new Uint8Array(64);
      this.bufferLength = 0;
      this.totalBytes = 0n;
    }

    transform(bytes, offset = 0) {
      const words = new Uint32Array(64);
      for (let index = 0; index < 16; index += 1) {
        const position = offset + index * 4;
        words[index] = ((bytes[position] << 24) | (bytes[position + 1] << 16) | (bytes[position + 2] << 8) | bytes[position + 3]) >>> 0;
      }
      for (let index = 16; index < 64; index += 1) {
        const value = words[index - 15];
        const gamma0 = ((value >>> 7) | (value << 25)) ^ ((value >>> 18) | (value << 14)) ^ (value >>> 3);
        const previous = words[index - 2];
        const gamma1 = ((previous >>> 17) | (previous << 15)) ^ ((previous >>> 19) | (previous << 13)) ^ (previous >>> 10);
        words[index] = (words[index - 16] + gamma0 + words[index - 7] + gamma1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = this.state;
      for (let index = 0; index < 64; index += 1) {
        const sigma1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        const choose = (e & f) ^ (~e & g);
        const temp1 = (h + sigma1 + choose + SHA256_K[index] + words[index]) >>> 0;
        const sigma0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        const majority = (a & b) ^ (a & c) ^ (b & c);
        const temp2 = (sigma0 + majority) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + temp1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (temp1 + temp2) >>> 0;
      }
      this.state[0] = (this.state[0] + a) >>> 0;
      this.state[1] = (this.state[1] + b) >>> 0;
      this.state[2] = (this.state[2] + c) >>> 0;
      this.state[3] = (this.state[3] + d) >>> 0;
      this.state[4] = (this.state[4] + e) >>> 0;
      this.state[5] = (this.state[5] + f) >>> 0;
      this.state[6] = (this.state[6] + g) >>> 0;
      this.state[7] = (this.state[7] + h) >>> 0;
    }

    update(bytes) {
      if (!bytes || bytes.length === 0) return;
      this.totalBytes += BigInt(bytes.length);
      let offset = 0;
      if (this.bufferLength > 0) {
        const needed = 64 - this.bufferLength;
        const take = Math.min(needed, bytes.length);
        this.buffer.set(bytes.subarray(0, take), this.bufferLength);
        this.bufferLength += take;
        offset += take;
        if (this.bufferLength === 64) {
          this.transform(this.buffer);
          this.bufferLength = 0;
        }
      }
      while (offset + 64 <= bytes.length) {
        this.transform(bytes, offset);
        offset += 64;
      }
      if (offset < bytes.length) {
        this.buffer.set(bytes.subarray(offset), 0);
        this.bufferLength = bytes.length - offset;
      }
    }

    digestHex() {
      const padded = new Uint8Array(this.bufferLength < 56 ? 64 : 128);
      padded.set(this.buffer.subarray(0, this.bufferLength));
      padded[this.bufferLength] = 0x80;
      const bitLength = this.totalBytes * 8n;
      for (let index = 0; index < 8; index += 1) padded[padded.length - 1 - index] = Number((bitLength >> BigInt(index * 8)) & 0xffn);
      for (let offset = 0; offset < padded.length; offset += 64) this.transform(padded, offset);
      return [...this.state].map(word => word.toString(16).padStart(8, "0")).join("");
    }
  }

  function parseStorageIds(payload) {
    const cursor = cursorFor(payload);
    const count = cursor.u32("storage count");
    if (count > MAX_ARRAY_COUNT || count > Math.floor((payload.length - 4) / 4)) throw new ProtocolError("Storage count is outside the safe bound.");
    return Array.from({ length: count }, () => cursor.u32("storage ID"));
  }

  function parseStorageInfo(payload, storageId) {
    const cursor = cursorFor(payload);
    return {
      storageId,
      storageType: cursor.u16("storage type"),
      filesystemType: cursor.u16("filesystem type"),
      accessCapability: cursor.u16("access capability"),
      maxCapacity: String(BigInt(cursor.u32("capacity low")) + (BigInt(cursor.u32("capacity high")) << 32n)),
      freeSpaceInBytes: String(BigInt(cursor.u32("free space low")) + (BigInt(cursor.u32("free space high")) << 32n)),
      freeSpaceInObjects: cursor.u32("free objects"),
      storageDescription: cursor.text("storage description"),
      volumeLabel: cursor.text("volume label"),
      trailingBytes: cursor.remaining()
    };
  }

  function parseObjectHandles(payload) {
    const cursor = cursorFor(payload);
    const count = cursor.u32("object handle count");
    if (count > MAX_OBJECT_HANDLES || count > Math.floor((payload.length - 4) / 4)) throw new ProtocolError("Object handle count is outside the safe bound.");
    return Array.from({ length: count }, () => cursor.u32("object handle"));
  }

  function parseObjectInfo(payload, handle) {
    const cursor = cursorFor(payload);
    return {
      handle,
      storageId: cursor.u32("object storage ID"),
      objectFormat: cursor.u16("object format"),
      protectionStatus: cursor.u16("protection status"),
      size: String(cursor.u32("object size")),
      thumbFormat: cursor.u16("thumbnail format"),
      thumbSize: cursor.u32("thumbnail size"),
      thumbWidth: cursor.u32("thumbnail width"),
      thumbHeight: cursor.u32("thumbnail height"),
      imageWidth: cursor.u32("image width"),
      imageHeight: cursor.u32("image height"),
      imageBitDepth: cursor.u32("image bit depth"),
      parentId: cursor.u32("parent object ID"),
      associationType: cursor.u16("association type"),
      associationDescription: cursor.u32("association description"),
      sequenceNumber: cursor.u32("sequence number"),
      filename: cursor.text("filename"),
      captureDate: cursor.text("capture date"),
      modificationDate: cursor.text("modification date"),
      keywords: cursor.text("keywords"),
      trailingBytes: cursor.remaining()
    };
  }

  function objectFormatLabel(format) {
    const labels = { 0x3000: "Undefined", 0x3001: "Association", 0x3002: "Script", 0x3004: "Executable", 0x3801: "JPEG" };
    return `${labels[format] || "Unknown"} (${hexValue(format)})`;
  }

  function associationFileType(object) {
    return object.objectFormat === 0x3001 ? "Association" : "File/object";
  }

  function enrichObject(object, depth, requestedParent) {
    return {
      ...object,
      depth,
      requestedParent,
      associationFileType: associationFileType(object)
    };
  }

  function objectSignal(object) {
    const filename = object.filename || "";
    if (/\.img$/i.test(filename)) return "IMG filename";
    if (/(garmin|map|gmap|gmapp)/i.test(filename)) return "Map/Garmin name match";
    if (object.objectFormat === 0x3001) return "Association object";
    return "Observed; no map match";
  }

  function renderProtocol() {
    const operations = state.current?.protocol?.operations || [];
    dom.protocolTable.innerHTML = operations.length ? operations.map(operation => `<tr><td>${escapeHtml(operation.name)}</td><td>${escapeHtml(decimalHex(operation.code))}</td><td>${escapeHtml(operation.transactionId)}</td><td>${escapeHtml(operation.dataBytes)}</td><td>${escapeHtml(decimalHex(operation.responseCode))}</td><td>${escapeHtml(operation.responseCode === RESPONSE_OK ? "OK" : "NOT OK")}</td></tr>`).join("") : '<tr><td colspan="6" class="empty">No protocol transaction yet.</td></tr>';
  }

  function renderStorage(storage) {
    setStatus(dom.storageCount, storage ? `${storage.length} STORAGE${storage.length === 1 ? "" : "S"}` : "NOT RUN");
    dom.storageTable.innerHTML = storage?.length ? storage.map(item => `<tr><td>${escapeHtml(decimalHex(item.storageId, 8))}</td><td>${escapeHtml(item.storageDescription || "EMPTY")}</td><td>${escapeHtml(item.maxCapacity)}</td><td>${escapeHtml(item.freeSpaceInBytes)}</td><td>${escapeHtml(decimalHex(item.accessCapability))}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">No storage metadata returned.</td></tr>';
  }

  function renderObjects(objects, totalHandles, selectedCount, truncated) {
    const mapMatches = objects.filter(object => objectSignal(object) !== "Observed; no map match");
    setStatus(dom.objectCount, `${totalHandles} HANDLE${totalHandles === 1 ? "" : "S"}`);
    if (state.mode === "recursive") {
      const associations = objects.filter(object => object.objectFormat === 0x3001).length;
      const maxDepth = objects.reduce((maximum, object) => Math.max(maximum, object.depth || 0), 0);
      setText(dom.objectSummary, `${totalHandles} handle${totalHandles === 1 ? "" : "s"} discovered; ${selectedCount} object-info record${selectedCount === 1 ? "" : "s"} read; ${associations} association${associations === 1 ? "" : "s"}; deepest observed level ${maxDepth}.${truncated ? " A safety limit stopped the traversal." : " Every reachable level within the depth limit was checked."}`);
      dom.objectTable.innerHTML = objects.length ? objects.map(object => `<tr><td>${escapeHtml(decimalHex(object.handle, 8))}</td><td>${escapeHtml(object.depth)}</td><td>${escapeHtml(decimalHex(object.parentId, 8))}</td><td>${escapeHtml(objectFormatLabel(object.objectFormat))}</td><td>${escapeHtml(object.filename || "EMPTY")}</td><td>${escapeHtml(object.size)}</td><td>${escapeHtml(object.associationFileType)}</td><td>${escapeHtml(objectSignal(object))}</td></tr>`).join("") : '<tr><td colspan="8" class="empty">No object metadata returned.</td></tr>';
      renderHierarchy(objects);
      return;
    }
    setText(dom.objectSummary, `${totalHandles} handle${totalHandles === 1 ? "" : "s"} returned; ${selectedCount} object-info record${selectedCount === 1 ? "" : "s"} read; ${mapMatches.length} transparent filename/format match${mapMatches.length === 1 ? "" : "es"}.${truncated ? " Metadata scan was bounded; enumeration is incomplete." : " Metadata scan covered every returned handle."}`);
    dom.objectTable.innerHTML = objects.length ? objects.map(object => `<tr><td>${escapeHtml(decimalHex(object.handle, 8))}</td><td>${escapeHtml(decimalHex(object.storageId, 8))}</td><td>${escapeHtml(objectFormatLabel(object.objectFormat))}</td><td>${escapeHtml(object.filename || "EMPTY")}</td><td>${escapeHtml(object.size)}</td><td>${escapeHtml(decimalHex(object.parentId, 8))}</td><td>${escapeHtml(objectSignal(object))}</td></tr>`).join("") : '<tr><td colspan="7" class="empty">No object metadata returned.</td></tr>';
  }

  function renderHierarchy(objects) {
    if (!dom.hierarchyTree) return;
    const children = new Map();
    objects.forEach(object => {
      const parent = Number.isFinite(object.parentId) ? object.parentId : 0;
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(object);
    });
    for (const list of children.values()) list.sort((left, right) => (left.filename || "").localeCompare(right.filename || "") || left.handle - right.handle);
    const lines = ["/"];
    const visited = new Set();
    function walk(parent, prefix) {
      const list = children.get(parent) || [];
      list.forEach((object, index) => {
        const last = index === list.length - 1;
        const name = object.filename || "(unnamed)";
        lines.push(`${prefix}${last ? "└── " : "├── "}${name} [${hexValue(object.handle, 8)} · ${objectFormatLabel(object.objectFormat)}]`);
        if (visited.has(object.handle)) {
          lines.push(`${prefix}${last ? "    " : "│   "}└── (cycle suppressed)`);
          return;
        }
        visited.add(object.handle);
        if (object.objectFormat === 0x3001) walk(object.handle, prefix + (last ? "    " : "│   "));
      });
    }
    walk(0, "");
    dom.hierarchyTree.textContent = lines.join("\n");
  }

  function resetPanel() {
    ["requestResult", "identityResult", "pidResult", "descriptorResult", "configurationResult", "claimResult", "openSessionResult", "storageIdsResult", "storageInfoResult", "objectHandlesResult", "objectInfoResult", "getObjectResult", "closeSessionResult", "releaseResult", "closeResult"].forEach(key => setStatus(dom[key], "NOT RUN"));
    setStatus(dom.flowStatus, "RUNNING");
    setStatus(dom.gateStatus, "NOT RUN");
    if (dom.gateMessage) dom.gateMessage.hidden = true;
    if (dom.errorMessage) dom.errorMessage.hidden = true;
    if (dom.protocolTable) dom.protocolTable.innerHTML = '<tr><td colspan="6" class="empty">No protocol transaction yet.</td></tr>';
    if (dom.storageTable) dom.storageTable.innerHTML = '<tr><td colspan="5" class="empty">No storage metadata yet.</td></tr>';
    if (dom.objectTable) dom.objectTable.innerHTML = `<tr><td colspan="${state.mode === "recursive" ? "8" : "7"}" class="empty">No object metadata yet.</td></tr>`;
    if (dom.hierarchyTree) setText(dom.hierarchyTree, "/\n(no object metadata yet)");
    if (dom.mapTable) dom.mapTable.innerHTML = '<tr><td colspan="8" class="empty">No map object read yet.</td></tr>';
    if (dom.mapSummary) setText(dom.mapSummary, "No map object read yet.");
    if (dom.mapProgress) setText(dom.mapProgress, "No transfer started.");
    setStatus(dom.storageCount, "NOT RUN");
    setStatus(dom.objectCount, "NOT RUN");
    setText(dom.objectSummary, "No object scan yet.");
    updateProgress(0, "Waiting to start", "The device has not been queried yet.");
  }

  function recordOperation(name, code, transactionId, dataBytes, responseCode) {
    const operation = { name, code, codeHex: hexValue(code), transactionId, dataBytes, responseCode, responseCodeHex: hexValue(responseCode) };
    state.current.protocol.operations.push(operation);
    renderProtocol();
    return operation;
  }

  async function protocolOperation(name, code, parameters, expectsData, options = {}) {
    const transactionId = state.transactionId++;
    const transferOut = await withTimeout(state.device.transferOut(BULK_OUT, buildCommand(code, transactionId, parameters)), `${name} bulk OUT`);
    if (transferOut.status && transferOut.status !== "ok") throw new ProtocolError(`${name} bulk OUT status: ${transferOut.status}.`);
    let dataContainer = null;
    let responseContainer = null;
    for (let index = 0; index < 4; index += 1) {
      const container = await state.reader.next();
      if (container.transactionId !== transactionId) throw new ProtocolError(`${name} returned an unexpected transaction ID.`);
      if (container.type === CONTAINER_DATA) {
        if (!expectsData || container.code !== code || dataContainer) throw new ProtocolError(`${name} returned an unexpected data container.`);
        dataContainer = container;
      } else if (container.type === CONTAINER_RESPONSE) {
        responseContainer = container;
        break;
      } else {
        throw new ProtocolError(`${name} returned an unexpected container type.`);
      }
    }
    if (!responseContainer) throw new ProtocolError(`${name} returned no response container.`);
    const operation = recordOperation(name, code, transactionId, dataContainer ? dataContainer.payload.length : 0, responseContainer.code);
    if (responseContainer.code !== RESPONSE_OK) {
      if (options.allowSessionAlreadyOpen && name === "OpenSession" && responseContainer.code === RESPONSE_SESSION_ALREADY_OPEN) {
        return { payload: new Uint8Array(0), operation, sessionAlreadyOpen: true };
      }
      throw new StopError(`${name} response code ${hexValue(responseContainer.code)} is not success.`);
    }
    if (expectsData && !dataContainer) throw new ProtocolError(`${name} returned no data container.`);
    return { payload: dataContainer ? dataContainer.payload : new Uint8Array(0), operation };
  }

  function formatBytes(value) {
    const bytes = typeof value === "bigint" ? Number(value) : Number(value);
    if (!Number.isFinite(bytes)) return "UNKNOWN";
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let scaled = bytes;
    let unit = -1;
    while (scaled >= 1024 && unit < units.length - 1) {
      scaled /= 1024;
      unit += 1;
    }
    return `${scaled.toFixed(scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2)} ${units[unit]}`;
  }

  function formatSpeed(bytes, durationMs) {
    const seconds = durationMs / 1000;
    if (!Number.isFinite(seconds) || seconds <= 0) return "UNKNOWN";
    return `${formatBytes(Number(bytes) / seconds)}/s`;
  }

  async function getObjectStream(object, mapIndex, totalMaps, readTelemetry) {
    const transactionId = state.transactionId++;
    const expectedBytes = BigInt(object.size);
    const startedAt = performance.now();
    const hash = new StreamingSha256();
    const emptyTransfersBefore = state.reader.getStats().emptyBulkInTransfers;
    if (readTelemetry) {
      readTelemetry.expectedBytes = expectedBytes.toString();
      readTelemetry.chunkSize = 512;
    }
    const baseProgress = 60 + ((mapIndex - 1) / totalMaps) * 40;
    updateProgress(baseProgress, `Preparing ${object.filename}`, `Map test ${mapIndex} of ${totalMaps} · requesting GetObject.`);
    const transferOut = await withTimeout(state.device.transferOut(BULK_OUT, buildCommand(OP_GET_OBJECT, transactionId, [object.handle])), `GetObject ${object.filename} bulk OUT`);
    if (transferOut.status && transferOut.status !== "ok") throw new ProtocolError(`GetObject ${object.filename} bulk OUT status: ${transferOut.status}.`);
    const dataHeader = await state.reader.nextHeader(true);
    if (dataHeader.transactionId !== transactionId) throw new ProtocolError(`GetObject ${object.filename} returned an unexpected transaction ID.`);
    if (dataHeader.type === CONTAINER_RESPONSE) {
      recordOperation("GetObject", OP_GET_OBJECT, transactionId, "0", dataHeader.code);
      throw new StopError(`GetObject ${object.filename} response code ${hexValue(dataHeader.code)} is not success.`);
    }
    if (dataHeader.type !== CONTAINER_DATA || dataHeader.code !== OP_GET_OBJECT) throw new ProtocolError(`GetObject ${object.filename} returned an unexpected data container.`);
    let remaining = dataHeader.length - 12;
    let receivedBytes = 0n;
    let lastProgressAt = 0;
    while (remaining > 0) {
      const chunk = await state.reader.readSome(Math.min(512, remaining));
      if (chunk.length === 0 || chunk.length > remaining) throw new ProtocolError(`GetObject ${object.filename} returned an invalid data chunk.`);
      hash.update(chunk);
      remaining -= chunk.length;
      receivedBytes += BigInt(chunk.length);
      const now = performance.now();
      if (readTelemetry) {
        readTelemetry.receivedBytes = receivedBytes.toString();
        readTelemetry.transferDurationMs = Math.round(now - startedAt);
        readTelemetry.averageSpeedBytesPerSecond = Math.round(Number(receivedBytes) / Math.max((now - startedAt) / 1000, 0.001));
        readTelemetry.averageSpeed = formatSpeed(receivedBytes, now - startedAt);
        readTelemetry.emptyBulkInTransfers = state.reader.getStats().emptyBulkInTransfers - emptyTransfersBefore;
      }
      if (dom.mapProgress && (now - lastProgressAt > 250 || remaining === 0)) {
        lastProgressAt = now;
        const elapsed = now - startedAt;
        setText(dom.mapProgress, `Test ${mapIndex} / ${totalMaps}: ${object.filename} · ${formatBytes(receivedBytes)} / ${formatBytes(expectedBytes)} · ${formatSpeed(receivedBytes, elapsed)}`);
        const fraction = Number(expectedBytes) > 0 ? Number(receivedBytes) / Number(expectedBytes) : 0;
        updateProgress(baseProgress + (fraction * 40 / totalMaps), `Reading ${object.filename}`, `Map test ${mapIndex} of ${totalMaps} · ${formatBytes(receivedBytes)} / ${formatBytes(expectedBytes)} · ${formatSpeed(receivedBytes, elapsed)}.`);
      }
    }
    const response = await state.reader.next();
    if (response.transactionId !== transactionId || response.type !== CONTAINER_RESPONSE) throw new ProtocolError(`GetObject ${object.filename} returned an invalid response container.`);
    const durationMs = performance.now() - startedAt;
    const operation = recordOperation("GetObject", OP_GET_OBJECT, transactionId, receivedBytes.toString(), response.code);
    if (response.code !== RESPONSE_OK) throw new StopError(`GetObject ${object.filename} response code ${hexValue(response.code)} is not success.`);
    if (receivedBytes !== expectedBytes) throw new ProtocolError(`GetObject ${object.filename} size mismatch: expected ${expectedBytes} bytes, received ${receivedBytes} bytes.`);
    return {
      handle: object.handle,
      name: object.filename,
      expectedBytes: expectedBytes.toString(),
      receivedBytes: receivedBytes.toString(),
      sha256: hash.digestHex(),
      transferDurationMs: Math.round(durationMs),
      averageSpeedBytesPerSecond: Math.round(Number(receivedBytes) / Math.max(durationMs / 1000, 0.001)),
      averageSpeed: formatSpeed(receivedBytes, durationMs),
      chunkSize: 512,
      emptyBulkInTransfers: state.reader.getStats().emptyBulkInTransfers - emptyTransfersBefore,
      responseCode: response.code,
      responseCodeHex: hexValue(response.code),
      operation: operation.name
    };
  }

  async function refreshPresence() {
    const devices = navigator.usb?.getDevices ? await navigator.usb.getDevices() : [];
    const garmins = devices.filter(device => device.vendorId === GARMIN_VENDOR_ID);
    setText(dom.usbPresenceValue, garmins.length ? `${garmins.length} permitted · ${garmins.map(device => hexValue(device.productId)).join(", ")}` : "NO PERMITTED DEVICE");
    const mtp = garmins.find(device => device.productId === MTP_PRODUCT_ID);
    setText(dom.usbModeValue, mtp ? `MTP (${hexValue(MTP_PRODUCT_ID)})${mtp.opened ? " · held by this page" : ""}` : garmins.length ? `NON-MTP (${hexValue(garmins[0].productId)})` : "NONE");
    return devices;
  }

  async function selectConfiguration() {
    const selected = state.device.configuration?.configurationValue;
    if (selected !== EXPECTED_CONFIGURATION) await withTimeout(state.device.selectConfiguration(EXPECTED_CONFIGURATION), "Selecting configuration 1");
    const after = state.device.configuration?.configurationValue;
    state.current.selectedConfiguration = Number.isFinite(after) ? after : null;
    setText(dom.configurationValue, after === null || after === undefined ? "UNKNOWN" : decimalHex(after, 2));
    if (after !== EXPECTED_CONFIGURATION) throw new StopError("Configuration 1 could not be confirmed after selection.");
    markStep("configuration", "PASS");
  }

  function selectObjectHandles(handles) {
    if (handles.length <= MAX_OBJECT_INFO) return { selected: handles, truncated: false };
    const half = Math.floor(MAX_OBJECT_INFO / 2);
    return { selected: [...handles.slice(0, half), ...handles.slice(-half)], truncated: true };
  }

  function renderMapReads(reads) {
    if (!dom.mapTable) return;
    dom.mapTable.innerHTML = reads.length ? reads.map(read => `<tr><td>${escapeHtml(read.name)}</td><td>${escapeHtml(read.handle ? decimalHex(read.handle, 8) : "UNKNOWN")}</td><td>${escapeHtml(read.expectedBytes || "UNKNOWN")}</td><td>${escapeHtml(read.receivedBytes || "—")}</td><td>${escapeHtml(read.sha256 || "—")}</td><td>${escapeHtml(read.transferDurationMs === undefined ? "—" : `${read.transferDurationMs} ms`)}</td><td>${escapeHtml(read.averageSpeed || "—")}</td><td><span class="status status--${String(read.status || "NOT RUN").toLowerCase().replaceAll(" ", "-")}">${escapeHtml(read.status || "NOT RUN")}</span></td></tr>`).join("") : '<tr><td colspan="8" class="empty">No map object read yet.</td></tr>';
    const passed = reads.filter(read => read.status === "PASS").length;
    setText(dom.mapSummary, `${passed} / ${reads.length} selected map object${reads.length === 1 ? "" : "s"} read. Data was streamed in 512-byte chunks and hashed incrementally; no binary content was saved locally.`);
  }

  async function inspectAndDiscoverMap() {
    updateProgress(2, "Checking WebUSB access", "Looking for an already permitted Garmin MTP device.");
    await refreshPresence();
    const existing = (await navigator.usb.getDevices()).find(device => device.vendorId === GARMIN_VENDOR_ID && device.productId === MTP_PRODUCT_ID);
    let device = existing || null;
    if (!device) {
      try {
        device = await navigator.usb.requestDevice({ filters: [{ vendorId: GARMIN_VENDOR_ID, productId: MTP_PRODUCT_ID }] });
      } catch (error) {
        if (error?.name === "NotFoundError") throw new StopError("No MTP device was selected.");
        throw error;
      }
    }
    state.device = device;
    const identity = identityFromDevice(device);
    state.current.identity = identity;
    setText(dom.vendorValue, decimalHex(identity.vendorId));
    setText(dom.productValue, decimalHex(identity.productId));
    setText(dom.usbNameValue, `${identity.manufacturerName || "UNKNOWN"} / ${identity.productName || "UNKNOWN"}`);
    setText(dom.usbSerialValue, identity.serialNumberPresent ? "YES" : "NO");
    markStep("request", "PASS");
    updateProgress(6, "USB device selected", `${identity.vendorIdHex} / ${identity.productIdHex} · verifying the expected Garmin target.`);
    if (identity.vendorId !== GARMIN_VENDOR_ID) throw new StopError("NON-GARMIN — DENIED.");
    markStep("identity", "PASS");
    if (identity.productId !== MTP_PRODUCT_ID) throw new StopError(`USB product ${hexValue(identity.productId)} is not the MTP target ${hexValue(MTP_PRODUCT_ID)}.`);
    if (state.firstProductId === null) state.firstProductId = identity.productId;
    if (state.firstProductId !== identity.productId) throw new StopError(`USB product ID changed: ${hexValue(state.firstProductId)} → ${hexValue(identity.productId)}.`);
    markStep("pid", "PASS");
    await withTimeout(device.open(), "Opening the USB device");
    state.opened = true;
    state.current.topology = captureTopology(device);
    const descriptor = descriptorCheck(state.current.topology);
    if (!descriptor.ok) throw new StopError(descriptor.reason);
    markStep("descriptor", "PASS");
    updateProgress(12, "USB descriptor verified", "Configuration 1, interface 0 and the observed MTP endpoints match.");
    await selectConfiguration();
    await withTimeout(device.claimInterface(EXPECTED_INTERFACE), "Claiming interface 0");
    state.claimed = true;
    markStep("claim", "PASS");
    updateProgress(18, "Interface 0 claimed", "Opening the read-only MTP session.");
    state.reader = makeReader(device);
    await protocolOperation("OpenSession", OP_OPEN_SESSION, [1], false);
    state.sessionOpen = true;
    markStep("openSession", "PASS");
    updateProgress(24, "MTP session open", "Reading the device storage list.");
    const storageIdsResult = await protocolOperation("GetStorageIDs", OP_GET_STORAGE_IDS, [], true);
    const storageIds = parseStorageIds(storageIdsResult.payload);
    state.current.protocol.storageIds = storageIds;
    markStep("storageIds", "PASS");
    if (storageIds.length !== 1 || storageIds[0] !== 0x00020001) throw new StopError("The expected Garmin internal storage 0x00020001 was not exposed.");
    const storageResult = await protocolOperation("GetStorageInfo", OP_GET_STORAGE_INFO, [storageIds[0]], true);
    const storage = parseStorageInfo(storageResult.payload, storageIds[0]);
    state.current.storage = [storage];
    state.current.protocol.storage = [storage];
    renderStorage([storage]);
    markStep("storageInfo", "PASS");
    updateProgress(32, "Storage confirmed", `Using storage ${hexValue(storageIds[0], 8)} · discovering the GARMIN association.`);

    const rootHandlesResult = await protocolOperation("GetObjectHandles", OP_GET_OBJECT_HANDLES, [storageIds[0], ALL_FORMATS, ALL_OBJECTS], true);
    const rootHandles = parseObjectHandles(rootHandlesResult.payload);
    updateProgress(38, "Reading storage root", `${rootHandles.length} root object handle${rootHandles.length === 1 ? "" : "s"} returned.`);
    const rootObjects = [];
    for (let index = 0; index < rootHandles.length; index += 1) {
      const handle = rootHandles[index];
      const infoResult = await protocolOperation("GetObjectInfo", OP_GET_OBJECT_INFO, [handle], true);
      rootObjects.push(parseObjectInfo(infoResult.payload, handle));
      updateProgress(38 + ((index + 1) / rootHandles.length) * 5, "Reading root metadata", `${index + 1} of ${rootHandles.length} root objects checked.`);
    }
    const garmin = rootObjects.find(object => object.filename === "GARMIN" && object.objectFormat === 0x3001);
    if (!garmin) throw new StopError("The GARMIN association was not found at the storage root.");
    updateProgress(45, "GARMIN association found", `Handle ${decimalHex(garmin.handle, 8)} · reading its direct children.`);
    const garminHandlesResult = await protocolOperation("GetObjectHandles", OP_GET_OBJECT_HANDLES, [storageIds[0], ALL_FORMATS, garmin.handle], true);
    const garminHandles = parseObjectHandles(garminHandlesResult.payload);
    const garminObjects = [];
    for (let index = 0; index < garminHandles.length; index += 1) {
      const handle = garminHandles[index];
      const infoResult = await protocolOperation("GetObjectInfo", OP_GET_OBJECT_INFO, [handle], true);
      garminObjects.push(parseObjectInfo(infoResult.payload, handle));
      updateProgress(45 + ((index + 1) / garminHandles.length) * 12, "Reading GARMIN metadata", `${index + 1} of ${garminHandles.length} GARMIN objects checked.`);
    }
    state.current.objectHandles = [{ storageId: storageIds[0], parentHandle: ALL_OBJECTS, handles: rootHandles }, { storageId: storageIds[0], parentHandle: garmin.handle, handles: garminHandles }];
    state.current.objectDiscovery = { storageId: storageIds[0], garminHandle: garmin.handle, rootObjectCount: rootObjects.length, garminObjectCount: garminObjects.length, mapCandidates: garminObjects.filter(object => /.img$/i.test(object.filename)).map(object => ({ handle: object.handle, filename: object.filename, size: object.size })) };
    markStep("objectHandles", "PASS");
    markStep("objectInfo", "PASS");

    const byName = new Map(garminObjects.map(object => [object.filename, object]));
    const targetNames = [...MAP_TARGET_NAMES];
    const missing = targetNames.filter(name => !byName.has(name));
    if (missing.length) throw new StopError(`Required map object(s) not found: ${missing.join(", ")}.`);
    const targets = targetNames.map(name => byName.get(name));
    state.current.mapTargets = targets.map(object => ({ handle: object.handle, name: object.filename, size: object.size }));
    state.current.mapReads = [];
    setStatus(dom.objectCount, `${targets.length} TARGET${targets.length === 1 ? "" : "S"}`);
    updateProgress(60, "Map targets selected", `${targets.map(target => target.filename).join(", ")} · starting streamed reads.`);
    renderMapReads(state.current.mapReads);
    for (let index = 0; index < targets.length; index += 1) {
      const target = targets[index];
      const read = { handle: target.handle, name: target.filename, expectedBytes: target.size, status: "NOT RUN", retries: 0, disconnects: 0, chunkSize: 512, emptyBulkInTransfers: 0 };
      try {
        const infoResult = await protocolOperation("GetObjectInfo", OP_GET_OBJECT_INFO, [target.handle], true);
        const refreshed = parseObjectInfo(infoResult.payload, target.handle);
        read.expectedBytes = refreshed.size;
        const result = await getObjectStream(refreshed, index + 1, targets.length, read);
        Object.assign(read, result, { status: "PASS", retries: 0, disconnects: 0 });
        state.current.mapReads.push(read);
        markStep("getObject", "PASS");
      } catch (error) {
        read.status = "FAIL";
        read.error = safeError(error);
        read.disconnects = /NetworkError|NotFoundError|disconnected|transfer/i.test(read.error.name + " " + read.error.message) ? 1 : 0;
        state.current.mapReads.push(read);
        markStep("getObject", "FAIL");
        renderMapReads(state.current.mapReads);
        throw error;
      }
      renderMapReads(state.current.mapReads);
    }
    setText(dom.mapProgress, `All ${targets.length} map object reads completed.`);
  }

  async function discoverRecursiveObjects(storageId, rootHandles) {
    const objects = [];
    const seen = new Set();
    const queue = [];
    const handleQueries = [];
    let limitsReached = false;
    let depthLimitReached = false;
    let objectLimitReached = false;

    async function inspectHandle(handle, depth, requestedParent) {
      if (seen.has(handle)) return null;
      if (objects.length >= MAX_DISCOVERED_OBJECTS) {
        limitsReached = true;
        objectLimitReached = true;
        return null;
      }
      const infoResult = await protocolOperation("GetObjectInfo", OP_GET_OBJECT_INFO, [handle], true);
      const info = enrichObject(parseObjectInfo(infoResult.payload, handle), depth, requestedParent);
      seen.add(handle);
      objects.push(info);
      return info;
    }

    for (const handle of rootHandles) {
      const info = await inspectHandle(handle, 0, 0);
      if (!info) break;
      if (info.objectFormat === 0x3001) queue.push({ handle: info.handle, depth: 0 });
    }

    while (queue.length) {
      if (objectLimitReached) break;
      const current = queue.shift();
      if (current.depth >= MAX_RECURSION_DEPTH) {
        limitsReached = true;
        depthLimitReached = true;
        break;
      }
      const childResult = await protocolOperation("GetObjectHandles", OP_GET_OBJECT_HANDLES, [storageId, ALL_FORMATS, current.handle], true);
      const childHandles = parseObjectHandles(childResult.payload);
      handleQueries.push({ storageId, parentHandle: current.handle, depth: current.depth + 1, handleCount: childHandles.length });
      for (const childHandle of childHandles) {
        if (seen.has(childHandle)) continue;
        const info = await inspectHandle(childHandle, current.depth + 1, current.handle);
        if (!info) break;
        if (info.objectFormat === 0x3001) queue.push({ handle: info.handle, depth: current.depth + 1 });
      }
      if (objectLimitReached) break;
    }
    return { objects, handleQueries, limitsReached, depthLimitReached, objectLimitReached };
  }

  async function inspectAndDiscoverRecursive() {
    await refreshPresence();
    const existing = (await navigator.usb.getDevices()).find(device => device.vendorId === GARMIN_VENDOR_ID && device.productId === MTP_PRODUCT_ID);
    let device = existing || null;
    if (!device) {
      try {
        device = await navigator.usb.requestDevice({ filters: [{ vendorId: GARMIN_VENDOR_ID, productId: MTP_PRODUCT_ID }] });
      } catch (error) {
        if (error?.name === "NotFoundError") throw new StopError("No MTP device was selected.");
        throw error;
      }
    }
    state.device = device;
    const identity = identityFromDevice(device);
    state.current.identity = identity;
    setText(dom.vendorValue, decimalHex(identity.vendorId));
    setText(dom.productValue, decimalHex(identity.productId));
    setText(dom.usbNameValue, `${identity.manufacturerName || "UNKNOWN"} / ${identity.productName || "UNKNOWN"}`);
    setText(dom.usbSerialValue, identity.serialNumberPresent ? "YES" : "NO");
    markStep("request", "PASS");
    if (identity.vendorId !== GARMIN_VENDOR_ID) throw new StopError("NON-GARMIN — DENIED.");
    markStep("identity", "PASS");
    if (identity.productId !== MTP_PRODUCT_ID) throw new StopError(`USB product ${hexValue(identity.productId)} is not the MTP target ${hexValue(MTP_PRODUCT_ID)}.`);
    if (state.firstProductId === null) state.firstProductId = identity.productId;
    if (state.firstProductId !== identity.productId) throw new StopError(`USB product ID changed: ${hexValue(state.firstProductId)} → ${hexValue(identity.productId)}.`);
    markStep("pid", "PASS");
    await withTimeout(device.open(), "Opening the USB device");
    state.opened = true;
    state.current.topology = captureTopology(device);
    const descriptor = descriptorCheck(state.current.topology);
    if (!descriptor.ok) throw new StopError(descriptor.reason);
    markStep("descriptor", "PASS");
    await selectConfiguration();
    await withTimeout(device.claimInterface(EXPECTED_INTERFACE), "Claiming interface 0");
    state.claimed = true;
    markStep("claim", "PASS");
    state.reader = makeReader(device);
    const openSessionResult = await protocolOperation("OpenSession", OP_OPEN_SESSION, [1], false, { allowSessionAlreadyOpen: true });
    state.sessionOpen = true;
    markStep("openSession", openSessionResult.sessionAlreadyOpen ? "PASS (SESSION ALREADY OPEN)" : "PASS");
    if (openSessionResult.sessionAlreadyOpen) updateProgress(24, "Existing MTP session detected", "Continuing with read-only recovery; the session will be closed safely after inspection.");
    const storageIdsResult = await protocolOperation("GetStorageIDs", OP_GET_STORAGE_IDS, [], true);
    const storageIds = parseStorageIds(storageIdsResult.payload);
    state.current.protocol.storageIds = storageIds;
    markStep("storageIds", "PASS");
    const storages = [];
    const allObjects = [];
    const traversal = [];
    for (const storageId of storageIds) {
      const storageResult = await protocolOperation("GetStorageInfo", OP_GET_STORAGE_INFO, [storageId], true);
      storages.push(parseStorageInfo(storageResult.payload, storageId));
      const rootHandlesResult = await protocolOperation("GetObjectHandles", OP_GET_OBJECT_HANDLES, [storageId, ALL_FORMATS, ALL_OBJECTS], true);
      const rootHandles = parseObjectHandles(rootHandlesResult.payload);
      const discovered = await discoverRecursiveObjects(storageId, rootHandles);
      allObjects.push(...discovered.objects);
      traversal.push({ storageId, rootHandleCount: rootHandles.length, associationQueries: discovered.handleQueries, limitsReached: discovered.limitsReached, depthLimitReached: discovered.depthLimitReached, objectLimitReached: discovered.objectLimitReached });
    }
    state.current.storage = storages;
    state.current.protocol.storage = storages;
    renderStorage(storages);
    markStep("storageInfo", "PASS");
    state.current.objectHandles = traversal;
    markStep("objectHandles", "PASS");
    state.current.objects = allObjects;
    const limitsReached = traversal.some(item => item.limitsReached);
    const depthLimitReached = traversal.some(item => item.depthLimitReached);
    const objectLimitReached = traversal.some(item => item.objectLimitReached);
    state.current.objectDiscovery = {
      recursive: true,
      rootObjectCount: allObjects.filter(object => object.depth === 0).length,
      totalDiscoveredObjects: allObjects.length,
      totalHandles: allObjects.length,
      selectedObjectInfoCount: allObjects.length,
      storageCount: storageIds.length,
      maxRecursionDepth: MAX_RECURSION_DEPTH,
      maxDiscoveredObjects: MAX_DISCOVERED_OBJECTS,
      maxObservedDepth: allObjects.reduce((maximum, object) => Math.max(maximum, object.depth || 0), 0),
      limitsReached,
      depthLimitReached,
      objectLimitReached,
      truncated: limitsReached,
      traversal
    };
    renderObjects(allObjects, allObjects.length, allObjects.length, limitsReached);
    markStep("objectInfo", limitsReached ? "PASS (BOUNDED)" : "PASS");
  }

  async function inspectAndDiscover() {
    if (state.mode === "map-read") {
      updateProgress(2, "Starting Stage 2C", "Preparing the read-only Garmin map-content test.");
      await inspectAndDiscoverMap();
      return;
    }
    if (state.mode === "recursive") {
      await inspectAndDiscoverRecursive();
      return;
    }
    await refreshPresence();
    const existing = (await navigator.usb.getDevices()).find(device => device.vendorId === GARMIN_VENDOR_ID && device.productId === MTP_PRODUCT_ID);
    let device = existing || null;
    if (!device) {
      try {
        device = await navigator.usb.requestDevice({ filters: [{ vendorId: GARMIN_VENDOR_ID, productId: MTP_PRODUCT_ID }] });
      } catch (error) {
        if (error?.name === "NotFoundError") throw new StopError("No MTP device was selected.");
        throw error;
      }
    }
    state.device = device;
    const identity = identityFromDevice(device);
    state.current.identity = identity;
    setText(dom.vendorValue, decimalHex(identity.vendorId));
    setText(dom.productValue, decimalHex(identity.productId));
    setText(dom.usbNameValue, `${identity.manufacturerName || "UNKNOWN"} / ${identity.productName || "UNKNOWN"}`);
    setText(dom.usbSerialValue, identity.serialNumberPresent ? "YES" : "NO");
    markStep("request", "PASS");
    if (identity.vendorId !== GARMIN_VENDOR_ID) throw new StopError("NON-GARMIN — DENIED.");
    markStep("identity", "PASS");
    if (identity.productId !== MTP_PRODUCT_ID) throw new StopError(`USB product ${hexValue(identity.productId)} is not the MTP target ${hexValue(MTP_PRODUCT_ID)}.`);
    if (state.firstProductId === null) state.firstProductId = identity.productId;
    if (state.firstProductId !== identity.productId) throw new StopError(`USB product ID changed: ${hexValue(state.firstProductId)} → ${hexValue(identity.productId)}.`);
    markStep("pid", "PASS");
    await withTimeout(device.open(), "Opening the USB device");
    state.opened = true;
    state.current.topology = captureTopology(device);
    const descriptor = descriptorCheck(state.current.topology);
    if (!descriptor.ok) throw new StopError(descriptor.reason);
    markStep("descriptor", "PASS");
    await selectConfiguration();
    await withTimeout(device.claimInterface(EXPECTED_INTERFACE), "Claiming interface 0");
    state.claimed = true;
    markStep("claim", "PASS");
    state.reader = makeReader(device);
    await protocolOperation("OpenSession", OP_OPEN_SESSION, [1], false);
    state.sessionOpen = true;
    markStep("openSession", "PASS");
    const storageIdsResult = await protocolOperation("GetStorageIDs", OP_GET_STORAGE_IDS, [], true);
    const storageIds = parseStorageIds(storageIdsResult.payload);
    state.current.protocol.storageIds = storageIds;
    markStep("storageIds", "PASS");
    const storages = [];
    const allObjects = [];
    for (const storageId of storageIds) {
      const storageResult = await protocolOperation("GetStorageInfo", OP_GET_STORAGE_INFO, [storageId], true);
      storages.push(parseStorageInfo(storageResult.payload, storageId));
      const handlesResult = await protocolOperation("GetObjectHandles", OP_GET_OBJECT_HANDLES, [storageId, ALL_FORMATS, ALL_OBJECTS], true);
      const handles = parseObjectHandles(handlesResult.payload);
      allObjects.push({ storageId, handles });
    }
    state.current.storage = storages;
    state.current.protocol.storage = storages;
    renderStorage(storages);
    markStep("storageInfo", "PASS");
    state.current.objectHandles = allObjects;
    const totalHandles = allObjects.reduce((sum, entry) => sum + entry.handles.length, 0);
    markStep("objectHandles", "PASS");
    const selectedEntries = allObjects.map(entry => ({ storageId: entry.storageId, ...selectObjectHandles(entry.handles) }));
    const selectedObjects = [];
    const truncated = selectedEntries.some(entry => entry.truncated);
    for (const entry of selectedEntries) {
      for (const handle of entry.selected) {
        const infoResult = await protocolOperation("GetObjectInfo", OP_GET_OBJECT_INFO, [handle], true);
        selectedObjects.push(parseObjectInfo(infoResult.payload, handle));
      }
    }
    state.current.objects = selectedObjects;
    state.current.objectDiscovery = { totalHandles, selectedObjectInfoCount: selectedObjects.length, truncated, storageCount: storageIds.length };
    renderObjects(selectedObjects, totalHandles, selectedObjects.length, truncated);
    markStep("objectInfo", truncated ? "PASS (BOUNDED)" : "PASS");
  }

  async function cleanup() {
    if (state.mode === "map-read") updateProgress(98, "Closing safely", "Closing the MTP session and releasing interface 0.");
    if (state.sessionOpen && state.reader) {
      try {
        await protocolOperation("CloseSession", OP_CLOSE_SESSION, [], false);
        markStep("closeSession", "PASS");
      } catch (error) {
        markStep("closeSession", "FAIL");
        state.current.cleanupError = safeError(error);
      }
      state.sessionOpen = false;
    }
    if (state.claimed && state.device) {
      try {
        await withTimeout(state.device.releaseInterface(EXPECTED_INTERFACE), "Releasing interface 0");
        markStep("release", "PASS");
      } catch (error) {
        markStep("release", "FAIL");
        state.current.cleanupError = safeError(error);
      }
      state.claimed = false;
    }
    if (state.opened && state.device) {
      try {
        await withTimeout(state.device.close(), "Closing the USB device");
        markStep("close", "PASS");
      } catch (error) {
        markStep("close", "FAIL");
        state.current.cleanupError = safeError(error);
      }
      state.opened = false;
    }
    state.reader = null;
    state.device = null;
    await refreshPresence();
  }

  function completed(run) {
    const required = ["request", "identity", "pid", "descriptor", "configuration", "claim", "openSession", "storageIds", "storageInfo", "objectHandles", "objectInfo", "closeSession", "release", "close"];
    if (state.mode === "map-read") required.splice(required.indexOf("closeSession"), 0, "getObject");
    return required.every(name => String(run.steps[name] || "").startsWith("PASS"));
  }

  function renderHistory() {
    if (!state.runs.length) return;
    const rows = state.runs.slice(-6).map(run => `<tr><td>${escapeHtml(run.runNumber)}</td><td>${escapeHtml(run.status)}</td><td>${escapeHtml(run.identity?.vendorIdHex || "UNKNOWN")}</td><td>${escapeHtml(run.identity?.productIdHex || "UNKNOWN")}</td><td>${escapeHtml(run.objectDiscovery?.totalHandles ?? "UNKNOWN")}</td><td>${escapeHtml(run.objectDiscovery?.selectedObjectInfoCount ?? "UNKNOWN")}</td><td>${escapeHtml(run.error?.message || "")}</td></tr>`).join("");
    const table = document.querySelector("#historyTable");
    if (table) table.innerHTML = rows;
    if (dom.cycleProgress && state.mode === "recursive") setText(dom.cycleProgress, `${Math.min(state.runs.length, 3)} / 3 cycles complete`);
  }

  function runSignature(run) {
    return JSON.stringify((run.objects || []).map(object => ({ handle: object.handle, filename: object.filename, objectFormat: object.objectFormat, size: object.size, parentId: object.parentId, depth: object.depth })).sort((left, right) => left.handle - right.handle));
  }

  function recursiveOutcome(runs) {
    if (runs.some(run => run.status !== "PASS" || !completed(run))) return { status: "FAIL", message: "At least one recursive read-only cycle did not complete." };
    if (runs.length < 3) return { status: "NOT RUN", message: `Complete ${3 - runs.length} more identical cycle${runs.length === 2 ? "" : "s"} to verify repeatability.` };
    const signatures = runs.map(runSignature);
    const consistent = signatures.every(signature => signature === signatures[0]);
    if (!consistent) return { status: "FAIL", message: "The last three cycles returned different handles, names or hierarchy." };
    if (runs.some(run => run.objectDiscovery?.limitsReached)) return { status: "PARTIAL PASS", message: "Traversal was repeatable, but a configured safety limit stopped the scan." };
    const garminRoots = new Set((runs[0].objects || []).filter(object => object.filename === "GARMIN" && object.depth === 0).map(object => object.handle));
    const hasGarminChildren = (runs[0].objects || []).some(object => object.depth > 0 && garminRoots.has(object.parentId));
    return hasGarminChildren
      ? { status: "PASS", message: "Three identical cycles completed and additional objects were exposed under an association." }
      : { status: "PARTIAL PASS", message: "Three identical cycles completed; traversal works, but no children were exposed under GARMIN or the other associations." };
  }

  function updateGate() {
    const latest = state.runs.at(-1);
    if (!latest) return;
    if (state.mode === "map-read") {
      const passed = latest.mapReads?.filter(read => read.status === "PASS").length || 0;
      const total = latest.mapTargets?.length || MAP_TARGET_NAMES.length;
      const status = latest.status === "PASS" && completed(latest) && passed === total ? "PASS" : passed > 0 ? "PARTIAL PASS" : "FAIL";
      setStatus(dom.gateStatus, status);
      if (dom.discoveryResult) setStatus(dom.discoveryResult, status);
      dom.gateMessage.hidden = false;
      dom.gateMessage.textContent = status === "PASS" ? `All ${total} map objects were streamed, size-checked and hashed without a write operation.` : `${passed} / ${total} map object read${passed === 1 ? "" : "s"} completed before the safe stop.`;
      return;
    }
    if (state.mode === "recursive") {
      const outcome = recursiveOutcome(state.runs.slice(-3));
      setStatus(dom.gateStatus, outcome.status);
      dom.gateMessage.hidden = false;
      dom.gateMessage.textContent = outcome.message;
      if (dom.discoveryResult) setText(dom.discoveryResult, outcome.status);
      return;
    }
    const pass = latest.status === "PASS" && completed(latest) && !latest.objectDiscovery?.truncated;
    setStatus(dom.gateStatus, pass ? "PASS" : "FAIL");
    dom.gateMessage.hidden = false;
    dom.gateMessage.textContent = pass ? `Read-only object discovery passed: ${latest.objectDiscovery.totalHandles} handle(s), ${latest.objectDiscovery.selectedObjectInfoCount} object-info record(s), no object content read.` : latest.objectDiscovery?.truncated ? "Object handles were enumerated, but metadata was bounded because the handle set exceeded the safe inspection limit." : "The read-only object discovery run did not complete.";
  }

  function finishRun(failure) {
    if (!state.current) return;
    state.current.finishedAt = new Date().toISOString();
    if (state.mode === "map-read" && failure && state.current.mapReads?.some(read => read.status === "PASS")) state.current.status = "PARTIAL PASS";
    else state.current.status = failure ? "FAIL" : "PASS";
    state.current.error = failure ? safeError(failure) : null;
    state.runs.push(state.current);
    setStatus(dom.flowStatus, state.current.status);
    renderHistory();
    updateGate();
    updateProgress(100, failure ? "Stopped safely" : "Completed safely", failure ? state.current.error.message : "All requested operations finished; no write operation was attempted.");
    if (failure) {
      dom.errorMessage.hidden = false;
      dom.errorMessage.textContent = `${state.current.error.name}: ${state.current.error.message}`;
    } else {
      dom.errorMessage.hidden = true;
      dom.errorMessage.textContent = "";
    }
    dom.downloadReport.disabled = false;
    dom.flowMessage.textContent = failure
      ? "Run stopped safely. Review the exact failure before reconnecting."
      : state.mode === "map-read"
        ? "Run complete. Selected map objects were read and hashed; no write operation was attempted."
        : "Run complete. No object content or write operation was attempted.";
  }

  function redactedRun(run) {
    return {
      runNumber: run.runNumber,
      startedAt: run.startedAt,
      finishedAt: run.finishedAt,
      status: run.status,
      steps: run.steps,
      identity: run.identity,
      selectedConfiguration: run.selectedConfiguration,
      protocol: run.protocol,
      storage: run.storage,
      objectDiscovery: run.objectDiscovery,
      objectHandles: run.objectHandles,
      objects: run.objects,
      mapTargets: run.mapTargets || null,
      mapReads: run.mapReads || null,
      error: run.error,
      cleanupError: run.cleanupError || null
    };
  }

  function downloadReport() {
    const recentRuns = state.mode === "recursive" ? state.runs.slice(-3) : state.runs;
    const outcome = state.mode === "recursive" ? recursiveOutcome(recentRuns) : null;
    const latest = state.runs.at(-1);
    const mapOutcome = state.mode === "map-read" && latest
      ? { status: latest.status, message: latest.error?.message || (latest.status === "PASS" ? "All selected map objects were read, size-checked and hashed." : "The map read did not complete for every selected object.") }
      : null;
    const report = {
      stage: state.mode === "recursive" ? "2B.1" : state.mode === "map-read" ? "2C" : "2B",
      method: state.mode === "recursive" ? "webusb-recursive-association-discovery" : state.mode === "map-read" ? "webusb-mtp-map-object-read" : "webusb-object-discovery",
      target: { vendorId: GARMIN_VENDOR_ID, productId: MTP_PRODUCT_ID, configuration: EXPECTED_CONFIGURATION, interface: EXPECTED_INTERFACE },
      allowedOperations: state.mode === "map-read" ? ["OpenSession", "GetStorageIDs", "GetStorageInfo", "GetObjectHandles", "GetObjectInfo", "GetObject", "CloseSession"] : ["OpenSession", "GetStorageIDs", "GetStorageInfo", "GetObjectHandles", "GetObjectInfo", "CloseSession"],
      forbiddenOperations: ["SendObjectInfo", "SendObject", "DeleteObject", "MoveObject", "SetObjectProperty"],
      limits: state.mode === "recursive" ? { maxRecursionDepth: MAX_RECURSION_DEPTH, maxDiscoveredObjects: MAX_DISCOVERED_OBJECTS } : null,
      result: state.mode === "map-read" ? mapOutcome : outcome,
      repeatability: state.mode === "recursive" ? { requiredCycles: 3, completedCycles: recentRuns.length, consistent: recentRuns.length >= 3 && recentRuns.every(run => runSignature(run) === runSignature(recentRuns[0])) } : null,
      environment: { browser: navigator.userAgent, platform: navigator.platform },
      safety: { interfaceClaimCalls: state.runs.filter(run => run.steps.claim).length, objectContentReads: state.mode === "map-read" ? state.runs.reduce((total, run) => total + (run.mapReads || []).length, 0) : 0, writeCalls: 0, deviceFileChanges: { added: 0, changed: 0, removed: 0 } },
      runs: recentRuns.map(redactedRun)
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    dom.downloadAnchor.href = url;
    dom.downloadAnchor.download = `terento-fenix8-${state.mode === "recursive" ? "stage-2b1-recursive" : state.mode === "map-read" ? "stage-2c-map-read" : "stage-2b-objects"}-${new Date().toISOString().replaceAll(/[:.]/g, "-")}.json`;
    dom.downloadAnchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function run() {
    if (state.busy || !dom.consent.checked || !navigator.usb) return;
    state.busy = true;
    startProgressTimer();
    dom.runButton.disabled = true;
    dom.runButton.textContent = state.mode === "map-read" ? "Running Stage 2C…" : state.mode === "recursive" ? "Running Stage 2B.1…" : "Running Stage 2B…";
    resetPanel();
    updateProgress(1, "Starting Stage 2C", "Preparing the read-only USB test.");
    state.transactionId = 1;
    state.current = { runNumber: state.runs.length + 1, startedAt: new Date().toISOString(), status: "FAIL", steps: {}, identity: null, selectedConfiguration: null, topology: [], protocol: { operations: [], storageIds: [], storage: [] }, storage: [], objectHandles: [], objects: [], objectDiscovery: null, mapTargets: [], mapReads: [], error: null, cleanupError: null };
    let failure = null;
    try {
      await inspectAndDiscover();
    } catch (error) {
      failure = error;
      updateProgress(97, "Stopping safely", error?.message || "The test encountered an error and is cleaning up.");
      const unfinished = ["request", "identity", "pid", "descriptor", "configuration", "claim", "openSession", "storageIds", "storageInfo", "objectHandles", "objectInfo", "getObject", "closeSession", "release", "close"];
      unfinished.forEach(name => { if (!state.current.steps[name]) state.current.steps[name] = "NOT RUN"; });
    } finally {
      try {
      await cleanup();
      } catch (error) {
        failure = failure || error;
      }
      finishRun(failure);
      stopProgressTimer();
      state.current = null;
      state.busy = false;
      dom.runButton.disabled = !dom.consent.checked || !navigator.usb;
      dom.runButton.textContent = state.mode === "map-read" ? "Run Stage 2C again" : state.mode === "recursive" ? "Run another Stage 2B.1 cycle" : "Run another Stage 2B discovery";
    }
  }

  function init() {
    setText(dom.browserValue, navigator.userAgent);
    setText(dom.platformValue, navigator.platform || "UNKNOWN");
    if (!navigator.usb) {
      setStatus(dom.apiResult, "FAIL");
      dom.flowMessage.textContent = "This browser does not expose WebUSB.";
    } else {
      setStatus(dom.apiResult, "PASS");
    }
    dom.consent.addEventListener("change", () => { dom.runButton.disabled = !dom.consent.checked || !navigator.usb || state.busy; });
    dom.runButton.addEventListener("click", run);
    dom.downloadReport.addEventListener("click", downloadReport);
    refreshPresence().catch(() => {});
  }

  init();
})();
