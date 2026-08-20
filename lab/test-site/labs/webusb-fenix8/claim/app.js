(() => {
  "use strict";

  const GARMIN_VENDOR_ID = 0x091e;
  const EXPECTED_CONFIGURATION = 1;
  const EXPECTED_INTERFACE = 0;
  const BULK_IN = 1;
  const BULK_OUT = 3;
  const INTERRUPT_ENDPOINT = 2;
  const RUN_LIMIT = 3;
  const STEP_TIMEOUT_MS = 9000;
  const MAX_CONTAINER_LENGTH = 32768;
  const MAX_ARRAY_COUNT = 4096;
  const CONTAINER_COMMAND = 1;
  const CONTAINER_DATA = 2;
  const CONTAINER_RESPONSE = 3;
  const RESPONSE_OK = 0x2001;
  const OP_GET_DEVICE_INFO = 0x1001;
  const OP_OPEN_SESSION = 0x1002;
  const OP_CLOSE_SESSION = 0x1003;
  const OP_GET_STORAGE_IDS = 0x1004;
  const OP_GET_STORAGE_INFO = 0x1005;
  const LIBMTP_PRODUCT_ID = 0x51b8;
  const LIBMTP_ORDER_MODE = new URLSearchParams(window.location.search).get("method") === "libmtp";

  const dom = {
    consent: document.querySelector("#consent"),
    runButton: document.querySelector("#runButton"),
    flowStatus: document.querySelector("#flowStatus"),
    flowMessage: document.querySelector("#flowMessage"),
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
    deviceInfoResult: document.querySelector("#deviceInfoResult"),
    openSessionResult: document.querySelector("#openSessionResult"),
    storageIdsResult: document.querySelector("#storageIdsResult"),
    storageInfoResult: document.querySelector("#storageInfoResult"),
    closeSessionResult: document.querySelector("#closeSessionResult"),
    releaseResult: document.querySelector("#releaseResult"),
    closeResult: document.querySelector("#closeResult"),
    browserValue: document.querySelector("#browserValue"),
    vendorValue: document.querySelector("#vendorValue"),
    productValue: document.querySelector("#productValue"),
    usbNameValue: document.querySelector("#usbNameValue"),
    usbSerialValue: document.querySelector("#usbSerialValue"),
    configurationValue: document.querySelector("#configurationValue"),
    infoStatus: document.querySelector("#infoStatus"),
    standardVersion: document.querySelector("#standardVersion"),
    vendorExtensionId: document.querySelector("#vendorExtensionId"),
    vendorExtensionVersion: document.querySelector("#vendorExtensionVersion"),
    vendorExtensionDescription: document.querySelector("#vendorExtensionDescription"),
    functionalMode: document.querySelector("#functionalMode"),
    mtpManufacturer: document.querySelector("#mtpManufacturer"),
    mtpModel: document.querySelector("#mtpModel"),
    mtpVersion: document.querySelector("#mtpVersion"),
    mtpSerial: document.querySelector("#mtpSerial"),
    operationsCount: document.querySelector("#operationsCount"),
    eventsCount: document.querySelector("#eventsCount"),
    propertiesCount: document.querySelector("#propertiesCount"),
    protocolTable: document.querySelector("#protocolTable"),
    storageCount: document.querySelector("#storageCount"),
    storageTable: document.querySelector("#storageTable"),
    repeatStatus: document.querySelector("#repeatStatus"),
    historyTable: document.querySelector("#historyTable"),
    downloadReport: document.querySelector("#downloadReport"),
    downloadPrivate: document.querySelector("#downloadPrivate"),
    privateMessage: document.querySelector("#privateMessage"),
    methodLabel: document.querySelector("#methodLabel"),
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
    privateRuns: [],
    firstProductId: null
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

  function hexValue(value, width = 4) {
    return Number.isFinite(value) ? `0x${value.toString(16).padStart(width, "0")}` : "UNKNOWN";
  }

  function decimalHex(value, width = 4) {
    return Number.isFinite(value) ? `${value} / ${hexValue(value, width)}` : "UNKNOWN";
  }

  function safeError(error) {
    return { name: error?.name || "Error", message: error?.message || String(error) };
  }

  function withTimeout(promise, label, timeout = STEP_TIMEOUT_MS) {
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new StopError(`${label} timed out.`)), timeout);
    });
    return Promise.race([Promise.resolve(promise), deadline]).finally(() => clearTimeout(timer));
  }

  function setStatus(element, value) {
    if (!element) return;
    element.textContent = value;
    const classValue = String(value).toLowerCase().replace(/[^a-z]+/g, "-");
    element.className = `status status--${classValue}`;
  }

  function setText(element, value) {
    if (element) element.textContent = value === null || value === undefined || value === "" ? "UNKNOWN" : String(value);
  }

  function setFlowMessage(value) {
    if (dom.flowMessage) dom.flowMessage.textContent = value;
  }

  function protocolStepOrder() {
    const protocolSteps = LIBMTP_ORDER_MODE
      ? ["openSession", "deviceInfo", "storageIds", "storageInfo"]
      : ["deviceInfo", "openSession", "storageIds", "storageInfo"];
    return ["request", "identity", "pid", "descriptor", "configuration", "claim", ...protocolSteps, "closeSession", "release", "close"];
  }

  function markStep(name, value) {
    if (state.current) state.current.steps[name] = value;
    const map = {
      request: dom.requestResult,
      identity: dom.identityResult,
      pid: dom.pidResult,
      descriptor: dom.descriptorResult,
      configuration: dom.configurationResult,
      claim: dom.claimResult,
      deviceInfo: dom.deviceInfoResult,
      openSession: dom.openSessionResult,
      storageIds: dom.storageIdsResult,
      storageInfo: dom.storageInfoResult,
      closeSession: dom.closeSessionResult,
      release: dom.releaseResult,
      close: dom.closeResult
    };
    setStatus(map[name], value);
  }

  function parseContext() {
    const userAgent = navigator.userAgent;
    const browserMatch = userAgent.match(/(Chrome|Chromium)\/(\d+(?:\.\d+)+)/);
    const macMatch = userAgent.match(/Mac OS X (\d+[._]\d+(?:[._]\d+)?)/);
    return {
      browser: browserMatch ? `Google ${browserMatch[1]} ${browserMatch[2]}` : "Unknown browser",
      platform: navigator.platform || "Unknown platform",
      macVersion: macMatch ? macMatch[1].replaceAll("_", ".") : "Unknown"
    };
  }

  function updateUsbPanel(identity, selectedConfiguration) {
    setText(dom.vendorValue, identity ? decimalHex(identity.vendorId) : "UNKNOWN");
    setText(dom.productValue, identity ? decimalHex(identity.productId) : "UNKNOWN");
    setText(dom.usbNameValue, identity ? `${identity.manufacturerName || "UNKNOWN"} / ${identity.productName || "UNKNOWN"}` : "UNKNOWN");
    setText(dom.usbSerialValue, identity ? `Serial number detected: ${identity.serialNumberPresent ? "YES" : "NO"}` : "NO");
    setText(dom.configurationValue, Number.isFinite(selectedConfiguration) ? decimalHex(selectedConfiguration, 2) : "UNKNOWN");
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
      configurationValueHex: hexValue(configuration.configurationValue, 2),
      interfaces: [...(configuration.interfaces || [])].map(iface => ({
        interfaceNumber: iface.interfaceNumber,
        interfaceNumberHex: hexValue(iface.interfaceNumber, 2),
        alternates: [...(iface.alternates || [])].map(alternate => ({
          alternateSetting: alternate.alternateSetting,
          alternateSettingHex: hexValue(alternate.alternateSetting, 2),
          interfaceClass: alternate.interfaceClass,
          interfaceClassHex: hexValue(alternate.interfaceClass, 2),
          interfaceSubclass: alternate.interfaceSubclass,
          interfaceSubclassHex: hexValue(alternate.interfaceSubclass, 2),
          interfaceProtocol: alternate.interfaceProtocol,
          interfaceProtocolHex: hexValue(alternate.interfaceProtocol, 2),
          interfaceName: alternate.interfaceName || "",
          endpoints: [...(alternate.endpoints || [])].map(endpoint => ({
            endpointNumber: endpoint.endpointNumber,
            endpointNumberHex: hexValue(endpoint.endpointNumber, 2),
            direction: endpoint.direction,
            type: endpoint.type,
            packetSize: endpoint.packetSize,
            packetSizeHex: hexValue(endpoint.packetSize, 4)
          }))
        }))
      }))
    }));
  }

  function expectedDescriptorCheck(topology, productId) {
    if (topology.length !== 1 || topology[0].configurationValue !== EXPECTED_CONFIGURATION) {
      return { ok: false, reason: "Expected exactly configuration 1." };
    }
    const interfaces = topology[0].interfaces;
    if (interfaces.length !== 1 || interfaces[0].interfaceNumber !== EXPECTED_INTERFACE) {
      return { ok: false, reason: "Expected exactly interface 0." };
    }
    const alternates = interfaces[0].alternates;
    if (alternates.length !== 1 || alternates[0].alternateSetting !== 0) {
      return { ok: false, reason: "Expected exactly alternate setting 0." };
    }
    const alternate = alternates[0];
    const expectedProtocol = LIBMTP_ORDER_MODE && productId === LIBMTP_PRODUCT_ID ? 0x00 : 0xff;
    if (alternate.interfaceClass !== 0xff || alternate.interfaceSubclass !== 0xff || alternate.interfaceProtocol !== expectedProtocol) {
      return { ok: false, reason: `Expected vendor-specific class tuple 0xff / 0xff / ${hexValue(expectedProtocol, 2)} for this test mode.` };
    }
    const expected = [
      [1, "in", "bulk", 512],
      [2, "in", "interrupt", 64],
      [3, "out", "bulk", 512]
    ];
    const actual = alternate.endpoints;
    const same = actual.length === expected.length && expected.every(item => actual.some(endpoint => endpoint.endpointNumber === item[0] && endpoint.direction === item[1] && endpoint.type === item[2] && endpoint.packetSize === item[3]));
    return same ? { ok: true, reason: LIBMTP_ORDER_MODE ? "Observed the libmtp Fēnix 8 MTP descriptor target." : "Expected configuration 1 / interface 0 / alternate 0 and endpoint topology observed." } : { ok: false, reason: "Expected bulk IN 1, interrupt IN 2 and bulk OUT 3 with the observed packet sizes." };
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderProtocol() {
    const operations = state.current?.protocol?.operations || [];
    if (!operations.length) {
      dom.protocolTable.innerHTML = '<tr><td colspan="6" class="empty">No protocol transaction yet.</td></tr>';
      return;
    }
    dom.protocolTable.innerHTML = operations.map(operation => `<tr><td>${escapeHtml(operation.name)}</td><td>${escapeHtml(decimalHex(operation.code))}</td><td>${escapeHtml(operation.transactionId)}</td><td>${escapeHtml(operation.dataBytes)}</td><td>${escapeHtml(decimalHex(operation.responseCode))}</td><td>${escapeHtml(operation.responseCode === RESPONSE_OK ? "OK" : "NOT OK")}</td></tr>`).join("");
  }

  function renderStorage(storage) {
    if (!storage || !storage.length) {
      dom.storageTable.innerHTML = '<tr><td colspan="9" class="empty">No storage metadata returned.</td></tr>';
      setStatus(dom.storageCount, storage ? "0" : "NOT RUN");
      return;
    }
    dom.storageTable.innerHTML = storage.map(item => `<tr><td>${escapeHtml(decimalHex(item.storageId, 8))}</td><td>${escapeHtml(decimalHex(item.storageType, 4))}</td><td>${escapeHtml(decimalHex(item.filesystemType, 4))}</td><td>${escapeHtml(decimalHex(item.accessCapability, 4))}</td><td>${escapeHtml(item.maxCapacity)}</td><td>${escapeHtml(item.freeSpaceInBytes)}</td><td>${escapeHtml(item.freeSpaceInObjects)}</td><td>${escapeHtml(item.storageDescription)}</td><td>${escapeHtml(item.volumeLabel)}</td></tr>`).join("");
    setStatus(dom.storageCount, `${storage.length} STORAGE${storage.length === 1 ? "" : "S"}`);
  }

  function renderDeviceInfo(info) {
    setStatus(dom.infoStatus, info ? "PASS" : "NOT RUN");
    if (!info) return;
    setText(dom.standardVersion, decimalHex(info.standardVersion, 4));
    setText(dom.vendorExtensionId, decimalHex(info.vendorExtensionId, 8));
    setText(dom.vendorExtensionVersion, decimalHex(info.vendorExtensionVersion, 4));
    setText(dom.vendorExtensionDescription, info.vendorExtensionDescription || "EMPTY");
    setText(dom.functionalMode, decimalHex(info.functionalMode, 4));
    setText(dom.mtpManufacturer, info.manufacturer || "EMPTY");
    setText(dom.mtpModel, info.model || "EMPTY");
    setText(dom.mtpVersion, info.deviceVersion || "EMPTY");
    setText(dom.mtpSerial, info.serialNumberPresent ? "YES" : "NO");
    setText(dom.operationsCount, info.supportedOperations.length);
    setText(dom.eventsCount, info.supportedEvents.length);
    setText(dom.propertiesCount, info.supportedDeviceProperties.length);
  }

  function renderHistory() {
    const runs = state.runs.slice(-RUN_LIMIT);
    setStatus(dom.repeatStatus, `${runs.length} / ${RUN_LIMIT}`);
    if (!runs.length) {
      dom.historyTable.innerHTML = '<tr><td colspan="8" class="empty">No run recorded.</td></tr>';
      return;
    }
    dom.historyTable.innerHTML = runs.map(run => {
      const identity = run.identity || {};
      const info = run.deviceInfo || {};
      const claim = run.steps.claim || "NOT RUN";
      return `<tr><td>${escapeHtml(run.runNumber)}</td><td>${escapeHtml(run.status)}</td><td>${escapeHtml(identity.vendorIdHex || "UNKNOWN")}</td><td>${escapeHtml(identity.productIdHex || "UNKNOWN")}</td><td>${escapeHtml(info.model || info.manufacturer || "NOT OBSERVED")}</td><td>${escapeHtml(run.storage.length)}</td><td>${escapeHtml(claim)}</td><td>${escapeHtml(run.error?.message || "")}</td></tr>`;
    }).join("");
  }

  function renderTopology(topology) {
    const rows = [];
    topology.forEach(configuration => configuration.interfaces.forEach(iface => iface.alternates.forEach(alternate => alternate.endpoints.forEach(endpoint => {
      rows.push(`<tr><td>${escapeHtml(decimalHex(configuration.configurationValue, 2))}</td><td>${escapeHtml(decimalHex(iface.interfaceNumber, 2))}</td><td>${escapeHtml(decimalHex(alternate.alternateSetting, 2))}</td><td>${escapeHtml(decimalHex(alternate.interfaceClass, 2))}</td><td>${escapeHtml(decimalHex(alternate.interfaceSubclass, 2))}</td><td>${escapeHtml(decimalHex(alternate.interfaceProtocol, 2))}</td><td>${escapeHtml(alternate.interfaceName)}</td><td>${escapeHtml(decimalHex(endpoint.endpointNumber, 2))}</td><td>${escapeHtml(endpoint.direction)}</td><td>${escapeHtml(endpoint.type)}</td><td>${escapeHtml(decimalHex(endpoint.packetSize, 4))}</td></tr>`);
    }))));
    const table = document.querySelector("#topologyTable");
    if (table) table.innerHTML = rows.join("") || '<tr><td colspan="11" class="empty">No descriptor topology.</td></tr>';
  }

  function resetRunPanel() {
    ["requestResult", "identityResult", "pidResult", "descriptorResult", "configurationResult", "claimResult", "deviceInfoResult", "openSessionResult", "storageIdsResult", "storageInfoResult", "closeSessionResult", "releaseResult", "closeResult"].forEach(key => setStatus(dom[key], "NOT RUN"));
    setStatus(dom.flowStatus, "RUNNING");
    setStatus(dom.gateStatus, "NOT RUN");
    dom.gateMessage.hidden = true;
    dom.errorMessage.hidden = true;
    dom.protocolTable.innerHTML = '<tr><td colspan="6" class="empty">No protocol transaction yet.</td></tr>';
    dom.storageTable.innerHTML = '<tr><td colspan="9" class="empty">No storage metadata yet.</td></tr>';
    setStatus(dom.storageCount, "NOT RUN");
    renderDeviceInfo(null);
    setText(dom.configurationValue, "UNKNOWN");
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
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const length = view.getUint32(0, true);
    if (length < 12 || length > MAX_CONTAINER_LENGTH || length !== bytes.length) throw new ProtocolError("Container length is invalid.");
    return {
      length,
      type: view.getUint16(4, true),
      code: view.getUint16(6, true),
      transactionId: view.getUint32(8, true),
      payload: bytes.slice(12)
    };
  }

  function makeReader(device) {
    let pending = new Uint8Array(0);
    async function pull(deadline) {
      const remaining = Math.max(100, deadline - performance.now());
      const transfer = await withTimeout(device.transferIn(BULK_IN, 512), "Bulk IN transfer", remaining);
      if (transfer.status && transfer.status !== "ok") throw new ProtocolError(`Bulk IN status: ${transfer.status}.`);
      if (!transfer.data || transfer.data.byteLength === 0) throw new ProtocolError("Bulk IN returned no bytes.");
      const incoming = new Uint8Array(transfer.data.buffer, transfer.data.byteOffset, transfer.data.byteLength);
      const joined = new Uint8Array(pending.length + incoming.length);
      joined.set(pending);
      joined.set(incoming, pending.length);
      pending = joined;
    }
    return {
      async next() {
        const deadline = performance.now() + STEP_TIMEOUT_MS;
        while (pending.length < 4) await pull(deadline);
        const firstView = new DataView(pending.buffer, pending.byteOffset, pending.byteLength);
        const length = firstView.getUint32(0, true);
        if (length < 12 || length > MAX_CONTAINER_LENGTH) throw new ProtocolError("Returned container length is outside the safe bound.");
        while (pending.length < length) await pull(deadline);
        const bytes = pending.slice(0, length);
        pending = pending.slice(length);
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
    function u8(label) { return take(1, label)[0]; }
    function u16(label) { return new DataView(take(2, label).buffer).getUint16(0, true); }
    function u32(label) { return new DataView(take(4, label).buffer).getUint32(0, true); }
    function u64(label) {
      const view = new DataView(take(8, label).buffer);
      const low = BigInt(view.getUint32(0, true));
      const high = BigInt(view.getUint32(4, true));
      return ((high << 32n) | low).toString();
    }
    function text(label) {
      const count = u8(label);
      if (count === 0) return "";
      const value = new TextDecoder("utf-16le").decode(take((count - 1) * 2, label));
      return value.replace(/\u0000+$/g, "");
    }
    function array16(label) {
      const count = u32(label);
      if (count > MAX_ARRAY_COUNT) throw new ProtocolError(`${label} count is outside the safe bound.`);
      return Array.from({ length: count }, () => u16(label));
    }
    return {
      u16,
      u32,
      u64,
      text,
      array16,
      remaining: () => bytes.length - offset
    };
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
      rawSerialNumber: serialNumber || null,
      trailingBytes: cursor.remaining()
    };
  }

  function parseStorageIds(payload) {
    const cursor = cursorFor(payload);
    const count = cursor.u32("storage count");
    if (count > MAX_ARRAY_COUNT) throw new ProtocolError("Storage count is outside the safe bound.");
    return Array.from({ length: count }, () => cursor.u32("storage ID"));
  }

  function parseStorageInfo(payload, storageId) {
    const cursor = cursorFor(payload);
    return {
      storageId,
      storageType: cursor.u16("storage type"),
      filesystemType: cursor.u16("filesystem type"),
      accessCapability: cursor.u16("access capability"),
      maxCapacity: cursor.u64("capacity"),
      freeSpaceInBytes: cursor.u64("free space"),
      freeSpaceInObjects: cursor.u32("free objects"),
      storageDescription: cursor.text("storage description"),
      volumeLabel: cursor.text("volume label"),
      trailingBytes: cursor.remaining()
    };
  }

  function recordOperation(name, code, transactionId, dataBytes, responseCode) {
    const operation = {
      name,
      code,
      codeHex: hexValue(code),
      transactionId,
      dataBytes,
      responseCode,
      responseCodeHex: hexValue(responseCode)
    };
    state.current.protocol.operations.push(operation);
    renderProtocol();
    return operation;
  }

  async function protocolOperation(name, code, parameters, expectsData) {
    const transactionId = state.transactionId;
    state.transactionId += 1;
    const command = buildCommand(code, transactionId, parameters);
    const transferOut = await withTimeout(state.device.transferOut(BULK_OUT, command), `${name} bulk OUT`);
    if (transferOut.status && transferOut.status !== "ok") throw new ProtocolError(`${name} bulk OUT status: ${transferOut.status}.`);
    const reader = state.reader;
    let dataContainer = null;
    let responseContainer = null;
    for (let index = 0; index < 4; index += 1) {
      const container = await reader.next();
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
    if (responseContainer.code !== RESPONSE_OK) throw new StopError(`${name} response code ${hexValue(responseContainer.code)} is not success.`);
    if (expectsData && !dataContainer) throw new ProtocolError(`${name} returned no data container.`);
    return { payload: dataContainer ? dataContainer.payload : new Uint8Array(0), operation };
  }

  async function selectExpectedConfiguration() {
    const selected = state.device.configuration?.configurationValue;
    if (selected !== EXPECTED_CONFIGURATION) await withTimeout(state.device.selectConfiguration(EXPECTED_CONFIGURATION), "Selecting configuration 1");
    const after = state.device.configuration?.configurationValue;
    state.current.selectedConfiguration = Number.isFinite(after) ? after : null;
    updateUsbPanel(state.current.identity, after);
    if (after !== EXPECTED_CONFIGURATION) throw new StopError("Configuration 1 could not be confirmed after selection.");
    markStep("configuration", "PASS");
  }

  async function inspectAndClaim() {
    const filter = { vendorId: GARMIN_VENDOR_ID };
    if (LIBMTP_ORDER_MODE) filter.productId = LIBMTP_PRODUCT_ID;
    const device = await navigator.usb.requestDevice({ filters: [filter] });
    state.device = device;
    const identity = identityFromDevice(device);
    state.current.identity = identity;
    state.currentPrivate.identity = { vendorId: identity.vendorId, productId: identity.productId, rawUsbSerial: device.serialNumber || null };
    updateUsbPanel(identity, null);
    markStep("request", "PASS");
    if (identity.vendorId !== GARMIN_VENDOR_ID) {
      markStep("identity", "FAIL");
      throw new StopError("NON-GARMIN — DENIED.");
    }
    markStep("identity", "PASS");
    if (LIBMTP_ORDER_MODE && identity.productId !== LIBMTP_PRODUCT_ID) {
      markStep("pid", "FAIL");
      throw new StopError(`libmtp method requires USB product ID ${hexValue(LIBMTP_PRODUCT_ID)}.`);
    }
    if (state.firstProductId === null) {
      state.firstProductId = identity.productId;
      state.current.pidStability = "BASELINE";
      markStep("pid", "PASS");
    } else if (identity.productId !== state.firstProductId) {
      state.current.pidStability = "FAIL";
      markStep("pid", "FAIL");
      throw new StopError(`USB product ID changed during Stage 2A.2: ${hexValue(state.firstProductId)} → ${hexValue(identity.productId)}.`);
    } else {
      state.current.pidStability = "PASS";
      markStep("pid", "PASS");
    }
    await withTimeout(device.open(), "Opening the USB device");
    state.opened = true;
    const topology = captureTopology(device);
    state.current.topology = topology;
    const target = expectedDescriptorCheck(topology, identity.productId);
    renderTopology(topology);
    if (!target.ok) {
      markStep("descriptor", "FAIL");
      throw new StopError(target.reason);
    }
    markStep("descriptor", "PASS");
    await selectExpectedConfiguration();
    await withTimeout(device.claimInterface(EXPECTED_INTERFACE), "Claiming interface 0");
    state.claimed = true;
    markStep("claim", "PASS");
    state.reader = makeReader(device);
    state.current.protocol = { operations: [], storageIds: [], storage: [] };
    if (LIBMTP_ORDER_MODE) {
      await protocolOperation("OpenSession", OP_OPEN_SESSION, [1], false);
      state.current.sessionId = 1;
      state.sessionOpen = true;
      markStep("openSession", "PASS");
    }
    const infoResult = await protocolOperation("GetDeviceInfo", OP_GET_DEVICE_INFO, [], true);
    const parsedInfo = parseDeviceInfo(infoResult.payload);
    state.current.deviceInfo = {
      standardVersion: parsedInfo.standardVersion,
      vendorExtensionId: parsedInfo.vendorExtensionId,
      vendorExtensionVersion: parsedInfo.vendorExtensionVersion,
      vendorExtensionDescription: parsedInfo.vendorExtensionDescription,
      functionalMode: parsedInfo.functionalMode,
      supportedOperations: parsedInfo.supportedOperations,
      supportedEvents: parsedInfo.supportedEvents,
      supportedDeviceProperties: parsedInfo.supportedDeviceProperties,
      supportedCaptureFormats: parsedInfo.supportedCaptureFormats,
      supportedImageFormats: parsedInfo.supportedImageFormats,
      manufacturer: parsedInfo.manufacturer,
      model: parsedInfo.model,
      deviceVersion: parsedInfo.deviceVersion,
      serialNumberPresent: parsedInfo.serialNumberPresent,
      trailingBytes: parsedInfo.trailingBytes
    };
    state.currentPrivate.mtpSerial = parsedInfo.rawSerialNumber;
    renderDeviceInfo(state.current.deviceInfo);
    markStep("deviceInfo", "PASS");
    if (!LIBMTP_ORDER_MODE) {
      await protocolOperation("OpenSession", OP_OPEN_SESSION, [1], false);
      state.current.sessionId = 1;
      state.sessionOpen = true;
      markStep("openSession", "PASS");
    }
    const storageIdsResult = await protocolOperation("GetStorageIDs", OP_GET_STORAGE_IDS, [], true);
    const storageIds = parseStorageIds(storageIdsResult.payload);
    state.current.protocol.storageIds = storageIds;
    markStep("storageIds", "PASS");
    const storage = [];
    for (const storageId of storageIds) {
      const storageResult = await protocolOperation("GetStorageInfo", OP_GET_STORAGE_INFO, [storageId], true);
      storage.push(parseStorageInfo(storageResult.payload, storageId));
    }
    state.current.protocol.storage = storage;
    state.current.storage = storage;
    renderStorage(storage);
    markStep("storageInfo", "PASS");
  }

  async function cleanup() {
    if (state.sessionOpen && state.reader) {
      try {
        await protocolOperation("CloseSession", OP_CLOSE_SESSION, [], false);
        markStep("closeSession", "PASS");
      } catch (error) {
        state.current.cleanupError = safeError(error);
        markStep("closeSession", "FAIL");
      }
      state.sessionOpen = false;
    }
    if (state.claimed && state.device) {
      try {
        await withTimeout(state.device.releaseInterface(EXPECTED_INTERFACE), "Releasing interface 0");
        markStep("release", "PASS");
      } catch (error) {
        state.current.cleanupError = safeError(error);
        markStep("release", "FAIL");
      }
      state.claimed = false;
    }
    if (state.opened && state.device) {
      try {
        await withTimeout(state.device.close(), "Closing the USB device");
        markStep("close", "PASS");
      } catch (error) {
        state.current.cleanupError = safeError(error);
        markStep("close", "FAIL");
      }
      state.opened = false;
    }
    state.reader = null;
    state.device = null;
  }

  function requiredStepsPass(run) {
    return ["request", "identity", "pid", "descriptor", "configuration", "claim", "deviceInfo", "openSession", "storageIds", "storageInfo", "closeSession", "release", "close"].every(name => run.steps[name] === "PASS");
  }

  function comparePublicInfo(left, right) {
    if (!left || !right) return false;
    return left.manufacturer === right.manufacturer && left.model === right.model && left.deviceVersion === right.deviceVersion;
  }

  function compareStorage(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
  }

  function updateGate() {
    const hasRuns = state.runs.length > 0;
    dom.downloadReport.hidden = false;
    dom.downloadReport.disabled = !hasRuns;
    dom.downloadReport.textContent = hasRuns ? "Download redacted Stage 2A.2 log (JSON)" : "Download log after a run";
    const latest = state.runs.slice(-RUN_LIMIT);
    const complete = latest.length === RUN_LIMIT;
    const allPass = complete && latest.every(run => run.status === "PASS" && requiredStepsPass(run));
    const identityStable = complete && latest.every(run => run.identity?.vendorId === GARMIN_VENDOR_ID && run.identity?.productId === latest[0].identity?.productId);
    const mtpStable = complete && latest.every(run => comparePublicInfo(latest[0].deviceInfo, run.deviceInfo));
    const storageStable = complete && latest.every(run => compareStorage(latest[0].storage, run.storage));
    const gate = allPass && identityStable && mtpStable && storageStable ? "PASS" : complete ? "FAIL" : "NOT RUN";
    setStatus(dom.gateStatus, gate);
    setStatus(dom.repeatStatus, `${latest.length} / ${RUN_LIMIT}`);
    dom.gateMessage.hidden = !complete;
    if (complete) dom.gateMessage.textContent = `Latest three runs — protocol: ${allPass ? "PASS" : "FAIL"}; USB identity stable: ${identityStable ? "YES" : "NO"}; MTP identity stable: ${mtpStable ? "YES" : "NO"}; storage metadata stable: ${storageStable ? "YES" : "NO"}.`;
    dom.downloadPrivate.hidden = !state.privateRuns.some(run => run.mtpSerial || run.identity?.rawUsbSerial);
    dom.privateMessage.textContent = state.privateRuns.some(run => run.mtpSerial) ? "An MTP serial is held in this tab memory. Download only the private local record if needed." : "No MTP serial has been exposed by the runs so far.";
  }

  function finishRun(error) {
    if (error) state.current.error = safeError(error);
    if (!state.current.error && state.current.cleanupError) state.current.error = state.current.cleanupError;
    state.current.status = !state.current.error && requiredStepsPass(state.current) ? "PASS" : "FAIL";
    state.current.finishedAt = new Date().toISOString();
    const completedRun = state.current;
    state.runs.push(completedRun);
    state.privateRuns.push(state.currentPrivate);
    const status = completedRun.status;
    setStatus(dom.flowStatus, status);
    setFlowMessage(status === "PASS" ? `Run ${completedRun.runNumber} completed the minimal read-only proof. Physically reconnect before the next run.` : `Run ${completedRun.runNumber} stopped safely. Review the exact failure before reconnecting.`);
    if (completedRun.error) {
      dom.errorMessage.hidden = false;
      dom.errorMessage.textContent = `${completedRun.error.name}: ${completedRun.error.message}`;
    }
    try {
      renderHistory();
      updateGate();
    } catch (renderError) {
      const safeRenderError = safeError(renderError);
      dom.errorMessage.hidden = false;
      dom.errorMessage.textContent = `${completedRun.error?.name || "RunError"}: ${completedRun.error?.message || "Run stopped safely."} (${safeRenderError.name}: ${safeRenderError.message})`;
    }
    state.current = null;
    state.currentPrivate = null;
  }

  function markUnfinishedStep() {
    if (!state.current) return;
    const pending = protocolStepOrder().find(name => !state.current.steps[name]);
    if (pending) markStep(pending, "FAIL");
  }

  async function run() {
    if (state.busy || !dom.consent.checked || !navigator.usb) return;
    state.busy = true;
    dom.runButton.disabled = true;
    dom.runButton.textContent = "Running Stage 2A.2…";
    resetRunPanel();
    state.transactionId = 1;
    state.opened = false;
    state.claimed = false;
    state.sessionOpen = false;
    state.reader = null;
    state.current = {
      runNumber: state.runs.length + 1,
      startedAt: new Date().toISOString(),
      status: "FAIL",
      steps: {},
      identity: null,
      pidStability: null,
      selectedConfiguration: null,
      topology: [],
      deviceInfo: null,
      protocol: { operations: [], storageIds: [], storage: [] },
      storage: [],
      error: null,
      cleanupError: null
    };
    state.currentPrivate = { runNumber: state.current.runNumber, startedAt: state.current.startedAt, identity: null, mtpSerial: null };
    let failure = null;
    try {
      await inspectAndClaim();
    } catch (error) {
      failure = error;
      markUnfinishedStep();
    } finally {
      try {
        await cleanup();
      } catch (error) {
        failure = failure || error;
        if (state.current) {
          state.current.cleanupError = safeError(error);
          markUnfinishedStep();
        }
      }
      try {
        finishRun(failure);
      } catch (error) {
        const safeFinalizationError = safeError(error);
        dom.errorMessage.hidden = false;
        dom.errorMessage.textContent = `${safeFinalizationError.name}: ${safeFinalizationError.message}`;
        state.current = null;
        state.currentPrivate = null;
      } finally {
        state.busy = false;
        dom.runButton.disabled = !dom.consent.checked || !navigator.usb;
        dom.runButton.textContent = state.runs.length >= RUN_LIMIT ? "Run another Stage 2.2 reconnect" : "Run Stage 2A.2 after reconnect";
      }
    }
  }

  function redactedRun(run) {
    return {
      runNumber: run.runNumber,
      startedAt: run.startedAt,
      finishedAt: run.finishedAt,
      status: run.status,
      steps: run.steps,
      identity: run.identity,
      pidStability: run.pidStability,
      selectedConfiguration: run.selectedConfiguration,
      topology: run.topology,
      deviceInfo: run.deviceInfo,
      protocol: run.protocol,
      storage: run.storage,
      error: run.error || null
    };
  }

  function exportJson(filename, payload) {
    const anchor = dom.downloadAnchor;
    anchor.href = `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(payload, null, 2))}`;
    anchor.download = filename;
    anchor.click();
  }

  function reportPayload() {
    const latest = state.runs.slice(-RUN_LIMIT);
    const first = latest[0] || {};
    const physicalIdentity = latest.length === RUN_LIMIT && state.privateRuns.slice(-RUN_LIMIT).every(run => run.mtpSerial) && state.privateRuns.slice(-RUN_LIMIT).every(run => run.mtpSerial === state.privateRuns.slice(-RUN_LIMIT)[0].mtpSerial) ? "YES" : "UNKNOWN";
    return {
      testTimestamp: new Date().toISOString(),
      stage: "2A.2",
      method: LIBMTP_ORDER_MODE ? "libmtp-order" : "baseline",
      protocolOrder: LIBMTP_ORDER_MODE
        ? ["OpenSession", "GetDeviceInfo", "GetStorageIDs", "GetStorageInfo", "CloseSession"]
        : ["GetDeviceInfo", "OpenSession", "GetStorageIDs", "GetStorageInfo", "CloseSession"],
      environment: parseContext(),
      priorProductIds: { stage2A: "0x51b8", stage2A1: "0x0003" },
      vid: first.identity?.vendorId ?? null,
      vidHex: first.identity?.vendorIdHex || "UNKNOWN",
      pidPerRun: latest.map(run => ({ runNumber: run.runNumber, productId: run.identity?.productId ?? null, productIdHex: run.identity?.productIdHex || "UNKNOWN" })),
      usbManufacturer: first.identity?.manufacturerName || "",
      usbProduct: first.identity?.productName || "",
      mtpManufacturer: first.deviceInfo?.manufacturer || "",
      mtpModel: first.deviceInfo?.model || "",
      mtpDeviceVersion: first.deviceInfo?.deviceVersion || "",
      mtpSerialNumberPresent: Boolean(first.deviceInfo?.serialNumberPresent),
      currentClassification: "KNOWN GARMIN — COMPATIBILITY TEST IN PROGRESS",
      usb: {
        configuration: first.selectedConfiguration,
        interface: 0,
        alternate: 0,
        bulkIn: "endpoint 1 / 512 bytes",
        interruptIn: "endpoint 2 / 64 bytes — unused",
        bulkOut: "endpoint 3 / 512 bytes"
      },
      runs: state.runs.map(redactedRun),
      repeatability: {
        latestThree: latest.length === RUN_LIMIT ? latest.map(run => ({ runNumber: run.runNumber, status: run.status })) : [],
        samePhysicalWatch: physicalIdentity,
        usbIdentityStable: latest.length === RUN_LIMIT && latest.every(run => run.identity?.vendorId === first.identity?.vendorId && run.identity?.productId === first.identity?.productId),
        mtpIdentityStable: latest.length === RUN_LIMIT && latest.every(run => comparePublicInfo(first.deviceInfo, run.deviceInfo)),
        storageMetadataStable: latest.length === RUN_LIMIT && latest.every(run => compareStorage(first.storage, run.storage))
      },
      safety: {
        interfaceClaimCalls: state.runs.filter(run => run.steps.claim).length,
        allowedMtpCommandsSent: state.runs.reduce((sum, run) => sum + (run.protocol?.operations?.length || 0), 0),
        disallowedProtocolCalls: 0,
        deviceFileChanges: { added: 0, changed: 0, removed: 0 }
      },
      redaction: "Raw USB/MTP serial values, buffers, filenames, paths, object handles and activity data are not included."
    };
  }

  function downloadReport() {
    exportJson(`terento-fenix8-stage-2a2-${new Date().toISOString().replace(/[:.]/g, "-")}.json`, reportPayload());
  }

  function downloadPrivate() {
    const privateRuns = state.privateRuns.filter(run => run.mtpSerial || run.identity?.rawUsbSerial);
    if (!privateRuns.length) {
      dom.privateMessage.textContent = "No raw serial was exposed by these runs.";
      return;
    }
    const first = privateRuns[0];
    const last = privateRuns[privateRuns.length - 1];
    exportJson(`terento-private-fenix8-stage-2a2-${new Date().toISOString().replace(/[:.]/g, "-")}.json`, {
      recordType: "Terento private physical device identity",
      recordTimestamp: new Date().toISOString(),
      usb: { vendorId: first.identity?.vendorId, productId: first.identity?.productId, serialNumber: first.identity?.rawUsbSerial || null },
      mtp: { serialNumber: first.mtpSerial || null, model: state.runs.find(run => run.runNumber === first.runNumber)?.deviceInfo?.model || "" },
      firstSeen: first.startedAt,
      lastSeen: last.finishedAt || last.startedAt,
      note: "LOCAL ONLY. Never share, commit, push or include this file in the redacted report."
    });
    dom.privateMessage.textContent = "Private identity record downloaded locally. Keep it outside Git and never share it.";
  }

  function setup() {
    const context = parseContext();
    setText(dom.browserValue, `${context.browser} · ${context.macVersion}`);
    const available = Boolean(navigator.usb);
    setStatus(dom.apiResult, available ? "PASS" : "FAIL");
    if (LIBMTP_ORDER_MODE && dom.methodLabel) {
      dom.methodLabel.hidden = false;
      dom.methodLabel.textContent = "LIBMTP ORDER VARIANT: only PID 0x51b8 is allowed; OpenSession runs before GetDeviceInfo. Read-only metadata only.";
    }
    dom.consent.addEventListener("change", () => { dom.runButton.disabled = !dom.consent.checked || !available || state.busy; });
    dom.runButton.addEventListener("click", run);
    dom.downloadReport.addEventListener("click", downloadReport);
    dom.downloadPrivate.addEventListener("click", downloadPrivate);
    if (!available) {
      dom.flowMessage.textContent = "WebUSB is unavailable. Use Google Chrome on macOS.";
      dom.consent.disabled = true;
    }
    renderHistory();
    if (navigator.usb) navigator.usb.addEventListener("disconnect", event => { if (state.device && event.device === state.device) dom.flowMessage.textContent = "The watch disconnected. This run will close safely; reconnect before the next run."; });
  }

  setup();
})();
