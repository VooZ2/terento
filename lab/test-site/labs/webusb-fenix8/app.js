(() => {
  "use strict";

  const GARMIN_VENDOR_ID = 0x091e;
  const RUN_LIMIT = 3;
  const CLOSE_TIMEOUT_MS = 12000;

  const dom = {
    action: document.querySelector("#connectButton"),
    apiStatus: document.querySelector("#apiStatus"),
    browserMessage: document.querySelector("#browserMessage"),
    flowStatus: document.querySelector("#flowStatus"),
    flowMessage: document.querySelector("#flowMessage"),
    apiResult: document.querySelector("#apiResult"),
    requestResult: document.querySelector("#requestResult"),
    garminIdentityResult: document.querySelector("#garminIdentityResult"),
    openResult: document.querySelector("#openResult"),
    descriptorResult: document.querySelector("#descriptorResult"),
    analysisResult: document.querySelector("#analysisResult"),
    closeResult: document.querySelector("#closeResult"),
    identityStabilityResult: document.querySelector("#identityStabilityResult"),
    topologyStabilityResult: document.querySelector("#topologyStabilityResult"),
    repeatResult: document.querySelector("#repeatResult"),
    browserValue: document.querySelector("#browserValue"),
    platformValue: document.querySelector("#platformValue"),
    architectureValue: document.querySelector("#architectureValue"),
    usbVendorValue: document.querySelector("#usbVendorValue"),
    usbProductValue: document.querySelector("#usbProductValue"),
    usbNameValue: document.querySelector("#usbNameValue"),
    serialValue: document.querySelector("#serialValue"),
    descriptorTable: document.querySelector("#descriptorTable"),
    analysisTable: document.querySelector("#analysisTable"),
    summary: document.querySelector("#summary"),
    downloadReport: document.querySelector("#downloadReport"),
    downloadPrivate: document.querySelector("#downloadPrivate"),
    privateMessage: document.querySelector("#privateMessage")
  };

  const state = {
    busy: false,
    opened: false,
    device: null,
    currentRun: null,
    currentPrivateRun: null,
    runs: [],
    privateRuns: [],
    events: [],
    classification: "UNKNOWN"
  };

  class StopError extends Error {
    constructor(message) {
      super(message);
      this.name = "StoppedSafely";
    }
  }

  function parseUserAgent() {
    const userAgent = navigator.userAgent;
    const browserMatch = userAgent.match(/(Chrome|Chromium)\/(\d+(?:\.\d+)+)/);
    const macMatch = userAgent.match(/Mac OS X (\d+[._]\d+(?:[._]\d+)?)/);
    return {
      browser: browserMatch ? `Google ${browserMatch[1]} ${browserMatch[2]}` : "Unknown browser",
      platform: navigator.platform || "Unknown platform",
      architecture: "Not exposed by browser",
      macVersion: macMatch ? macMatch[1].replaceAll("_", ".") : "Unknown"
    };
  }

  function numberValue(value) {
    return Number.isFinite(value) ? value : null;
  }

  function hexValue(value, width = 2) {
    return Number.isFinite(value) ? `0x${value.toString(16).padStart(width, "0")}` : "UNKNOWN";
  }

  function decimalHex(value, width = 2) {
    return Number.isFinite(value) ? `${value} / ${hexValue(value, width)}` : "UNKNOWN";
  }

  function formatEndpoint(endpoint) {
    return {
      endpointNumber: numberValue(endpoint.endpointNumber),
      endpointNumberHex: hexValue(endpoint.endpointNumber, 2),
      direction: endpoint.direction || "unknown",
      type: endpoint.type || "unknown",
      packetSize: numberValue(endpoint.packetSize),
      packetSizeHex: hexValue(endpoint.packetSize, 4)
    };
  }

  function captureDescriptors(device) {
    return [...(device.configurations || [])].map(configuration => ({
      configurationValue: numberValue(configuration.configurationValue),
      configurationValueHex: hexValue(configuration.configurationValue, 2),
      configurationName: configuration.configurationName || "",
      interfaceCount: configuration.interfaces.length,
      interfaces: configuration.interfaces.map(iface => ({
        interfaceNumber: numberValue(iface.interfaceNumber),
        interfaceNumberHex: hexValue(iface.interfaceNumber, 2),
        alternates: iface.alternates.map(alternate => ({
          alternateSetting: numberValue(alternate.alternateSetting),
          alternateSettingHex: hexValue(alternate.alternateSetting, 2),
          interfaceClass: numberValue(alternate.interfaceClass),
          interfaceClassHex: hexValue(alternate.interfaceClass, 2),
          interfaceSubclass: numberValue(alternate.interfaceSubclass),
          interfaceSubclassHex: hexValue(alternate.interfaceSubclass, 2),
          interfaceProtocol: numberValue(alternate.interfaceProtocol),
          interfaceProtocolHex: hexValue(alternate.interfaceProtocol, 2),
          interfaceName: alternate.interfaceName || "",
          endpointCount: alternate.endpoints.length,
          endpoints: alternate.endpoints.map(formatEndpoint)
        }))
      }))
    }));
  }

  function allAlternates(configurations) {
    return configurations.flatMap(configuration => configuration.interfaces.flatMap(iface => iface.alternates.map(alternate => ({
      configurationValue: configuration.configurationValue,
      interfaceNumber: iface.interfaceNumber,
      alternate
    }))));
  }

  function analyzeAlternate(item) {
    const alternate = item.alternate;
    const endpoints = alternate.endpoints;
    const bulkIn = endpoints.filter(endpoint => endpoint.direction === "in" && endpoint.type === "bulk");
    const bulkOut = endpoints.filter(endpoint => endpoint.direction === "out" && endpoint.type === "bulk");
    const interrupt = endpoints.filter(endpoint => endpoint.type === "interrupt");
    const standardPtpTuple = alternate.interfaceClass === 0x06
      && alternate.interfaceSubclass === 0x01
      && alternate.interfaceProtocol === 0x01;
    const vendorSpecific = alternate.interfaceClass === 0xff;
    let classification = "UNKNOWN";
    let reason = "No sufficient class or endpoint evidence for an MTP candidate.";

    if (standardPtpTuple && bulkIn.length > 0 && bulkOut.length > 0) {
      classification = "LIKELY MTP";
      reason = "Observed 0x06 / 0x01 / 0x01 Still Image/PTP-compatible class tuple with bulk IN and bulk OUT; this is structural evidence, not proof of MTP.";
    } else if (vendorSpecific && bulkIn.length > 0 && bulkOut.length > 0) {
      classification = "POSSIBLE MTP";
      reason = "Observed vendor-specific class 0xff with bulk IN and bulk OUT; this can carry a proprietary PTP/MTP-like transport, but class-level evidence is absent.";
    } else if (bulkIn.length > 0 && bulkOut.length > 0) {
      classification = "POSSIBLE MTP";
      reason = "Observed bulk IN and bulk OUT; the endpoint shape can carry a data transport, but no standard PTP/MTP class tuple was observed.";
    } else if (interrupt.length > 0) {
      classification = "UNLIKELY MTP";
      reason = "Observed interrupt endpoint(s) without both bulk IN and bulk OUT; this is insufficient for a typical PTP/MTP data transport.";
    }

    return {
      configurationValue: item.configurationValue,
      configurationValueHex: hexValue(item.configurationValue, 2),
      interfaceNumber: item.interfaceNumber,
      interfaceNumberHex: hexValue(item.interfaceNumber, 2),
      alternateSetting: alternate.alternateSetting,
      alternateSettingHex: alternate.alternateSettingHex,
      interfaceClass: alternate.interfaceClass,
      interfaceClassHex: alternate.interfaceClassHex,
      interfaceSubclass: alternate.interfaceSubclass,
      interfaceSubclassHex: alternate.interfaceSubclassHex,
      interfaceProtocol: alternate.interfaceProtocol,
      interfaceProtocolHex: alternate.interfaceProtocolHex,
      interfaceName: alternate.interfaceName,
      endpointCount: alternate.endpointCount,
      bulkInCount: bulkIn.length,
      bulkOutCount: bulkOut.length,
      interruptCount: interrupt.length,
      classification,
      reason
    };
  }

  function analyzeDescriptors(configurations) {
    return allAlternates(configurations).map(analyzeAlternate);
  }

  function setStatus(element, value) {
    if (!element) return;
    element.textContent = value;
    element.className = `status status--${value.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  }

  function markRun(name, value) {
    if (state.currentRun) state.currentRun.steps[name] = value;
    const element = {
      request: dom.requestResult,
      garminIdentity: dom.garminIdentityResult,
      open: dom.openResult,
      descriptor: dom.descriptorResult,
      analysis: dom.analysisResult,
      close: dom.closeResult
    }[name];
    setStatus(element, value);
  }

  function event(record) {
    state.events.push({ ...record, timestamp: new Date().toISOString() });
  }

  function setFlowMessage(message) {
    dom.flowMessage.textContent = message;
  }

  function updateEnvironment(device) {
    const context = parseUserAgent();
    dom.browserValue.textContent = context.browser;
    dom.platformValue.textContent = context.platform;
    dom.architectureValue.textContent = context.architecture;
    if (!device) return;
    dom.usbVendorValue.textContent = decimalHex(device.vendorId, 4);
    dom.usbProductValue.textContent = decimalHex(device.productId, 4);
    dom.usbNameValue.textContent = `${device.manufacturerName || "UNKNOWN"} / ${device.productName || "UNKNOWN"}`;
    dom.serialValue.textContent = `Serial number detected: ${device.serialNumber ? "YES" : "NO"}`;
  }

  function clearDescriptorTable() {
    dom.descriptorTable.replaceChildren();
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="11" class="empty">Nothing inspected yet.</td>';
    dom.descriptorTable.append(row);
  }

  function appendCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
    row.append(cell);
  }

  function renderDescriptors(configurations) {
    dom.descriptorTable.replaceChildren();
    const rows = [];
    configurations.forEach(configuration => {
      configuration.interfaces.forEach(iface => {
        iface.alternates.forEach(alternate => {
          const endpoints = alternate.endpoints.length ? alternate.endpoints : [null];
          endpoints.forEach(endpoint => rows.push({ configuration, iface, alternate, endpoint }));
        });
      });
    });
    if (!rows.length) {
      clearDescriptorTable();
      return;
    }
    rows.forEach(({ configuration, iface, alternate, endpoint }) => {
      const row = document.createElement("tr");
      appendCell(row, decimalHex(configuration.configurationValue, 2));
      appendCell(row, decimalHex(iface.interfaceNumber, 2));
      appendCell(row, decimalHex(alternate.alternateSetting, 2));
      appendCell(row, decimalHex(alternate.interfaceClass, 2));
      appendCell(row, decimalHex(alternate.interfaceSubclass, 2));
      appendCell(row, decimalHex(alternate.interfaceProtocol, 2));
      appendCell(row, alternate.interfaceName);
      appendCell(row, endpoint ? decimalHex(endpoint.endpointNumber, 2) : "—");
      appendCell(row, endpoint?.direction);
      appendCell(row, endpoint?.type);
      appendCell(row, endpoint ? decimalHex(endpoint.packetSize, 4) : "—");
      dom.descriptorTable.append(row);
    });
  }

  function renderAnalysis(analysis) {
    dom.analysisTable.replaceChildren();
    if (!analysis.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="6" class="empty">No alternates exposed.</td>';
      dom.analysisTable.append(row);
      return;
    }
    analysis.forEach(item => {
      const row = document.createElement("tr");
      appendCell(row, decimalHex(item.configurationValue, 2));
      appendCell(row, decimalHex(item.interfaceNumber, 2));
      appendCell(row, decimalHex(item.alternateSetting, 2));
      appendCell(row, item.classification);
      appendCell(row, `bulk IN ${item.bulkInCount}; bulk OUT ${item.bulkOutCount}; interrupt ${item.interruptCount}`);
      appendCell(row, item.reason);
      dom.analysisTable.append(row);
    });
  }

  function withTimeout(promise, timeoutMs, label) {
    return Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new StopError(`${label} timed out.`)), timeoutMs))
    ]);
  }

  function errorText(error) {
    if (error?.name === "NotFoundError") return "No device selected.";
    return error?.message || String(error);
  }

  function deviceIdentity(device) {
    return {
      vendorId: numberValue(device.vendorId),
      productId: numberValue(device.productId),
      manufacturerName: device.manufacturerName || "",
      productName: device.productName || "",
      serialNumberPresent: Boolean(device.serialNumber)
    };
  }

  async function inspectDevice() {
    const device = await navigator.usb.requestDevice({ filters: [{ vendorId: GARMIN_VENDOR_ID }] });
    state.device = device;
    const identity = deviceIdentity(device);
    state.currentRun.identity = { usb: identity };
    state.currentPrivateRun.identity = {
      vendorId: identity.vendorId,
      productId: identity.productId,
      rawSerialNumber: device.serialNumber || null
    };
    event({
      type: "device-selected",
      vendorId: identity.vendorId,
      productId: identity.productId,
      manufacturerName: identity.manufacturerName,
      productName: identity.productName,
      serialNumberPresent: identity.serialNumberPresent
    });
    updateEnvironment(device);
    markRun("request", "PASS");
    if (device.vendorId !== GARMIN_VENDOR_ID) {
      state.classification = "NON-GARMIN — DENIED";
      markRun("garminIdentity", "FAIL");
      throw new StopError("NON-GARMIN — DENIED. The selected USB vendor does not match the established Garmin vendor ID.");
    }
    state.classification = "KNOWN GARMIN — COMPATIBILITY TEST IN PROGRESS";
    markRun("garminIdentity", "PASS");

    await withTimeout(device.open(), CLOSE_TIMEOUT_MS, "Opening the USB device");
    state.opened = true;
    markRun("open", "PASS");

    const configurations = captureDescriptors(device);
    const analysis = analyzeDescriptors(configurations);
    state.currentRun.configurations = configurations;
    state.currentRun.analysis = analysis;
    state.currentPrivateRun.topology = configurations;
    renderDescriptors(configurations);
    renderAnalysis(analysis);
    markRun("descriptor", "PASS");
    markRun("analysis", "PASS");
    event({
      type: "descriptor-capture",
      configurationCount: configurations.length,
      interfaceCount: configurations.reduce((sum, configuration) => sum + configuration.interfaceCount, 0),
      alternateCount: analysis.length,
      endpointCount: configurations.reduce((sum, configuration) => sum + configuration.interfaces.reduce((ifaceSum, iface) => ifaceSum + iface.alternates.reduce((alternateSum, alternate) => alternateSum + alternate.endpoints.length, 0), 0), 0)
    });
    state.currentRun.status = "PASS";
    setStatus(dom.flowStatus, "PASS");
    setFlowMessage(`Run ${state.currentRun.runNumber} captured the complete WebUSB descriptor topology. No interface was claimed.`);
  }

  async function closeDevice() {
    let closePass = true;
    if (state.opened && state.device) {
      try {
        await withTimeout(state.device.close(), CLOSE_TIMEOUT_MS, "Closing the USB device");
      } catch (error) {
        closePass = false;
        event({ type: "device-close-error", error: errorText(error) });
      }
    }
    if (state.currentRun) markRun("close", closePass ? "PASS" : "FAIL");
    state.opened = false;
    state.device = null;
  }

  function clearStatuses() {
    [dom.requestResult, dom.garminIdentityResult, dom.openResult, dom.descriptorResult, dom.analysisResult, dom.closeResult].forEach(element => setStatus(element, "NOT RUN"));
    setStatus(dom.flowStatus, "UNKNOWN");
    clearDescriptorTable();
    renderAnalysis([]);
    dom.summary.hidden = true;
    dom.privateMessage.textContent = "Raw serial values remain in this tab memory until a private record is explicitly downloaded.";
  }

  function selectedRuns() {
    return state.runs.filter(run => run.steps.request === "PASS" && run.steps.descriptor === "PASS");
  }

  function privateSelectedRuns() {
    return state.privateRuns.filter(run => run.identity && run.topology);
  }

  function sameUsb(left, right) {
    return left.vendorId === right.vendorId
      && left.productId === right.productId
      && left.manufacturerName === right.manufacturerName
      && left.productName === right.productName
      && left.serialNumberPresent === right.serialNumberPresent;
  }

  function topologyComparable(topology) {
    return JSON.stringify(topology);
  }

  function updateStability() {
    const runs = selectedRuns();
    const privateRuns = privateSelectedRuns();
    if (runs.length < RUN_LIMIT) {
      setStatus(dom.identityStabilityResult, "NOT RUN");
      setStatus(dom.topologyStabilityResult, "NOT RUN");
      setStatus(dom.repeatResult, "NOT RUN");
      dom.downloadPrivate.hidden = !state.privateRuns.some(run => run.identity?.rawSerialNumber);
      dom.summary.hidden = state.runs.length === 0;
      if (!dom.summary.hidden) dom.summary.textContent = `${runs.length}/${RUN_LIMIT} descriptor run(s) captured. Physically disconnect and reconnect the watch between runs.`;
      return;
    }

    const firstUsb = runs[0].identity.usb;
    const usbStable = runs.slice(1, RUN_LIMIT).every(run => sameUsb(firstUsb, run.identity.usb));
    const firstTopology = topologyComparable(runs[0].configurations);
    const topologyStable = runs.slice(1, RUN_LIMIT).every(run => topologyComparable(run.configurations) === firstTopology);
    const serials = privateRuns.slice(0, RUN_LIMIT).map(run => run.identity.rawSerialNumber);
    const physicalIdentity = serials.length === RUN_LIMIT && serials.every(Boolean)
      ? (serials.every(serial => serial === serials[0]) ? "YES" : "NO")
      : "UNKNOWN";
    setStatus(dom.identityStabilityResult, usbStable ? "PASS" : "FAIL");
    setStatus(dom.topologyStabilityResult, topologyStable ? "PASS" : "FAIL");
    setStatus(dom.repeatResult, usbStable && topologyStable ? "PASS" : "FAIL");
    dom.summary.hidden = false;
    dom.summary.textContent = `${RUN_LIMIT}/${RUN_LIMIT} descriptor runs captured. USB identity stable: ${usbStable ? "YES" : "NO"}. Descriptor topology identical: ${topologyStable ? "YES" : "NO"}. Same physical device: ${physicalIdentity}.`;
    dom.downloadReport.hidden = false;
    dom.downloadPrivate.hidden = !privateRuns.some(run => run.identity.rawSerialNumber);
  }

  function completeRun(error) {
    if (error) {
      state.currentRun.status = "FAIL";
      state.currentRun.error = errorText(error);
      setStatus(dom.flowStatus, "FAIL");
      setFlowMessage(`${state.currentRun.error} No interface was claimed and no USB data operation was attempted.`);
      const failedStep = state.currentRun.steps;
      if (!failedStep.request) markRun("request", "FAIL");
      else if (!failedStep.garminIdentity) markRun("garminIdentity", "FAIL");
      else if (!failedStep.open) markRun("open", "FAIL");
      else if (!failedStep.descriptor) markRun("descriptor", "FAIL");
      else if (!failedStep.analysis) markRun("analysis", "FAIL");
    }
    state.currentRun.finishedAt = new Date().toISOString();
    state.runs.push(state.currentRun);
    state.privateRuns.push(state.currentPrivateRun);
    event({ type: "run-complete", runNumber: state.currentRun.runNumber, status: state.currentRun.status, error: state.currentRun.error || null });
    updateStability();
    state.currentRun = null;
    state.currentPrivateRun = null;
  }

  async function run() {
    if (state.busy) return;
    state.busy = true;
    dom.action.disabled = true;
    dom.action.textContent = "Inspecting descriptors…";
    clearStatuses();
    const runNumber = state.runs.length + 1;
    state.currentRun = {
      runNumber,
      startedAt: new Date().toISOString(),
      status: "FAIL",
      steps: {},
      identity: null,
      configurations: [],
      analysis: []
    };
    state.currentPrivateRun = {
      runNumber,
      startedAt: state.currentRun.startedAt,
      identity: null,
      topology: []
    };
    let caughtError = null;
    try {
      await inspectDevice();
    } catch (error) {
      caughtError = error;
    } finally {
      await closeDevice();
      completeRun(caughtError);
      state.busy = false;
      dom.action.disabled = false;
      dom.action.textContent = state.runs.length >= RUN_LIMIT ? "Run another descriptor inspection" : "Run after physical reconnect";
      dom.downloadReport.hidden = state.runs.length === 0;
    }
  }

  function reportEnvironment() {
    const context = parseUserAgent();
    return {
      browser: context.browser,
      platform: context.platform,
      architecture: context.architecture,
      macVersion: context.macVersion
    };
  }

  function firstObservedIdentity() {
    return selectedRuns()[0]?.identity?.usb || {
      vendorId: null,
      productId: null,
      manufacturerName: "",
      productName: "",
      serialNumberPresent: false
    };
  }

  function redactRun(run) {
    return {
      runNumber: run.runNumber,
      startedAt: run.startedAt,
      finishedAt: run.finishedAt,
      status: run.status,
      steps: run.steps,
      identity: run.identity,
      configurations: run.configurations,
      analysis: run.analysis,
      error: run.error || null
    };
  }

  function downloadJson(filename, payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadReport() {
    const identity = firstObservedIdentity();
    const runs = selectedRuns();
    const payload = {
      testTimestamp: new Date().toISOString(),
      environment: reportEnvironment(),
      vendorId: identity.vendorId,
      productId: identity.productId,
      manufacturerName: identity.manufacturerName,
      productName: identity.productName,
      serialNumberPresent: identity.serialNumberPresent,
      configurations: runs[0]?.configurations || [],
      candidateAnalysis: runs[0]?.analysis || [],
      runs: state.runs.map(redactRun),
      stability: {
        usbIdentity: runs.length >= RUN_LIMIT ? "evaluated in UI" : "not enough runs",
        descriptorTopology: runs.length >= RUN_LIMIT ? "evaluated in UI" : "not enough runs"
      },
      classification: state.classification,
      safety: {
        interfaceClaimCalls: 0,
        mtpCommandsSent: 0,
        usbDataOperations: 0,
        deviceMutationCounts: {
          created: 0,
          changed: 0,
          removed: 0
        }
      },
      redaction: "Raw serial values, personal filenames, object content and account data are not included."
    };
    downloadJson(`terento-fenix8-descriptors-${new Date().toISOString().replace(/[:.]/g, "-")}.json`, payload);
  }

  function downloadPrivateRecord() {
    const privateRuns = privateSelectedRuns();
    const withSerial = privateRuns.filter(run => run.identity.rawSerialNumber);
    if (!withSerial.length) {
      dom.privateMessage.textContent = "No raw serial was exposed by the selected device.";
      return;
    }
    const first = withSerial[0];
    const last = withSerial[withSerial.length - 1];
    const payload = {
      recordType: "Terento private physical device identity",
      createdAt: new Date().toISOString(),
      physicalDevice: {
        vendorId: first.identity.vendorId,
        productId: first.identity.productId,
        serialNumber: first.identity.rawSerialNumber,
        firstSeen: first.startedAt,
        lastSeen: last.finishedAt || last.startedAt,
        runNumbers: withSerial.map(run => run.runNumber)
      },
      note: "LOCAL ONLY. Never share, commit, push, or include this file in a redacted diagnostic report."
    };
    downloadJson(`terento-private-fenix8-device-${new Date().toISOString().replace(/[:.]/g, "-")}.json`, payload);
    dom.privateMessage.textContent = "Private record downloaded locally. Keep it outside Git and never share it.";
  }

  function setupBrowserState() {
    const available = Boolean(navigator.usb);
    setStatus(dom.apiStatus, available ? "PASS" : "FAIL");
    setStatus(dom.apiResult, available ? "PASS" : "FAIL");
    dom.browserMessage.textContent = available
      ? "WebUSB is available. This stage will inspect descriptors only."
      : "WebUSB is unavailable. Use Google Chrome on macOS for this diagnostic.";
    updateEnvironment(null);
    if (!available) dom.action.disabled = true;
    if (navigator.usb) {
      navigator.usb.addEventListener("disconnect", eventData => {
        if (state.device && eventData.device === state.device) {
          setFlowMessage("The watch disconnected. This run is closed; reconnect before the next inspection.");
        }
      });
    }
  }

  dom.action.addEventListener("click", run);
  dom.downloadReport.addEventListener("click", downloadReport);
  dom.downloadPrivate.addEventListener("click", downloadPrivateRecord);
  setupBrowserState();
})();
