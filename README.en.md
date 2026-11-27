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
| Read saved experiments | Inspect settings, list runs and units, extract samples, and read saved graph bindings and fits. |
| Analyze measurements | Plot paired samples, run linear regression and compare run statistics. |
| Operate Capstone | Inspect windows and controls, capture screenshots, send input, save to a new path and export CSV. |
| Work with displays | Manage graphs, tables, Digits, Scope, FFT and workbook layouts. Results indicate which settings and values were observed. |
| Work with instruments | Select sensors and supported rates, configure timers, or request a manual sample. Confirm zeroing, calibration and 850/550 generator output on the actual equipment. |
| Analyze physics experiments | Analyze supplied photoelectric, RLC, forced oscillation, adiabatic gas or slit diffraction measurements. Generate Markdown and HTML reports from recorded data. |

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
        "run", "--no-sync", "capstone-mcp"
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
uv run --no-sync capstone-mcp-http
```

Register `http://127.0.0.1:8766/mcp` as the MCP server URL in your client and keep the terminal running. The server listens only on the local loopback address.

</details>

### 3. Try your first request

Ask your assistant to inspect an experiment file. Paths refer to files on the **Windows PC running the MCP server**.

> Show me the datasets in `C:/Experiments/momentum.cap`, including their names, unit information, and sample counts.

Replace the example path with an existing `.cap` file. To operate the app instead, open an experiment in Capstone and ask: “Connect to the running Capstone app and show me its current windows.”

## Example requests

- **Saved experiment** — “Show the runs and units, then give me the first 20 paired time and velocity samples from a recorded run.”
- **Graphs** — “Read the axes, run and fit coefficients from the second saved graph.” For changes to an open graph, observe the current window and verify native fit status after the change.
- **Export before saving** — “Export this experiment to a new file, `C:/Experiments/current.csv`, and show the first 20 rows.”
- **Photoelectric effect** — “Estimate Planck’s constant using my recorded wavelengths in nm and stopping voltages in V.”
- **Live readings** — “Read the current value and unit from the connected force sensor.” Live measurement queries require the same Capstone process to own the local debugging port. [Setup in Korean](docs/usage.md#실시간-조회)

## Things to know

- UI operations may bring Capstone to the foreground. Use an unlocked desktop and avoid simultaneous control from multiple clients.
- Saving and exporting never overwrite an existing file. Saving a new `.cap` file also changes the active experiment's file path.
- CSV uses Capstone's display precision and aligns data by index, not necessarily by time. Extract values from a saved `.cap` file when you need the stored numerical precision.
- Graph creation, axis selection, and 23 built-in fitting models operate directly on Capstone pages. Repeating the same model configuration does not toggle existing fits off.
- Read saved graphs from the file. For an unsaved graph the server checks ownership of the native Copy Display result and restores supported clipboard formats while the copied generation is still current.
- If native automation times out, the worker process is stopped without replaying the input. Check the app's recording and save state before reconnecting with `capstone_attach`.
- The server uses internal interfaces and UI controls. Compatibility may vary with the Capstone version and screen configuration.

Tool-level workflows and troubleshooting are available in the **[user guide (Korean)](docs/usage.md)**.
