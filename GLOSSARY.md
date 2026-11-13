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
