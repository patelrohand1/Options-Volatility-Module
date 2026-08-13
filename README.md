# Institutional Options Volatility Surface & Risk Analytics Desk

## 🏢 Project Overview
This production-grade quantitative derivatives platform reverse-engineers option market pricing structures, maps multi-metric portfolio risk profiles, and scans for statistical relative value edge. 

The platform features a custom high-performance numerical optimization engine to solve for implied volatility, computes position risk Greeks, and exposes a web-hosted risk-management terminal with a built-in mathematical market simulator for fault tolerance.

Live Deployed URL: [Insert your live Streamlit Cloud link here]

---

## 🏗️ Core Architecture & Platform Features

The workspace is organized into a modular execution environment separating computational pricing logic from UI state and layout logic:

### 1. 📊 3D Market Topology Surface
* **Purpose**: Maps scattered real-world or synthetic option contracts onto a uniform mathematical plane.
* **Mechanism**: Uses **linear mesh-grid interpolation** via `scipy.interpolate.griddata` to cast unevenly distributed strike/maturity coordinates onto an evenly spaced grid.
* **Dynamic Visualization**: Allows risk desks to toggle the 3D surface rendering dynamically across three core risk parameters:
  * **Implied Volatility Surface:** Maps the market's pricing landscape, visually rendering structural out-of-the-money premium "skews." Notice the structural "smirk" shape, reflecting higher demand for crash protection (OTM puts).
  * **Option Delta Plane:** Tracks directional price exposure sensitivity. Functions as an institutional proxy for the probability of expiring in-the-money, visually representing the slope break as strikes cross the at-the-money boundary.
  * **Option Gamma Ridge:** Isolates option risk acceleration. Maps the volatile "Gamma wall" peaks faced by near-term at-the-money market makers where hedge rebalancing is most aggressively required.

### 2. 📈 2D Volatility Skew Slicer
* **Purpose**: Isolates a discrete expiration date to extract a single cross-section of the surface topology.
* **Mechanism**: Filters the surface matrix by `ExpirationDate` and sorts by `Strike` to plot the continuous **Volatility Smile / Skew** using Plotly splines.
* **Analysis**: Highlights structural pricing asymmetries between downside protection (hedging insurance) and upside spec call premiums. Traders monitor this spline for "kinks"—individual strikes that deviate sharply from the curve, marking mispriced relative value (RV) opportunities.

### 3. ⚡ Macro Scenario Stress Testing Engine
* **Purpose**: Models dynamic risk drift by running macro simulations on an At-The-Money (ATM) options inventory matrix.
* **Mechanism**: Filters contracts within $\pm 5\%$ of the current spot price.
* **Shock Inputs**: Accepts manual adjustments for systemic market shifts:
  * **Spot Shocks**: $-15\%$ to $+15\%$
  * **Volatility Shifts**: Absolute IV point changes from $-10\%$ to $+20\%$.
* **Output**: The engine instantly recalculates Black-Scholes pricing and Greeks on the shocked inputs, projecting updated capital evaluations, portfolio Delta drift, and Gamma shifts, allowing the risk desk to quantify potential blowout exposure.

### 4. ⚙️ Volatility Risk Premium (VRP) Engine & RV Scanner
* **VRP Tracker**: 
  * Computes 20-day annualized realized historical volatility (HV) via geometric log returns on the underlying asset's historical close prices.
  * Nets Realized Volatility against the mean At-The-Money Implied Volatility.
  * **Signal**: A positive Net VRP suggests options are structurally overvalued (short volatility execution favored); a negative VRP suggests options are cheap (long gamma execution favored).
* **Surface Dislocation Scanner**: 
  * Evaluates standard Z-score deviations of individual option contracts against the dataset's Implied Volatility mean.
  * Automatically isolates and flags statistically "Rich" (Sell targets, Z-score > 1.5) or "Cheap" (Buy targets, Z-score < -1.5) opportunities.

---

## 🧮 Mathematical Engine Framework (`black_scholes.py`)

### 1. The Black-Scholes Option Pricing & Greek Models
Theoretical pricing baseline and localized exposure matrices are solved via continuous probability density modeling:

$$d_1 = \frac{\ln(S/K) + (r + \frac{\sigma^2}{2})T}{\sigma\sqrt{T}}$$

$$d_2 = d_1 - \sigma\sqrt{T}$$

$$\text{Price}_{\text{Call}} = S \cdot N(d_1) - K \cdot e^{-rT} \cdot N(d_2)$$

