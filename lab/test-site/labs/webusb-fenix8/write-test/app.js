(() => {
  "use strict";

  const GARMIN_VENDOR_ID = 0x091e;
  const MTP_PRODUCT_ID = 0x51b8;
  const STORAGE_ID = 0x00020001;
  const CONFIGURATION = 1;
  const INTERFACE = 0;
  const BULK_IN = 1;
  const BULK_OUT = 3;
  const GARMIN_ASSOCIATION = 0x3001;
  // Match libmtp's mapping for a .txt file. 0x3000 is the undefined
  // fallback; Garmin's responder did not acknowledge that variant.
  const FILE_FORMAT = 0x3004;
  const ALL_OBJECTS = 0xffffffff;
  const ALL_FORMATS = 0x0000;
  const RESPONSE_OK = 0x2001;
  const SESSION_ID = 1;
  const OPEN_SESSION_TRANSACTION_ID = 0;
  const RESPONSE_SESSION_ALREADY_OPEN = 0x201e;
  const CONTAINER_COMMAND = 1;
  const CONTAINER_DATA = 2;
  const CONTAINER_RESPONSE = 3;
  const STEP_TIMEOUT_MS = 9000;
  const MAX_CONTAINER_LENGTH = 262144;
  const MAX_ARRAY_COUNT = 4096;
  const TRACE_HEX_LIMIT = 96;
  const OP_GET_DEVICE_INFO = 0x1001;
  const OP_OPEN_SESSION = 0x1002;
  const OP_CLOSE_SESSION = 0x1003;
  const OP_GET_STORAGE_IDS = 0x1004;
  const OP_GET_STORAGE_INFO = 0x1005;
  const OP_GET_OBJECT_HANDLES = 0x1007;
  const OP_GET_OBJECT_INFO = 0x1008;
  const OP_GET_OBJECT = 0x1009;
  const OP_DELETE_OBJECT = 0x100b;
  const OP_SEND_OBJECT_INFO = 0x100c;
  const OP_SEND_OBJECT = 0x100d;
  const CYCLE_COUNT = 3;

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
    recoveryMessage: document.querySelector("#recoveryMessage"),
    apiResult: document.querySelector("#apiResult"),
    requestResult: document.querySelector("#requestResult"),
    identityResult: document.querySelector("#identityResult"),
    pidResult: document.querySelector("#pidResult"),
    descriptorResult: document.querySelector("#descriptorResult"),
    configurationResult: document.querySelector("#configurationResult"),
    claimResult: document.querySelector("#claimResult"),
    deviceInfoResult: document.querySelector("#deviceInfoResult"),
    openSessionResult: document.querySelector("#openSessionResult"),
    storageIdsResult: document.querySelector("#storageIdsResult"),
    storageInfoResult: document.querySelector("#storageInfoResult"),
    objectHandlesResult: document.querySelector("#objectHandlesResult"),
    objectInfoResult: document.querySelector("#objectInfoResult"),
    sendObjectInfoResult: document.querySelector("#sendObjectInfoResult"),
    sendObjectResult: document.querySelector("#sendObjectResult"),
    getObjectResult: document.querySelector("#getObjectResult"),
    deleteObjectResult: document.querySelector("#deleteObjectResult"),
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
    storageTable: document.querySelector("#storageTable"),
    cycleTable: document.querySelector("#cycleTable"),
    integritySummary: document.querySelector("#integritySummary"),
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
    cycles: [],
    baselineObjects: null,
    integrity: null,
    recoveryRequired: false,
    recoveryCandidates: [],
    transportDesynchronized: false,
    transportState: "IDLE",
    progressStartedAt: null,
    progressTimer: null,
    emptyBulkInTransfers: 0
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
    element.className = `status status--${String(value).toLowerCase().replaceAll(" ", "-")}`;
  }

  function safeError(error) {
    return { name: error?.name || "Error", message: error?.message || String(error) };
  }

  function responseCodeMessage(name, code) {
    if (code === RESPONSE_SESSION_ALREADY_OPEN) {
      return `${name} response code ${hexValue(code)} (Session Already Open). Close every other MTP client, physically disconnect the watch, reconnect it, and retry.`;
    }
    return `${name} response code ${hexValue(code)} is not success.`;
  }

  function hexPreview(bytes, limit = TRACE_HEX_LIMIT) {
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
    const preview = Array.from(view.slice(0, limit)).map(byte => byte.toString(16).padStart(2, "0")).join(" ");
    return view.length > limit ? `${preview} … (${view.length} bytes total)` : preview;
  }

  function recordTransportEvent(event, details = {}) {
    const trace = { at: new Date().toISOString(), event, ...details };
    if (state.current?.protocol) {
      state.current.protocol.transportTrace ||= [];
      state.current.protocol.transportTrace.push(trace);
      if (state.current.protocol.transportTrace.length > 2000) state.current.protocol.transportTrace.shift();
    }
  }

  function quarantineTransport(reason) {
    if (state.transportState !== "QUARANTINED") {
      state.transportState = "QUARANTINED";
      state.transportDesynchronized = true;
      state.reader?.invalidate?.(reason);
      recordTransportEvent("transport-quarantined", { reason, reuseBlocked: true });
    }
  }

  function ensureTransportUsable(operationName) {
    if (state.transportDesynchronized || state.transportState === "QUARANTINED") {
      throw new StopError(`${operationName} blocked: USB transport is quarantined after an uncertain transfer. Reconnect the watch before retrying.`);
    }
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function hexValue(value, width = 4) {
    return Number.isFinite(value) ? `0x${value.toString(16).padStart(width, "0")}` : "UNKNOWN";
  }

  function decimalHex(value, width = 4) {
    return Number.isFinite(value) ? `${value} / ${hexValue(value, width)}` : "UNKNOWN";
  }

  function formatElapsed(milliseconds) {
    const seconds = Math.max(0, Math.floor(milliseconds / 1000));
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) return "UNKNOWN";
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB"];
    let amount = bytes;
    let index = -1;
    do {
      amount /= 1024;
      index += 1;
    } while (amount >= 1024 && index < units.length - 1);
    return `${amount.toFixed(amount >= 100 ? 0 : 2)} ${units[index]}`;
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

  function progressForCycle(cycleNumber, phase, label, detail) {
    const base = ((cycleNumber - 1) / CYCLE_COUNT) * 100;
    updateProgress(base + (phase / CYCLE_COUNT), label, detail);
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
      deviceInfo: dom.deviceInfoResult,
      storageIds: dom.storageIdsResult,
      storageInfo: dom.storageInfoResult,
      objectHandles: dom.objectHandlesResult,
      objectInfo: dom.objectInfoResult,
      sendObjectInfo: dom.sendObjectInfoResult,
      sendObject: dom.sendObjectResult,
      getObject: dom.getObjectResult,
      deleteObject: dom.deleteObjectResult,
      closeSession: dom.closeSessionResult,
      release: dom.releaseResult,
      close: dom.closeResult
    };
    if (state.current) state.current.steps[name] = value;
    setStatus(map[name], value);
  }

  function withTimeout(promise, label, timeout = STEP_TIMEOUT_MS) {
    const pending = Promise.resolve(promise);
    let timer;
    let timedOut = false;
    return new Promise((resolve, reject) => {
      timer = setTimeout(() => {
        timedOut = true;
        quarantineTransport(`${label} timed out; the underlying USB transfer cannot be safely reused.`);
        reject(new ProtocolError(`${label} timed out; transport quarantined.`));
      }, timeout);
      pending.then(value => {
        if (timedOut) {
          recordTransportEvent("late-settle", { label, outcome: "resolved", status: value?.status || null, bytesRead: value?.data?.byteLength ?? null, bytesWritten: value?.bytesWritten ?? null });
          return;
        }
        clearTimeout(timer);
        resolve(value);
      }, error => {
        if (timedOut) {
          recordTransportEvent("late-settle", { label, outcome: "rejected", error: safeError(error) });
          return;
        }
        clearTimeout(timer);
        reject(error);
      });
    });
  }

  function identityFromDevice(device) {
    return {
      vendorId: device.vendorId,
      vendorIdHex: hexValue(device.vendorId),
      productId: device.productId,
      productIdHex: hexValue(device.productId),
      manufacturerName: device.manufacturerName || "",
      productName: device.productName || "",
      serialNumberPresent: Boolean(device.serialNumber)
    };
  }

  function captureTopology(device) {
    return (device.configuration ? [device.configuration] : []).map(configuration => ({
      configurationValue: configuration.configurationValue,
      interfaces: configuration.interfaces.map(iface => ({
        interfaceNumber: iface.interfaceNumber,
        alternates: iface.alternates.map(alternate => ({
          alternateSetting: alternate.alternateSetting,
          interfaceClass: alternate.interfaceClass,
          interfaceSubclass: alternate.interfaceSubclass,
          interfaceProtocol: alternate.interfaceProtocol,
          endpoints: alternate.endpoints.map(endpoint => ({ endpointNumber: endpoint.endpointNumber, direction: endpoint.direction, type: endpoint.type, packetSize: endpoint.packetSize }))
        }))
      }))
    }));
  }

  function descriptorCheck(topology) {
    const alternate = topology[0]?.interfaces[0]?.alternates[0];
    if (!alternate) return { ok: false, reason: "The expected USB interface was not exposed." };
    const endpointSet = [[1, "in", "bulk", 512], [2, "in", "interrupt", 64], [3, "out", "bulk", 512]];
    const endpointsMatch = endpointSet.every(expected => alternate.endpoints.some(endpoint => expected.every((value, index) => [endpoint.endpointNumber, endpoint.direction, endpoint.type, endpoint.packetSize][index] === value)));
    const tupleMatch = alternate.interfaceClass === 0xff && alternate.interfaceSubclass === 0xff && alternate.interfaceProtocol === 0x00;
    const interfaceNumber = topology[0]?.interfaces[0]?.interfaceNumber;
    return topology.length === 1 && topology[0].configurationValue === CONFIGURATION && interfaceNumber === INTERFACE && alternate.alternateSetting === 0 && tupleMatch && endpointsMatch
      ? { ok: true }
      : { ok: false, reason: "The observed fēnix 8 MTP descriptor target did not match." };
  }

  function buildContainer(type, code, transactionId, payload = new Uint8Array(0)) {
    const bytes = new Uint8Array(12 + payload.length);
    const view = new DataView(bytes.buffer);
    view.setUint32(0, bytes.length, true);
    view.setUint16(4, type, true);
    view.setUint16(6, code, true);
    view.setUint32(8, transactionId, true);
    bytes.set(payload, 12);
    return bytes;
  }

  function buildCommand(code, transactionId, parameters = []) {
    const payload = new Uint8Array(parameters.length * 4);
    const view = new DataView(payload.buffer);
    parameters.forEach((parameter, index) => view.setUint32(index * 4, parameter >>> 0, true));
    return buildContainer(CONTAINER_COMMAND, code, transactionId, payload);
  }

  function parseContainerHeader(bytes) {
    if (bytes.length < 12) throw new ProtocolError("MTP container header is shorter than 12 bytes.");
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const length = view.getUint32(0, true);
    if (length < 12 || length > MAX_CONTAINER_LENGTH) throw new ProtocolError("MTP container length is outside the safe bound.");
    return { length, type: view.getUint16(4, true), code: view.getUint16(6, true), transactionId: view.getUint32(8, true) };
  }

  function makeReader(device) {
    let pending = new Uint8Array(0);
    let invalidated = false;
    let invalidationReason = "";
    function invalidate(reason) {
      invalidated = true;
      invalidationReason = reason || "USB transport was quarantined.";
      pending = new Uint8Array(0);
    }
    async function pull(deadline) {
      if (invalidated) throw new StopError(`Bulk IN blocked: ${invalidationReason}`);
      const remaining = deadline - performance.now();
      if (remaining <= 0) throw new ProtocolError("Bulk IN read deadline exceeded.");
      recordTransportEvent("bulk-in-start", { endpoint: BULK_IN, bytesRequested: 512 });
      try {
        const transfer = await withTimeout(device.transferIn(BULK_IN, 512), "Bulk IN transfer", remaining);
        const bytesRead = transfer.data?.byteLength || 0;
        recordTransportEvent("bulk-in-complete", { endpoint: BULK_IN, bytesRead, status: transfer.status || "ok", hex: transfer.data ? hexPreview(new Uint8Array(transfer.data.buffer, transfer.data.byteOffset, transfer.data.byteLength)) : "" });
        if (transfer.status && transfer.status !== "ok") throw new ProtocolError(`Bulk IN status: ${transfer.status}.`);
        if (!transfer.data) throw new ProtocolError("Bulk IN returned no data view.");
        if (transfer.data.byteLength === 0) {
          state.emptyBulkInTransfers += 1;
          return;
        }
        const incoming = new Uint8Array(transfer.data.buffer, transfer.data.byteOffset, transfer.data.byteLength);
        const joined = new Uint8Array(pending.length + incoming.length);
        joined.set(pending);
        joined.set(incoming, pending.length);
        pending = joined;
      } catch (error) {
        recordTransportEvent("bulk-in-error", { endpoint: BULK_IN, error: safeError(error) });
        throw error;
      }
    }
    return {
      invalidate,
      async next() {
        if (invalidated) throw new StopError(`Bulk IN blocked: ${invalidationReason}`);
        const deadline = performance.now() + STEP_TIMEOUT_MS;
        while (pending.length < 12) await pull(deadline);
        const headerBytes = pending.slice(0, 12);
        const header = parseContainerHeader(headerBytes);
        while (pending.length < header.length) await pull(deadline);
        const bytes = pending.slice(0, header.length);
        pending = pending.slice(header.length);
        return { ...header, payload: bytes.slice(12), hex: hexPreview(bytes) };
      }
    };
  }

  function cursorFor(bytes) {
    let offset = 0;
    function take(count, label) {
      if (offset + count > bytes.length) throw new ProtocolError(`Malformed ${label} dataset.`);
      const value = bytes.slice(offset, offset + count);
      offset += count;
      return value;
    }
    function u16(label) { return new DataView(take(2, label).buffer).getUint16(0, true); }
    function u32(label) { return new DataView(take(4, label).buffer).getUint32(0, true); }
    function array16(label) {
      const count = u32(`${label} count`);
      if (count > MAX_ARRAY_COUNT) throw new ProtocolError(`${label} count is outside the safe bound.`);
      return Array.from({ length: count }, () => u16(label));
    }
    function text(label) {
      const count = take(1, label)[0];
      if (count === 0) return "";
      const raw = take((count - 1) * 2 + 2, label);
      return new TextDecoder("utf-16le").decode(raw.slice(0, (count - 1) * 2));
    }
    return { u16, u32, array16, text, remaining: () => bytes.length - offset };
  }

  function parseDeviceInfo(payload) {
    const cursor = cursorFor(payload);
    const standardVersion = cursor.u16("standard version");
    const vendorExtensionId = cursor.u32("vendor extension ID");
    const vendorExtensionVersion = cursor.u16("vendor extension version");
    const vendorExtensionDescription = cursor.text("vendor extension description");
    const functionalMode = cursor.u16("functional mode");
    const supportedOperations = cursor.array16("supported operations");
    const supportedEvents = cursor.array16("supported events");
    const supportedDeviceProperties = cursor.array16("supported properties");
    const supportedCaptureFormats = cursor.array16("supported capture formats");
    const supportedImageFormats = cursor.array16("supported image formats");
    const manufacturer = cursor.text("manufacturer");
    const model = cursor.text("model");
    const deviceVersion = cursor.text("device version");
    const serialNumber = cursor.text("serial number");
    return {
      standardVersion,
      vendorExtensionId,
      vendorExtensionVersion,
      vendorExtensionDescription,
      functionalMode,
      supportedOperations,
      supportedEvents,
      supportedDeviceProperties,
      supportedCaptureFormats,
      supportedImageFormats,
      manufacturer,
      model,
      deviceVersion,
      serialNumberPresent: Boolean(serialNumber),
      trailingBytes: cursor.remaining()
    };
  }

  function deviceInfoCapabilityGate(info) {
    const required = [
      OP_GET_STORAGE_IDS,
      OP_GET_STORAGE_INFO,
      OP_GET_OBJECT_HANDLES,
      OP_GET_OBJECT_INFO,
      OP_GET_OBJECT,
      OP_SEND_OBJECT_INFO,
      OP_SEND_OBJECT,
      OP_DELETE_OBJECT
    ];
    const supported = new Set(info.supportedOperations);
    const missing = required.filter(code => !supported.has(code));
    return {
      required,
      supported: info.supportedOperations,
      requiredHex: required.map(code => hexValue(code)),
      supportedHex: info.supportedOperations.map(code => hexValue(code)),
      missing,
      missingHex: missing.map(code => hexValue(code)),
      ok: missing.length === 0
    };
  }

  function parseObjectInfo(payload, handle) {
    const cursor = cursorFor(payload);
    return {
      handle,
      storageId: cursor.u32("storage ID"),
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
      parentId: cursor.u32("parent object"),
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

  function parseStorageIds(payload) {
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const count = view.getUint32(0, true);
    return Array.from({ length: count }, (_, index) => view.getUint32(4 + index * 4, true));
  }

  function parseStorageInfo(payload, storageId) {
    const cursor = cursorFor(payload);
    return {
      storageId,
      storageType: cursor.u16("storage type"),
      filesystemType: cursor.u16("filesystem type"),
      accessCapability: cursor.u16("access capability"),
      maxCapacity: String(BigInt(cursor.u32("capacity low")) + (BigInt(cursor.u32("capacity high")) << 32n)),
      freeSpaceInBytes: String(BigInt(cursor.u32("free low")) + (BigInt(cursor.u32("free high")) << 32n)),
      freeSpaceInObjects: cursor.u32("free objects"),
      storageDescription: cursor.text("storage description"),
      volumeLabel: cursor.text("volume label"),
      trailingBytes: cursor.remaining()
    };
  }

  function parseHandles(payload) {
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const count = view.getUint32(0, true);
    return Array.from({ length: count }, (_, index) => view.getUint32(4 + index * 4, true));
  }

  function parseResponseParameters(payload) {
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const parameters = [];
    for (let offset = 0; offset + 4 <= payload.length; offset += 4) parameters.push(view.getUint32(offset, true));
    return parameters;
  }

  function isWriteOperation(name) {
    return ["SendObjectInfo", "SendObject", "DeleteObject"].includes(name);
  }

  function beginOperationAttempt(name, code, transactionId, options) {
    const attempt = {
      name,
      code,
      codeHex: hexValue(code),
      transactionId,
      status: "IN FLIGHT",
      phase: "COMMAND OUT",
      commandOutStarted: false,
      commandOutCompleted: false,
      dataOutStarted: false,
      dataOutCompleted: false,
      commandBytesOut: 0,
      commandHex: null,
      dataBytesOut: options.dataOut ? options.dataOut.length : 0,
      dataContainerBytesOut: 0,
      dataContainerHex: null,
      commandTransfer: null,
      dataTransfer: null,
      responseReceived: false,
      responseContainerBytesIn: 0,
      responseCode: null,
      responseCodeHex: null,
      error: null,
      startedAt: new Date().toISOString(),
      finishedAt: null
    };
    state.current.protocol.attempts.push(attempt);
    return attempt;
  }

  function recordOperation(name, code, transactionId, details) {
    const operation = { name, code, codeHex: hexValue(code), transactionId, ...details };
    state.current.protocol.operations.push(operation);
    renderProtocol();
    return operation;
  }

  async function operation(name, code, parameters = [], options = {}) {
    ensureTransportUsable(name);
    const transactionId = state.transactionId++;
    const attempt = beginOperationAttempt(name, code, transactionId, options);
    try {
      const command = buildCommand(code, transactionId, parameters);
      attempt.commandBytesOut = command.length;
      attempt.commandHex = hexPreview(command);
      attempt.commandOutStarted = true;
      recordTransportEvent("bulk-out-start", { operation: name, phase: "COMMAND", endpoint: BULK_OUT, bytes: command.length, hex: attempt.commandHex });
      const commandTransfer = await withTimeout(state.device.transferOut(BULK_OUT, command), `${name} command OUT`);
      attempt.commandTransfer = { status: commandTransfer.status || "ok", bytesWritten: commandTransfer.bytesWritten ?? null };
      recordTransportEvent("bulk-out-complete", { operation: name, phase: "COMMAND", endpoint: BULK_OUT, bytes: command.length, status: commandTransfer.status || "ok", bytesWritten: commandTransfer.bytesWritten ?? null });
      if (commandTransfer.status && commandTransfer.status !== "ok") throw new ProtocolError(`${name} command OUT status: ${commandTransfer.status}.`);
      attempt.commandOutCompleted = true;
      if (options.dataOut) {
        attempt.phase = "DATA OUT";
        attempt.dataOutStarted = true;
        const dataContainer = buildContainer(CONTAINER_DATA, code, transactionId, options.dataOut);
        attempt.dataContainerBytesOut = dataContainer.length;
        attempt.dataContainerHex = hexPreview(dataContainer);
        recordTransportEvent("bulk-out-start", { operation: name, phase: "DATA", endpoint: BULK_OUT, bytes: dataContainer.length, payloadBytes: options.dataOut.length, hex: attempt.dataContainerHex });
        const dataTransfer = await withTimeout(state.device.transferOut(BULK_OUT, dataContainer), `${name} data OUT`);
        attempt.dataTransfer = { status: dataTransfer.status || "ok", bytesWritten: dataTransfer.bytesWritten ?? null };
        recordTransportEvent("bulk-out-complete", { operation: name, phase: "DATA", endpoint: BULK_OUT, bytes: dataContainer.length, payloadBytes: options.dataOut.length, status: dataTransfer.status || "ok", bytesWritten: dataTransfer.bytesWritten ?? null });
        if (dataTransfer.status && dataTransfer.status !== "ok") throw new ProtocolError(`${name} data OUT status: ${dataTransfer.status}.`);
        attempt.dataOutCompleted = true;
      }
      attempt.phase = "RESPONSE IN";
      let dataContainer = null;
      let responseContainer = null;
      for (let index = 0; index < 4; index += 1) {
        const container = await state.reader.next();
        if (container.transactionId !== transactionId) throw new ProtocolError(`${name} returned an unexpected transaction ID.`);
        if (container.type === CONTAINER_DATA) {
          if (!options.expectsData || dataContainer) throw new ProtocolError(`${name} returned an unexpected data container.`);
          if (container.code !== code) throw new ProtocolError(`${name} returned a data container with the wrong operation code.`);
          dataContainer = container;
        } else if (container.type === CONTAINER_RESPONSE) {
          responseContainer = container;
          break;
        } else {
          throw new ProtocolError(`${name} returned an unexpected container type.`);
        }
      }
      if (!responseContainer) throw new ProtocolError(`${name} returned no response container.`);
      const responseParameters = parseResponseParameters(responseContainer.payload);
      attempt.responseReceived = true;
      attempt.responseCode = responseContainer.code;
      attempt.responseCodeHex = hexValue(responseContainer.code);
      attempt.responseContainerBytesIn = responseContainer.length;
      attempt.responseHex = responseContainer.hex;
      attempt.responseParameters = responseParameters;
      recordOperation(name, code, transactionId, {
        commandBytesOut: attempt.commandBytesOut,
        commandHex: attempt.commandHex,
        dataBytesOut: options.dataOut ? options.dataOut.length : 0,
        dataContainerBytesOut: attempt.dataContainerBytesOut,
        dataContainerHex: attempt.dataContainerHex,
        dataBytesIn: dataContainer ? dataContainer.payload.length : 0,
        dataContainerBytesIn: dataContainer ? dataContainer.length : 0,
        responseContainerBytesIn: responseContainer.length,
        responseHex: responseContainer.hex,
        responseCode: responseContainer.code,
        responseCodeHex: hexValue(responseContainer.code),
        responseParameters
      });
      if (responseContainer.code !== RESPONSE_OK) throw new StopError(responseCodeMessage(name, responseContainer.code));
      if (options.expectsData && !dataContainer) throw new ProtocolError(`${name} returned no data container.`);
      attempt.status = "PASS";
      attempt.phase = "COMPLETE";
      attempt.transportState = state.transportState;
      attempt.finishedAt = new Date().toISOString();
      return { payload: dataContainer?.payload || new Uint8Array(0), responseParameters };
    } catch (error) {
      attempt.status = "FAIL";
      attempt.error = safeError(error);
      attempt.transportState = state.transportState;
      attempt.finishedAt = new Date().toISOString();
      if (isWriteOperation(name) && (attempt.commandOutStarted || attempt.dataOutStarted)) state.recoveryRequired = true;
      if (error?.name === "ProtocolError" && /timed out|deadline exceeded/i.test(error.message || "")) state.transportDesynchronized = true;
      renderProtocol();
      throw error;
    }
  }

  function mtpString(value) {
    if (!value) return new Uint8Array([0]);
    const bytes = new Uint8Array(1 + value.length * 2 + 2);
    bytes[0] = value.length + 1;
    const view = new DataView(bytes.buffer);
    for (let index = 0; index < value.length; index += 1) view.setUint16(1 + index * 2, value.charCodeAt(index), true);
    view.setUint16(1 + value.length * 2, 0, true);
    return bytes;
  }

  function buildObjectInfo(storageId, parentHandle, filename, contentLength) {
    const strings = [mtpString(filename), mtpString(""), mtpString(""), mtpString("")];
    const bytes = new Uint8Array(52 + strings.reduce((total, stringBytes) => total + stringBytes.length, 0));
    const view = new DataView(bytes.buffer);
    view.setUint32(0, storageId, true);
    view.setUint16(4, FILE_FORMAT, true);
    view.setUint16(6, 0, true);
    view.setUint32(8, contentLength, true);
    view.setUint16(12, 0, true);
    view.setUint32(14, 0, true);
    view.setUint32(18, 0, true);
    view.setUint32(22, 0, true);
    view.setUint32(26, 0, true);
    view.setUint32(30, 0, true);
    view.setUint32(34, 0, true);
    view.setUint32(38, parentHandle, true);
    view.setUint16(42, 0, true);
    view.setUint32(44, 0, true);
    view.setUint32(48, 0, true);
    let offset = 52;
    strings.forEach(stringBytes => { bytes.set(stringBytes, offset); offset += stringBytes.length; });
    return bytes;
  }

  function objectSignature(object) {
    return [object.handle, object.storageId, object.filename, object.objectFormat, object.size, object.parentId].join("|");
  }

  function signatureFor(objects) {
    return objects.map(objectSignature).sort().join("\n");
  }

  function sameObjects(left, right) {
    return signatureFor(left) === signatureFor(right);
  }

  function mapMetadata(objects) {
    return objects.filter(object => /\.img$/i.test(object.filename)).map(object => ({ handle: object.handle, name: object.filename, size: object.size, parent: object.parentId, format: object.objectFormat })).sort((left, right) => left.name.localeCompare(right.name));
  }

  function exactObject(object, expected) {
    return object && object.handle === expected.handle && object.storageId === STORAGE_ID && object.filename === expected.filename && object.objectFormat === FILE_FORMAT && object.size === String(expected.size) && object.parentId === expected.parentHandle;
  }

  async function getObjectInfo(handle) {
    const result = await operation("GetObjectInfo", OP_GET_OBJECT_INFO, [handle], { expectsData: true });
    return parseObjectInfo(result.payload, handle);
  }

  async function getObjectsForParent(storageId, parentHandle) {
    const handlesResult = await operation("GetObjectHandles", OP_GET_OBJECT_HANDLES, [storageId, ALL_FORMATS, parentHandle], { expectsData: true });
    const handles = parseHandles(handlesResult.payload);
    const objects = [];
    for (const handle of handles) objects.push(await getObjectInfo(handle));
    return objects;
  }

  async function findGarmin(storageId) {
    const rootObjects = await getObjectsForParent(storageId, ALL_OBJECTS);
    const garmin = rootObjects.find(object => object.filename === "GARMIN" && object.objectFormat === GARMIN_ASSOCIATION);
    if (!garmin) throw new StopError("The GARMIN association was not found at the storage root.");
    return { garmin, rootObjects };
  }

  async function connectSession(cycleNumber) {
    const permitted = (await navigator.usb.getDevices()).find(device => device.vendorId === GARMIN_VENDOR_ID && device.productId === MTP_PRODUCT_ID);
    let device = permitted;
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
    if (identity.vendorId !== GARMIN_VENDOR_ID) throw new StopError("NON-GARMIN device denied.");
    markStep("identity", "PASS");
    if (identity.productId !== MTP_PRODUCT_ID) throw new StopError("The selected USB product is not the fēnix 8 MTP target.");
    markStep("pid", "PASS");
    await withTimeout(device.open(), "Opening the USB device");
    state.opened = true;
    state.transportState = "OPEN";
    const topology = captureTopology(device);
    const descriptor = descriptorCheck(topology);
    if (!descriptor.ok) throw new StopError(descriptor.reason);
    markStep("descriptor", "PASS");
    if (!device.configuration || device.configuration.configurationValue !== CONFIGURATION) await withTimeout(device.selectConfiguration(CONFIGURATION), "Selecting configuration 1");
    setText(dom.configurationValue, device.configuration?.configurationValue || "UNKNOWN");
    markStep("configuration", "PASS");
    await withTimeout(device.claimInterface(INTERFACE), "Claiming interface 0");
    state.claimed = true;
    state.transportState = "READY";
    markStep("claim", "PASS");
    state.reader = makeReader(device);
    // libmtp starts the OpenSession transaction at ID 0. The next MTP
    // transaction begins at 1 after this operation increments the counter.
    state.transactionId = OPEN_SESSION_TRANSACTION_ID;
    await operation("OpenSession", OP_OPEN_SESSION, [SESSION_ID]);
    state.sessionOpen = true;
    markStep("openSession", "PASS");
    const deviceInfoResult = await operation("GetDeviceInfo", OP_GET_DEVICE_INFO, [], { expectsData: true });
    const deviceInfo = parseDeviceInfo(deviceInfoResult.payload);
    const capabilityGate = deviceInfoCapabilityGate(deviceInfo);
    state.current.deviceInfo = {
      standardVersion: deviceInfo.standardVersion,
      vendorExtensionId: deviceInfo.vendorExtensionId,
      vendorExtensionVersion: deviceInfo.vendorExtensionVersion,
      vendorExtensionDescription: deviceInfo.vendorExtensionDescription,
      functionalMode: deviceInfo.functionalMode,
      supportedOperations: deviceInfo.supportedOperations,
      supportedEvents: deviceInfo.supportedEvents,
      supportedDeviceProperties: deviceInfo.supportedDeviceProperties,
      supportedCaptureFormats: deviceInfo.supportedCaptureFormats,
      supportedImageFormats: deviceInfo.supportedImageFormats,
      manufacturer: deviceInfo.manufacturer,
      model: deviceInfo.model,
      deviceVersion: deviceInfo.deviceVersion,
      serialNumberPresent: deviceInfo.serialNumberPresent,
      trailingBytes: deviceInfo.trailingBytes
    };
    state.current.capabilityGate = {
      required: capabilityGate.required,
      supported: capabilityGate.supported,
      requiredHex: capabilityGate.requiredHex,
      supportedHex: capabilityGate.supportedHex,
      missing: capabilityGate.missing,
      missingHex: capabilityGate.missingHex,
      ok: capabilityGate.ok
    };
    if (!capabilityGate.ok) {
      markStep("deviceInfo", "FAIL");
      const missing = capabilityGate.missing.map(code => hexValue(code)).join(", ");
      throw new StopError(`Write capability gate failed. DeviceInfo does not advertise: ${missing}. No write operation was attempted.`);
    }
    markStep("deviceInfo", "PASS");
    const storageIdsResult = await operation("GetStorageIDs", OP_GET_STORAGE_IDS, [], { expectsData: true });
    const storageIds = parseStorageIds(storageIdsResult.payload);
    if (storageIds.length !== 1 || storageIds[0] !== STORAGE_ID) throw new StopError(`Unexpected storage ID: ${storageIds.map(id => hexValue(id, 8)).join(", ") || "none"}.`);
    markStep("storageIds", "PASS");
    const storageResult = await operation("GetStorageInfo", OP_GET_STORAGE_INFO, [STORAGE_ID], { expectsData: true });
    const storage = parseStorageInfo(storageResult.payload, STORAGE_ID);
    state.current.storage = storage;
    renderStorage(storage);
    markStep("storageInfo", "PASS");
    const { garmin, rootObjects } = await findGarmin(STORAGE_ID);
    const objects = await getObjectsForParent(STORAGE_ID, garmin.handle);
    markStep("objectHandles", "PASS");
    markStep("objectInfo", "PASS");
    state.current.rootObjectCount = rootObjects.length;
    state.current.garminHandle = garmin.handle;
    state.current.garminObjectCount = objects.length;
    setText(dom.usbModeValue, "MTP · interface 0 claimed");
    return { storage, garmin, objects };
  }

  async function cleanupSession(cycle) {
    if (state.sessionOpen && state.reader) {
      if (state.recoveryRequired || state.transportDesynchronized) {
        state.reader.invalidate?.("CloseSession skipped after an uncertain transfer.");
        markStep("closeSession", "SKIPPED");
        cycle.cleanupAction = "MTP CloseSession skipped after an uncertain or desynchronized transfer; USB device close was used instead.";
      } else {
        try {
          await operation("CloseSession", OP_CLOSE_SESSION, []);
          markStep("closeSession", "PASS");
        } catch (error) {
          markStep("closeSession", "FAIL");
          cycle.cleanupError = safeError(error);
        }
      }
      state.sessionOpen = false;
    }
    if (state.claimed && state.device) {
      try {
        await withTimeout(state.device.releaseInterface(INTERFACE), "Releasing interface 0");
        markStep("release", "PASS");
      } catch (error) {
        markStep("release", "FAIL");
        cycle.cleanupError = safeError(error);
      }
      state.claimed = false;
    }
    if ((state.opened || state.transportState === "QUARANTINED") && state.device) {
      try {
        await withTimeout(state.device.close(), "Closing the USB device");
        markStep("close", "PASS");
        if (state.transportState !== "QUARANTINED") state.transportState = "CLOSED";
      } catch (error) {
        markStep("close", "FAIL");
        cycle.cleanupError = safeError(error);
      }
      state.opened = false;
    }
    state.reader?.invalidate?.("USB session cleanup completed.");
    state.reader = null;
    state.device = null;
  }

  async function sha256(bytes) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
  }

  function createTestFile(cycleNumber) {
    const timestamp = new Date().toISOString();
    const compact = timestamp.replaceAll(/[-:.]/g, "");
    const filename = `TERENTO_TEST_${compact}_C${cycleNumber}.txt`;
    const contentText = `Terento WebUSB write validation test.\nTimestamp: ${timestamp}\nCycle: ${cycleNumber}\n`;
    return { filename, contentText, content: new TextEncoder().encode(contentText), timestamp };
  }

  async function runCycle(cycleNumber) {
    const testFile = createTestFile(cycleNumber);
    const cycle = {
      cycle: cycleNumber,
      status: "FAIL",
      filename: testFile.filename,
      content: testFile.contentText,
      expectedSize: testFile.content.length,
      startedAt: new Date().toISOString(),
      createdHandle: null,
      parentHandle: null,
      writtenSha256: await sha256(testFile.content),
      readSha256: null,
      sendDurationMs: null,
      readDurationMs: null,
      deleteResult: "NOT RUN",
      writeState: "NOT STARTED",
      writeAttempt: null,
      existingObjectSetUnchanged: null,
      mapMetadataUnchanged: null,
      remainingTestObject: null,
      error: null,
      cleanupError: null,
      cleanupAction: null
    };
    state.cycles.push(cycle);
    renderCycles();
    try {
      progressForCycle(cycleNumber, 1, `Cycle ${cycleNumber}/${CYCLE_COUNT}: opening session`, "Verifying the permitted Garmin MTP target.");
      const context = await connectSession(cycleNumber);
      cycle.parentHandle = context.garmin.handle;
      if (!state.baselineObjects) {
        state.baselineObjects = context.objects;
        state.integrity = { baselineObjectCount: context.objects.length, baselineMapMetadata: mapMetadata(context.objects), existingObjectSetUnchanged: null, mapMetadataUnchanged: null, unexpectedObjectsRemaining: [] };
      } else if (!sameObjects(state.baselineObjects, context.objects)) {
        state.integrity.existingObjectSetUnchanged = false;
        state.integrity.mapMetadataUnchanged = false;
        throw new StopError("Existing object metadata changed before this cycle; no test object was created.");
      }
      if (context.objects.some(object => object.filename === testFile.filename)) throw new StopError(`Refusing to overwrite an existing object named ${testFile.filename}.`);
      progressForCycle(cycleNumber, 2, `Cycle ${cycleNumber}/${CYCLE_COUNT}: creating test object`, `${testFile.filename} · ${testFile.content.length} bytes · parent ${decimalHex(context.garmin.handle, 8)}.`);
      const objectInfo = buildObjectInfo(STORAGE_ID, context.garmin.handle, testFile.filename, testFile.content.length);
      cycle.writeState = "SENDING OBJECT INFO";
      const sendInfoStarted = performance.now();
      const sendInfoResult = await operation("SendObjectInfo", OP_SEND_OBJECT_INFO, [STORAGE_ID, context.garmin.handle], { dataOut: objectInfo });
      cycle.sendObjectInfoDurationMs = Math.round(performance.now() - sendInfoStarted);
      markStep("sendObjectInfo", "PASS");
      cycle.writeState = "OBJECT INFO ACKNOWLEDGED";
      const responderStorageId = sendInfoResult.responseParameters[0];
      const responderParentHandle = sendInfoResult.responseParameters[1];
      const createdHandle = sendInfoResult.responseParameters[2];
      cycle.responderStorageId = responderStorageId;
      cycle.responderParentHandle = responderParentHandle;
      if (responderStorageId !== STORAGE_ID || responderParentHandle !== context.garmin.handle) throw new StopError("SendObjectInfo returned an unexpected storage or parent; deletion was blocked.");
      if (!Number.isFinite(createdHandle) || createdHandle === 0 || createdHandle === ALL_OBJECTS) throw new ProtocolError("SendObjectInfo did not return a valid object handle.");
      cycle.createdHandle = createdHandle;
      cycle.writeState = "SENDING OBJECT CONTENT";
      const sendStarted = performance.now();
      await operation("SendObject", OP_SEND_OBJECT, [], { dataOut: testFile.content });
      cycle.sendDurationMs = Math.round(performance.now() - sendStarted);
      markStep("sendObject", "PASS");
      cycle.writeState = "OBJECT CONTENT ACKNOWLEDGED";
      const afterCreate = await getObjectsForParent(STORAGE_ID, context.garmin.handle);
      const created = afterCreate.find(object => object.handle === createdHandle);
      if (!exactObject(created, { handle: createdHandle, filename: testFile.filename, size: testFile.content.length, parentHandle: context.garmin.handle })) throw new StopError("Created object verification failed; deletion was blocked.");
      cycle.createdObject = { handle: created.handle, filename: created.filename, size: created.size, parentId: created.parentId, objectFormat: created.objectFormat };
      progressForCycle(cycleNumber, 3, `Cycle ${cycleNumber}/${CYCLE_COUNT}: reading back and hashing`, `Verified exact object identity; reading ${formatBytes(testFile.content.length)} back before deletion.`);
      const readStarted = performance.now();
      const readResult = await operation("GetObject", OP_GET_OBJECT, [createdHandle], { expectsData: true });
      cycle.readDurationMs = Math.round(performance.now() - readStarted);
      const received = readResult.payload;
      cycle.receivedSize = received.length;
      cycle.readSha256 = await sha256(received);
      markStep("getObject", "PASS");
      if (received.length !== testFile.content.length || cycle.readSha256 !== cycle.writtenSha256) throw new StopError("Read-back size or SHA-256 did not match; deletion was blocked.");
      const preDelete = await getObjectInfo(createdHandle);
      if (!exactObject(preDelete, { handle: createdHandle, filename: testFile.filename, size: testFile.content.length, parentHandle: context.garmin.handle })) throw new StopError("Final deletion verification failed; deletion was blocked.");
      cycle.deletionAuthorized = true;
      await operation("DeleteObject", OP_DELETE_OBJECT, [createdHandle]);
      cycle.deleteResult = "PASS";
      markStep("deleteObject", "PASS");
      cycle.writeState = "OBJECT DELETED";
      const afterDelete = await getObjectsForParent(STORAGE_ID, context.garmin.handle);
      const remaining = afterDelete.filter(object => object.filename === testFile.filename && object.parentId === context.garmin.handle);
      if (remaining.length) throw new StopError("The exact test object still appears after DeleteObject.");
      cycle.remainingTestObject = null;
      cycle.existingObjectSetUnchanged = sameObjects(state.baselineObjects, afterDelete);
      cycle.mapMetadataUnchanged = JSON.stringify(mapMetadata(state.baselineObjects)) === JSON.stringify(mapMetadata(afterDelete));
      state.integrity.existingObjectSetUnchanged = cycle.existingObjectSetUnchanged;
      state.integrity.mapMetadataUnchanged = cycle.mapMetadataUnchanged;
      if (!cycle.existingObjectSetUnchanged || !cycle.mapMetadataUnchanged) throw new StopError("Existing object metadata changed after the test object was removed.");
      cycle.status = "PASS";
    } catch (error) {
      cycle.error = safeError(error);
      const failedAttempt = state.current.protocol.attempts.at(-1);
      if (failedAttempt && isWriteOperation(failedAttempt.name) && (failedAttempt.commandOutStarted || failedAttempt.dataOutStarted)) {
        cycle.writeState = "UNKNOWN — OUTBOUND WRITE MAY HAVE REACHED DEVICE";
        cycle.writeAttempt = failedAttempt;
        cycle.remainingTestObject = { handle: cycle.createdHandle, filename: cycle.filename, expectedSize: cycle.expectedSize, parentHandle: cycle.parentHandle, state: "UNKNOWN — verify with Stage 2B.1 before any retry or deletion" };
        state.recoveryCandidates.push({ filename: cycle.filename, expectedSize: cycle.expectedSize, parentHandle: cycle.parentHandle, operation: failedAttempt.name, transactionId: failedAttempt.transactionId });
        state.recoveryRequired = true;
      } else if (cycle.createdHandle && cycle.deleteResult !== "PASS") {
        cycle.remainingTestObject = { handle: cycle.createdHandle, filename: cycle.filename, expectedSize: cycle.expectedSize, parentHandle: cycle.parentHandle, state: "UNKNOWN — verify with Stage 2B.1 before any retry or deletion" };
        state.recoveryRequired = true;
      }
      throw error;
    } finally {
      cycle.finishedAt = new Date().toISOString();
      renderCycles();
      await cleanupSession(cycle);
      renderCycles();
    }
  }

  function renderStorage(storage) {
    if (!dom.storageTable) return;
    dom.storageTable.innerHTML = `<tr><td>${escapeHtml(decimalHex(storage.storageId, 8))}</td><td>${escapeHtml(storage.storageDescription || "EMPTY")}</td><td>${escapeHtml(formatBytes(storage.maxCapacity))}</td><td>${escapeHtml(formatBytes(storage.freeSpaceInBytes))}</td><td>${escapeHtml(decimalHex(storage.accessCapability))}</td></tr>`;
  }

  function renderCycles() {
    if (!dom.cycleTable) return;
    dom.cycleTable.innerHTML = state.cycles.length ? state.cycles.map(cycle => `<tr><td>${cycle.cycle}</td><td>${escapeHtml(cycle.filename)}</td><td>${escapeHtml(cycle.createdHandle ? decimalHex(cycle.createdHandle, 8) : "—")}</td><td>${escapeHtml(cycle.writtenSha256 || "—")}</td><td>${escapeHtml(cycle.readSha256 || "—")}</td><td>${escapeHtml(cycle.deleteResult)}</td><td><span class="status status--${String(cycle.status).toLowerCase().replaceAll(" ", "-")}">${escapeHtml(cycle.status)}</span></td></tr>`).join("") : '<tr><td colspan="7" class="empty">No write cycle has run.</td></tr>';
  }

  function renderProtocol() {
    if (!dom.protocolTable) return;
    const operations = state.current?.protocol?.operations || [];
    const failedAttempts = (state.current?.protocol?.attempts || []).filter(attempt => attempt.status !== "PASS");
    const outLabel = record => `${record.commandBytesOut || 0}${record.dataContainerBytesOut ? ` + ${record.dataContainerBytesOut}` : ""}`;
    const rows = [
      ...operations.map(operationRecord => `<tr><td>${escapeHtml(operationRecord.name)}</td><td>${escapeHtml(decimalHex(operationRecord.code))}</td><td>${escapeHtml(operationRecord.transactionId)}</td><td>${escapeHtml(outLabel(operationRecord))}</td><td>${escapeHtml(operationRecord.dataContainerBytesIn || operationRecord.dataBytesIn || 0)}</td><td>${escapeHtml(decimalHex(operationRecord.responseCode))}</td><td>${escapeHtml(operationRecord.responseCode === RESPONSE_OK ? "OK" : "NOT OK")}</td></tr>`),
      ...failedAttempts.map(attempt => `<tr class="protocol-row--failed"><td>${escapeHtml(attempt.name)} <small>(attempt)</small></td><td>${escapeHtml(attempt.codeHex)}</td><td>${escapeHtml(attempt.transactionId)}</td><td>${escapeHtml(outLabel(attempt))}</td><td>—</td><td>${escapeHtml(attempt.responseCodeHex || "UNKNOWN")}</td><td>NOT CONFIRMED: ${escapeHtml(attempt.error?.message || attempt.status)}</td></tr>`)
    ];
    dom.protocolTable.innerHTML = rows.length ? rows.join("") : '<tr><td colspan="7" class="empty">No protocol transaction yet.</td></tr>';
  }

  function resetPanel() {
    ["requestResult", "identityResult", "pidResult", "descriptorResult", "configurationResult", "claimResult", "deviceInfoResult", "openSessionResult", "storageIdsResult", "storageInfoResult", "objectHandlesResult", "objectInfoResult", "sendObjectInfoResult", "sendObjectResult", "getObjectResult", "deleteObjectResult", "closeSessionResult", "releaseResult", "closeResult"].forEach(key => setStatus(dom[key], "NOT RUN"));
    if (dom.gateMessage) dom.gateMessage.hidden = true;
    if (dom.errorMessage) dom.errorMessage.hidden = true;
    if (dom.recoveryMessage) dom.recoveryMessage.hidden = true;
    if (dom.storageTable) dom.storageTable.innerHTML = '<tr><td colspan="5" class="empty">No storage metadata yet.</td></tr>';
    if (dom.cycleTable) dom.cycleTable.innerHTML = '<tr><td colspan="7" class="empty">No write cycle has run.</td></tr>';
    if (dom.protocolTable) dom.protocolTable.innerHTML = '<tr><td colspan="7" class="empty">No protocol transaction yet.</td></tr>';
    setText(dom.integritySummary, "No device integrity comparison yet.");
  }

  function buildReport() {
    const allPassed = state.cycles.length === CYCLE_COUNT && state.cycles.every(cycle => cycle.status === "PASS") && state.integrity?.existingObjectSetUnchanged === true && state.integrity?.mapMetadataUnchanged === true;
    const failedCycle = state.cycles.find(cycle => cycle.status !== "PASS");
    const remainingObjects = state.cycles.filter(cycle => cycle.remainingTestObject).map(cycle => cycle.remainingTestObject);
    const operations = state.current?.protocol?.operations || [];
    const attempts = state.current?.protocol?.attempts || [];
    const writeAttempts = attempts.filter(attempt => isWriteOperation(attempt.name));
    const outboundWriteAttempts = writeAttempts.filter(attempt => attempt.commandOutStarted || attempt.dataOutStarted);
    const uncertainWriteState = state.recoveryRequired || outboundWriteAttempts.some(attempt => !attempt.responseReceived || attempt.status !== "PASS");
    const resultMessage = allPassed
      ? "Three independent create, read-back, hash-verify and delete cycles completed."
      : uncertainWriteState
        ? "SAFE STOP: an outbound write transfer was attempted without a confirmed response. Run the read-only Stage 2B.1 recovery check before retrying or deleting anything."
        : failedCycle?.error?.message || "The write test did not complete.";
    return {
      stage: "2D",
      method: "webusb-mtp-safe-write-roundtrip",
      target: { vendorId: GARMIN_VENDOR_ID, vendorIdHex: hexValue(GARMIN_VENDOR_ID), productId: MTP_PRODUCT_ID, productIdHex: hexValue(MTP_PRODUCT_ID), configuration: CONFIGURATION, interface: INTERFACE, sessionId: SESSION_ID, openSessionTransactionId: OPEN_SESSION_TRANSACTION_ID },
      allowedOperations: ["OpenSession", "GetDeviceInfo", "GetStorageIDs", "GetStorageInfo", "GetObjectHandles", "GetObjectInfo", "SendObjectInfo", "SendObject", "GetObject", "DeleteObject", "CloseSession"],
      forbiddenOperations: ["Modify existing Garmin files", "Touch any .img file", "RenameObject", "MoveObject", "DeleteObject for any object other than the exact created test object"],
      testObjectPolicy: { filenamePattern: "TERENTO_TEST_<timestamp>_C<cycle>.txt", location: "/GARMIN/", format: hexValue(FILE_FORMAT), content: "Terento WebUSB write validation test + timestamp + cycle.", cyclesRequired: CYCLE_COUNT },
      result: { status: allPassed ? "PASS" : state.cycles.length ? "FAIL" : "NOT RUN", message: resultMessage },
      environment: { browser: navigator.userAgent, platform: navigator.platform },
      safety: {
        writeCalls: outboundWriteAttempts.length,
        confirmedWriteOperations: operations.filter(operationRecord => isWriteOperation(operationRecord.name)).length,
        writeAttempts,
        uncertainWriteState,
        recoveryRequired: Boolean(state.recoveryRequired),
        recoveryCandidates: state.recoveryCandidates,
        transportDesynchronized: Boolean(state.transportDesynchronized),
        transportState: state.transportState,
        mapContentReads: 0,
        mapWriteCalls: 0,
        emptyBulkInTransfers: state.emptyBulkInTransfers,
        existingObjectSetUnchanged: state.integrity?.existingObjectSetUnchanged ?? null,
        existingMapMetadataUnchanged: state.integrity?.mapMetadataUnchanged ?? null,
        unexpectedObjectsRemaining: remainingObjects
      },
      deviceIntegrity: state.integrity ? { ...state.integrity, unexpectedObjectsRemaining: remainingObjects } : { unexpectedObjectsRemaining: remainingObjects },
      deviceInfo: state.current?.deviceInfo || null,
      capabilityGate: state.current?.capabilityGate || null,
      cycles: state.cycles,
      protocol: state.current?.protocol || null
    };
  }

  function finish() {
    const report = buildReport();
    setStatus(dom.flowStatus, report.result.status);
    setStatus(dom.gateStatus, report.safety.recoveryRequired ? "RECOVERY REQUIRED" : report.result.status);
    if (dom.gateMessage) {
      dom.gateMessage.hidden = false;
      dom.gateMessage.textContent = report.result.message;
    }
    if (dom.integritySummary) {
      dom.integritySummary.textContent = report.result.status === "PASS"
        ? "PASS — all three temporary objects were removed; existing object metadata and .img metadata matched the baseline."
        : report.safety.recoveryRequired
          ? "RECOVERY REQUIRED — an outbound write was not fully acknowledged. Confirm the exact filename with Stage 2B.1 before any retry or deletion."
          : "SAFE STOP — review the cycle report before reconnecting or repeating any write test.";
    }
    if (report.result.status === "FAIL" && dom.errorMessage) {
      dom.errorMessage.hidden = report.safety.recoveryRequired;
      dom.errorMessage.textContent = report.result.message;
    }
    if (dom.recoveryMessage) {
      dom.recoveryMessage.hidden = !report.safety.recoveryRequired;
      if (report.safety.recoveryRequired) {
        const candidates = report.safety.recoveryCandidates.map(candidate => `${candidate.filename} (${formatBytes(candidate.expectedSize)})`).join(", ");
        dom.recoveryMessage.innerHTML = `<strong>Do not retry this write test yet.</strong> The device must be checked read-only for: <code>${escapeHtml(candidates || "the last generated TERENTO_TEST file")}</code>. <a href="/labs/webusb-fenix8/recursive/">Open Stage 2B.1 recovery check ↗</a>`;
      }
    }
    dom.downloadReport.disabled = false;
    state.report = report;
  }

  function downloadReport() {
    const report = state.report || buildReport();
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    dom.downloadAnchor.href = url;
    dom.downloadAnchor.download = `terento-fenix8-stage-2d-write-${new Date().toISOString().replaceAll(/[:.]/g, "-")}.json`;
    dom.downloadAnchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function run() {
    if (state.busy || !dom.consent.checked || !navigator.usb) return;
    state.busy = true;
    state.cycles = [];
    state.baselineObjects = null;
    state.integrity = null;
    state.recoveryRequired = false;
    state.recoveryCandidates = [];
    state.transportDesynchronized = false;
    state.transportState = "IDLE";
    state.emptyBulkInTransfers = 0;
    state.report = null;
    state.current = { steps: {}, protocol: { operations: [], attempts: [], transportTrace: [] }, storage: null, identity: null, deviceInfo: null, capabilityGate: null };
    resetPanel();
    startProgressTimer();
    dom.runButton.disabled = true;
    dom.runButton.textContent = "Running Stage 2D…";
    setStatus(dom.flowStatus, "RUNNING");
    updateProgress(1, "Starting Stage 2D", "Preparing the exact temporary test-object policy.");
    let failure = null;
    try {
      for (let cycle = 1; cycle <= CYCLE_COUNT; cycle += 1) {
        try {
          await runCycle(cycle);
        } catch (error) {
          failure = error;
          updateProgress(Math.min(99, ((cycle - 1) / CYCLE_COUNT) * 100 + 30), "Stopped safely", error?.message || "The test stopped before the next write cycle.");
          break;
        }
      }
      if (!failure) updateProgress(100, "Completed safely", "All three temporary objects were verified and removed.");
    } catch (error) {
      failure = error;
    } finally {
      if (failure && dom.errorMessage) {
        dom.errorMessage.hidden = false;
        dom.errorMessage.textContent = safeError(failure).message;
      }
      finish();
      stopProgressTimer();
      state.busy = false;
      dom.runButton.disabled = state.recoveryRequired || !dom.consent.checked || !navigator.usb;
      dom.runButton.textContent = state.recoveryRequired ? "Recovery required before retry" : "Run Stage 2D again";
    }
  }

  function init() {
    setText(dom.browserValue, navigator.userAgent);
    setText(dom.platformValue, navigator.platform || "UNKNOWN");
    if (!navigator.usb) {
      setStatus(dom.apiResult, "FAIL");
      setText(dom.flowMessage, "This browser does not expose WebUSB.");
    } else {
      setStatus(dom.apiResult, "PASS");
    }
    dom.consent.addEventListener("change", () => { dom.runButton.disabled = state.recoveryRequired || !dom.consent.checked || !navigator.usb || state.busy; });
    dom.runButton.addEventListener("click", run);
    dom.downloadReport.addEventListener("click", downloadReport);
    navigator.usb?.getDevices().then(devices => setText(dom.usbPresenceValue, devices.some(device => device.vendorId === GARMIN_VENDOR_ID && device.productId === MTP_PRODUCT_ID) ? "PERMITTED GARMIN MTP DEVICE" : "NO PERMITTED DEVICE"));
  }

  init();
})();
