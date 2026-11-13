# Capstone Native Reverse Engineering & RPC Boundary Findings

## 1. Executive Summary

- **Target Application**: PASCO Capstone v2.13.4 (x64)
- **Architecture**: Hybrid Desktop Application (C++ / Qt 5.15.15 with QtWebEngine / Chromium 87.0.4280.144 and QWebChannel)
- **Investigation Objective**: Evaluate the feasibility of replacing Windows UI Automation (pywinauto / UIA) with Chrome DevTools Protocol (CDP) WebSocket communication and native QWebChannel RPC calls.
- **Key Results**:
  - Successfully connected to Capstone via CDP WebSocket on port 9222 (`ws://127.0.0.1:9222/devtools/page/...`).
  - Extracted the complete runtime object tree (`window.app`, `window.javascriptBridge`, `QWebChannel`) into `docs/reverse_engineering_dump.json`.
  - Cataloged **53 native C++ RPC methods** available on `window.app.mSenseAndControlView.mServices`.
  - Established a definitive architectural boundary: **Telemetry, sensor inventory, and measurement polling can be 100% offloaded to CDP WebSocket (10–15 ms latency)**, whereas **Graph display creation, axis scaling, file dialogs, and run visibility must remain on Desktop UIA**.

---

## 2. Launch & Remote Debugging Configuration

### 2.1 Process Invocations
When starting Capstone, `src/capstone_mcp/desktop.py` automatically injects the following command line flags and environment variables:

```python
DEFAULT_DEBUG_PORT: Final = 9222
CHROMIUM_DEBUG_FLAGS: Final = (
    f"--remote-debugging-port={DEFAULT_DEBUG_PORT}",
    "--remote-allow-origins=*",
)
```

In addition, the environment variable `QTWEBENGINE_REMOTE_DEBUGGING=9222` is recognized by Qt 5.15.

### 2.2 Target Discovery & Runtime Metadata
Querying `http://127.0.0.1:9222/json/version` yields:

```json
{
   "Browser": "PASCO Capstone/2.13.4",
   "Protocol-Version": "1.3",
   "User-Agent": "Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/5.15.15 Chrome/87.0.4280.144 Safari/537.36",
   "V8-Version": "8.7.220.39",
   "WebKit-Version": "537.36 (@38a74c624ca48a6acb2a6f427998be599b504eed)",
   "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/fddb6c5a-5419-48b1-80f4-e37575cc6428"
}
```

Querying `http://127.0.0.1:9222/json/list` returns exactly 1 active page target:
- **Type**: `page`
- **Title**: `"Sense and Control"`
- **URL**: `file:///C:/Program%20Files/PASCO%20scientific/Capstone/Resources/www/index.html`
- **WebSocket Endpoint**: `ws://127.0.0.1:9222/devtools/page/<GUID>`

---

## 3. Object Tree & Initialization Architecture

### 3.1 Webview Loading Lifecycle
1. QtWebEngine spins up an embedded Chromium renderer hosting `index.html`.
2. Qt injects `qt.webChannelTransport` before script execution.
3. The page loads dependencies:
   - `iscroll5.js`
   - `qwebchannel.js` (Qt 5.15 QWebChannel client)
   - `jquery.min.js`
   - `capstonelibrary.js` (PASCO proprietary frontend library, ~1.18 MB)
4. Upon script evaluation, `new QWebChannel(qt.webChannelTransport, ...)` establishes `window.javascriptBridge`.
5. The native C++ Capstone core invokes `window.initialize(lang, strings, ...)`, which constructs the controller `_e` and binds it to `window.app`.

### 3.2 Top-Level `window.app` Structure

| Field | Type | Description |
|---|---|---|
| `mSenseAndControlView` | `Object` | Main controller for code tools and hardware messaging |
| `mSenseAndControlView.mServices` | `Object` | Gateway exposing 53 C++ RPC methods |
| `mSenseAndControlView.mServices.mViewModelServices` | `Object` | Low-level IPC proxy communicating with `ViewModelHandler` |
| `mLuaDiv`, `mJavascriptDiv`, `mPascodeDiv` | `jQuery Element` | Code editor DOM containers |
| `mToggleExecutionButton` | `jQuery Element` | UI toggle for code execution state |
| `mControlNodeDropdownList` | `Array` | Discovered PASCO Control Nodes |

---

## 4. Supported RPC Methods Catalog

Inspection of `Object.getOwnPropertyNames(Object.getPrototypeOf(window.app.mSenseAndControlView.mServices))` reveals 53 native RPC methods:

### 4.1 Hardware Telemetry & Measurement
- **`RequestSensorsAndMeasurements()`**:
  - Queries all connected sensors and active measurement channels.
  - Return shape:
    ```json
    {
      "accessories": [],
      "codableInterfaces": [],
      "codeNodes": [],
      "controlNodes": [],
      "measurements": [ ... ],
      "outputs": [],
      "sensors": [ ... ]
    }
    ```
  - **Latency**: ~12 ms RTT over CDP WebSocket.