$$\text{Delta } (\Delta_{\text{Call}}) = N(d_1)$$

$$\text{Gamma } (\Gamma) = \frac{N'(d_1)}{S \cdot \sigma\sqrt{T}}$$

*Where: $S$ = Spot Price, $K$ = Strike Price, $T$ = Annualized Time to Maturity, $r$ = Risk-Free Rate, $\sigma$ = Implied Volatility, $N(x)$ = Cumulative Normal Distribution, and $N'(x)$ = Standard Normal Probability Density Function.*

### 2. Implied Volatility Numerical Optimization
Because the Black-Scholes formula cannot be algebraically isolated for $\sigma$, the pricing engine executes a high-performance **Newton-Raphson numerical optimization loop** to reverse-engineer IV from live market premiums.

* **Iteration Step**: The engine calculates the price error against a baseline option premium and updates the guess iteratively using the slope of Vega ($\text{Vega} = S \cdot N'(d_1) \sqrt{T}$):
  $$\sigma_{n+1} = \sigma_n - \frac{\text{Price}_{\text{BS}}(\sigma_n) - \text{Price}_{\text{Market}}}{\text{Vega}(\sigma_n)}$$
* **Edge-Case Safeguards**:
  * **Intrinsic Guard**: If the market price is at or below intrinsic value ($S - K$), the engine short-circuits and returns 0 to prevent infinite loops.
  * **Zero-Vega Fallback**: If Vega approaches zero (e.g., in deep OTM or deep ITM contracts), division by nearly zero would cause the solver to explode. The engine intercepts this and applies a manual step increment ($0.05$) in the direction of the price error to safely traverse flat gradient regions.

---

## 📡 Live Data Pipeline & Fallback Systems (`app.py`)

### 1. Live Exchange Feed Ingestion
* **Source**: `yfinance` API fetching options chains directly from CBOE feeds.
* **Extraction & Formatting**:
  * Calculates Mid-Price using `(Bid + Ask) / 2`.
  * Computes Time to Maturity ($T$) in annualized fractions based on exact calendar days remaining.
* **Liquidity Filtering**:
  * Discards contracts with volume $< 5$ or premiums $< \$0.30$ to prevent wide bid-ask spreads from generating noisy implied volatility spikes.
  * Discards extreme outlier strikes outside a $\pm 15\%$ boundary of the current spot price, focusing the computational mesh on the liquid core surface.

### 2. Fault-Tolerant Synthetic Volatility Engine
To safeguard against public cloud API request throttling (`YFRateLimitError`) caused by shared IP pools, the platform features an automated **Synthetic Volatility Engine**. 

If an API restriction occurs, the system intercepts the exception (`try/except` block) and instantly deploys a mathematical surface simulation to preserve full analytical functions:
* **Term Structure Model**: Generates volatility contango, slightly increasing baseline ATM volatility for later expirations.
* **Institutional Skew Model (Asymmetric Smirk)**: Uses a parabolic equation mapped against Log Moneyness ($\ln(K/S)$):
  $$\text{IV} = \text{ATM\_Vol} + (\text{Skew\_Slope} \cdot \text{Moneyness}) + (\text{Convexity} \cdot \text{Moneyness}^2)$$
  The skew slope is negative (to price downside crash protection higher) and convexity is positive (creating the extreme tail "smile"), accurately mirroring institutional S&P 500 options behavior.

---

## 📁 Repository Directory Structure

* `app.py`: The frontend application script utilizing Streamlit. Handles data caching (`@st.cache_data`), synthetic fallback generation, UI grids/tabs, and Plotly visualization renders.
* `black_scholes.py`: The core quantitative library executing analytical option values, risk Greek distributions, and the Newton-Raphson root-finding loop. Completely decoupled from the UI for high-performance execution.
* `requirements.txt`: The isolated dependency configuration matrix ensuring clean virtual machine image builds.
* `.gitignore`: Excludes virtual environments (`.venv`), macOS `DS_Store` files, and `__pycache__` artifacts from source control.

---

## 🚀 Local Development & Deployment Guide

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/options-vol-surface.git
cd options-vol-surface

# Initialize a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install exact dependencies
pip install -r requirements.txt
```

### 2. Launching the Risk Desk
```bash
streamlit run app.py
```
The terminal will launch the interactive quantitative risk desk in your default web browser at `http://localhost:8501`.
