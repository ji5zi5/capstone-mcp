<h1 align="center">PASCO Capstone MCP</h1>

<p align="center">Control Capstone experiments and analyze data through your AI assistant.</p>

<p align="center"><a href="README.md">한국어</a> · <strong>English</strong></p>

<p align="center">
  <a href="#getting-started">Getting started</a> &nbsp;·&nbsp;
  <a href="#example-requests">Example requests</a> &nbsp;·&nbsp;
  <a href="docs/usage.md">User guide (Korean)</a>
</p>

---

PASCO Capstone MCP is an unofficial MCP server that lets an AI client **operate PASCO Capstone, extract experiment data, and perform numerical analysis** on your Windows PC. It exposes these tools through the Model Context Protocol (MCP).

Use it to analyze saved `.cap` files or work with an open experiment, from sensor configuration to measurement control. Analyzing saved files does not require the Capstone app to be running.

## What can it do?

| Task | Capabilities |
| :--- | :--- |
| **Analyze experiment files** | Inspect sensor and experiment settings, extract datasets, create scatter plots, fit lines, and compare runs |
| **Operate the Capstone interface** | Inspect windows and controls, click, type, drag, scroll, and capture screenshots |
| **Save and export data** | Save to a new `.cap` file or export data to CSV without saving the experiment first |
| **Configure sensors and control recording** | Select sensors by name, set supported sampling rates, start and stop recording, and schedule repeated runs |

> File analysis, UI operations, sensor settings, saving, and exporting have been checked against the app. Acquisition and repeated runs with physical sensors have not yet been verified.

## Getting started

### 1. Install

You need Windows, Git, [uv](https://docs.astral.sh/uv/), and an AI client that supports MCP servers. The project requires Python 3.12 or later.

To operate the app, PASCO Capstone must be installed at the following path. App attachment currently uses this fixed location.

```text
C:/Program Files/PASCO scientific/Capstone/Capstone.exe
```

Clone the repository and install dependencies in PowerShell:

```powershell
git clone https://github.com/ji5zi5/capstone-mcp.git
cd capstone-mcp
uv sync --python 3.12
```

### 2. Connect your AI client

Add this entry to your client's MCP configuration. Replace `C:/Projects/capstone-mcp` with the **absolute path to your local clone**. The configuration file location or setup screen depends on your client.

```json
{
  "mcpServers": {
    "capstone": {
      "command": "uv",
      "args": [
        "--directory", "C:/Projects/capstone-mcp",
        "run", "capstone-mcp"
      ]
    }
  }
}
```

Apply the configuration or restart the client. Check that the `capstone` server and tools such as `capstone_file_datasets` appear. With this setup, your client starts the server; you do not need to keep a separate server terminal open.

<details>
<summary><strong>Using Streamable HTTP instead</strong></summary>

Run the server from the repository folder:

```powershell
uv run capstone-mcp-http
```

Register `http://127.0.0.1:8766/mcp` as the MCP server URL in your client and keep the terminal running. The server listens only on the local loopback address.

</details>

### 3. Try your first request

Ask your assistant to inspect an experiment file. Paths refer to files on the **Windows PC running the MCP server**.

> Show me the datasets in `C:/Experiments/momentum.cap`, including their names, unit information, and sample counts.

Replace the example path with an existing `.cap` file. To operate the app instead, open an experiment in Capstone and ask: “Connect to the running Capstone app and show me its current windows.”

## Example requests

The MCP exposes workflow instructions, strict graph-request schemas, and tool annotations. Read the graph and a fresh screenshot before fitting; pass its `data_signature` as `expected_data_signature` to reject changed source/run/unit bindings. This signature does not detect live sample changes or a moved graph. Results include explicit native solver status and a machine-readable next action.

Saved-file and explicit-sample OLS also return residual, leverage, Cook's-distance, and adjacent-residual-correlation diagnostics. Per-sample arrays are limited to the first 256 observations, with explicit truncation metadata; calculations use all observations. Influence flags are descriptive, not significance tests or instructions to remove data. These diagnostics are computed by the MCP, not Capstone's native solver.

**Analyze data**

> Add a graph to the open Capstone experiment, select data from the same run, and compare linear and quadratic fits. Report Capstone's own coefficients and errors.

**Export data before saving**

> Export the current experiment data to `C:/Experiments/current.csv` and show the first 20 rows.

**Configure a sensor**

> List the sensors in this experiment, then set the sensor I choose to 100 Hz.

**Record repeated runs**

> Record three runs of five seconds each, with a two-second pause between runs. Save each run's experiment snapshot in a new folder, `C:/Experiments/session-01`.

Choose sensor names, supported rates, dataset runs, and units based on the actual experiment. For individual saves and CSV exports, create the destination folder first and choose a filename that does not already exist.

<details>
<summary><strong>Setup for live queries and repeated recording</strong></summary>

Live configuration/current-value queries and repeated recording require a debugging port. Save your work and close Capstone, then launch it from PowerShell:

```powershell
$env:QTWEBENGINE_REMOTE_DEBUGGING = "127.0.0.1:9223"
Start-Process "C:/Program Files/PASCO scientific/Capstone/Capstone.exe"
Remove-Item Env:QTWEBENGINE_REMOTE_DEBUGGING
```

Repeated recording also requires a configured, enabled recording source. The process ID, window handle, and debugging port must belong to the same Capstone instance.

For automatic saving, set `plan.capture.directory` to a new or empty folder. The server saves `baseline.cap` before recording and `run-001.cap`, `run-002.cap`, and so on after each stopped run. These are snapshots of the entire experiment.

To fit newly acquired samples automatically, set `plan.capture.fit.x_source_euid` and `y_source_euid` to the selected measurement source IDs. Use the returned `job_id` to check completion or request cancellation. A cancellation request does not itself confirm that recording has stopped.

This extra launch configuration is not needed for ordinary UI operations, saved-file analysis, saving, or CSV export.

</details>

## Things to know

- UI operations may bring Capstone to the foreground. Use an unlocked desktop and avoid simultaneous control from multiple clients.
- Saving and exporting never overwrite an existing file. Saving a new `.cap` file also changes the active experiment's file path.
- CSV uses Capstone's display precision and aligns data by index, not necessarily by time. Extract values from a saved `.cap` file when you need the stored numerical precision.
- Graph creation, axis selection, and 23 built-in fitting models operate directly on Capstone pages. Repeating the same model configuration does not toggle existing fits off.
- Graph verification uses Capstone's Copy Display data and replaces the Windows clipboard with the selected graph. Coefficients, uncertainties, metrics, and run IDs come from Capstone itself. Custom-expression editing is not included.
- If native automation times out, the worker process is stopped without replaying the input. Check the app's recording and save state before reconnecting with `capstone_attach`.
- The server uses internal interfaces and UI controls. Compatibility may vary with the Capstone version and screen configuration.

Tool-level workflows and troubleshooting are available in the **[user guide (Korean)](docs/usage.md)**.
