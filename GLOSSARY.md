# Domain Glossary

Domain concepts and terms used across the `capstone-mcp` project.

### Capstone
The official PASCO Capstone Windows desktop application used for physics and science experimentation, sensor data collection, and graphing.

### Run (회차)
A single execution or trial of data recording within an experiment. Named sequentially by default (`Run #1`, `Run #2`) in the Data Summary tree.

### Data Summary
The panel in Capstone listing connected interfaces, sensors, available runs, and their constituent datasets.

### Calculator
The formula creation and calculation workspace in Capstone where mathematical expressions and variable relationships (e.g., `[Position (m)]`) are defined.

### Dataset
A column or array of numeric data points (such as Time, Voltage, Current, Position) produced by a sensor or formula for a specific Run.

### Scale to Fit
The graph tool in Capstone that automatically adjusts the X and Y axis bounds to fully display all visible data points.

### Graph
The primary 2D data visualization display in Capstone displaying continuous or discrete measurements along horizontal and vertical axes, supporting curve fitting and toolbox tools.

### Curve Fit
Mathematical model fitting (Linear, Quadratic, Polynomial, Sine, etc.) applied to experimental data points in a graph to extract physical parameters.

### Toolbox
The Qt-based floating smart toolbar (`ZSmartToolBox`) positioned over a graph display, housing tools for delta coordinates, statistics, area integration, and auto-scaling.

### CDP (Chrome DevTools Protocol)
The WebSocket debugging protocol exposed by Capstone's internal QtWebEngine / Chromium instance on port 9222, providing high-speed telemetry and direct JavaScript/C++ RPC inspection.

### QWebChannel
Qt's IPC bridge bridging native C++ objects (`javascriptBridge`) with the embedded webview, hosting 53 native RPC methods under `window.app.mSenseAndControlView.mServices`.

### UnifiedSessionManager
Central coordinator in `capstone_mcp.session` managing desktop UIA interactions and high-speed CDP WebSocket telemetry (< 15 ms).

### Fast-Path Telemetry
Direct WebSocket polling for sensor inventories and instantaneous values without UI automation overhead.

### Stop Condition Trigger
Automated threshold monitor halting data recording when sensor values exceed or cross specified mathematical boundaries (`StopCondition`).

### UI Escape Hatch (`capstone_interact_ui`)
Consolidated fallback tool providing raw mouse and keyboard UIA activations across invoke, click, drag, scroll, and key typing without polluting the top-level tool catalog.