- **`RequestReadMeasurement(measurementEUID, unitType)`**:
  - Reads instantaneous sensor value.
  - Return shape: `{"ReturnValue": 12.34, "cmdResult": true}`.
  - **Latency**: ~8 ms RTT.
- **`RequestCreateNumericMeasurement()`, `RequestWriteNumericMeasurementValue()`**:
  - Dynamically injects numeric measurement channels into Capstone's data model.
- **`RequestCreateTextMeasurement()`, `RequestWriteTextMeasurmentValue()`**:
  - Injects textual annotations / metadata into runs.
- **`RequestRenameCodeOutputMeasurement()`, `RequestRemoveCodeOutputMeasurement()`**:
  - Manages custom calculated or code-derived output columns.

### 4.2 Sensor & Accessory References
- `RequestAddMeasurementReference()`, `RequestRemoveMeasurementReference()`
- `RequestAddSensorReference()`, `RequestRemoveSensorReference()`
- `RequestAddOutputReference()`, `RequestRemoveOutputReference()`
- `RequestAddAccessoryReference()`, `RequestRemoveAccessoryReference()`
- `RequestAddInterfaceReference()`, `RequestRemoveInterfaceReference()`
- `RequestAddDualStepperReference()`, `RequestAddPowerOutputReference()`, `RequestAddGrowLightReference()`

### 4.3 Code Execution & Logic
- `RequestStartLua()`, `RequestStopLua()`: Starts/stops embedded Lua execution engine.
- `RequestSetBlocklyXML()`, `RequestGetBlocklyXML()`: Sets/retrieves Blockly block graphs.
- `RequestCopyBlocks()`, `RequestPasteBlocks()`, `RequestPrepareExportBlocks()`, `RequestCompleteExportBlocks()`.
- `RequestUploadPascode()`, `RequestStartStopPascode()`, `RequestClearPascode()`: Controls Pascode firmware targets.
- `RequestSetExecutionEnabled()`, `RequestGetExecutionEnabled()`: Global code run switch.

### 4.4 Internal IPC Handlers
- **`ViewModelHandler`**:
  - `Method_CreateViewModel` (`-1`)
  - `Method_ViewModelRequest` (`-2`)
  - `Method_ViewModelRequestPromise` (`-3`)
- **`FileHandler`**:
  - `FileHandlerGetApplicationPaths` (`-5`)
  - `FileHandlerReadImageDataBase64` (`-6`)
  - `FileHandlerOpenFileChooser` (`-7`)
  - `FileHandlerCopy` (`-8`)

---

## 5. Architectural Boundary: WebChannel vs. Desktop UIA

| Functional Area | Preferred Path | Rationale & Technical Boundary |
|---|:---:|---|
| **Sensor Discovery** | **WebChannel (CDP)** | Direct C++ RPC (`RequestSensorsAndMeasurements`) returns structured JSON in < 15 ms without opening UI dialogs. |
| **Live Value Polling** | **WebChannel (CDP)** | `RequestReadMeasurement` polls instantaneous values in < 10 ms without screen capture or OCR. |
| **User Code / Script Injection** | **WebChannel (CDP)** | `RequestStartLua` / `RequestSetBlocklyXML` injects algorithmic logic directly into the native runtime. |
| **Graph Creation & Placement** | **Desktop UIA** | Graphs are native Qt C++ widgets (`QGraphicsView` / `QWidget`) outside the Chromium DOM. No WebChannel API exists for creating display widgets. |
| **Axes & Fitting Configuration** | **Desktop UIA** | Toolbars, fit popups, and coordinate cursors are native Qt controls. |
| **Display Layout Management** | **Desktop UIA** | Workbook pages, tile arrangements, Digits, Table, and Scope displays require UIA activation. |
| **Project File (.capstone) I/O** | **Desktop UIA** | Open/Save workflows invoke standard Windows / Qt File Dialogs requiring UIA automation. |
| **Run Lifecycle (Visibility/Delete)**| **Desktop UIA** | Run visibility checkboxes and run deletion are managed inside the native Table/Tree widgets. |
| **Bluetooth / USB Hardware Pairing**| **Desktop UIA** | Pairing modal dialog is part of native Qt desktop UI (`Hardware Setup`). |

---

## 6. Implementation Strategy for Phase 9 Ticket 6

1. **CDP Integration in `UnifiedSessionManager`**:
   - `bridge.py` is established as the primary fast-path for all sensor read operations.
   - Fallback to UIA is preserved if CDP port 9222 is inaccessible or blocked.
2. **Resource Protocol `capstone://measurements/live`**:
   - Ticket 6 will implement a real-time polling resource on top of `bridge.read_inventory()` and `bridge.read_measurement()`.
3. **Headless Test Guard**:
   - Live smoke tests must check for Capstone executable existence (`HAS_CAPSTONE`) and skip gracefully in headless CI environments.
