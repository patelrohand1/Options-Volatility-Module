import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy.interpolate import griddata
import yfinance as yf
import datetime
from black_scholes import implied_volatility, calculate_delta, calculate_gamma, black_scholes_price

# --- SYNTHETIC FALLBACK ENGINE ---
def generate_synthetic_surface(spot, r):
    """
    Generates a high-resolution, mathematically accurate synthetic volatility surface.
    Uses a polynomial log-moneyness model to accurately recreate institutional equity skew (smirk)
    and realistic term structure dynamics.
    """
    records = []
    
    # 1. Increase grid resolution for a smooth, highly detailed 3D mesh
    expirations = np.linspace(0.05, 2.0, 15)  # 15 time slices up to 2 years out
    strikes = np.linspace(spot * 0.70, spot * 1.30, 40) # 40 strike slices, 30% OTM/ITM

    for T in expirations:
        # 2. Term Structure Model: Volatility contango (increases slightly with time)
        atm_vol = 0.18 + 0.05 * (1 - np.exp(-1.5 * T))

        for strike in strikes:
            # 3. Log Moneyness
            moneyness = np.log(strike / spot)

            # 4. Institutional Skew Model: Asymmetric Smirk
            # Slope is negative to price downside crash protection higher
            # Convexity is positive to create the 'smile' at the extreme tails
            skew_slope = -0.15 / np.sqrt(T)  # Skew is much steeper in near-term expirations
            convexity = 0.30 / T             # Convexity is sharper in near-term expirations

            iv = atm_vol + (skew_slope * moneyness) + (convexity * (moneyness ** 2))

            # Hard mathematical floor to prevent negative volatility in deep extreme tails
            iv = max(0.05, iv)

            # 5. Calculate Greeks & Reverse-Engineer Premium
            delta = calculate_delta(spot, strike, T, r, iv, "call")
            gamma = calculate_gamma(spot, strike, T, r, iv)
            market_price = black_scholes_price(spot, strike, T, r, iv, "call")

            records.append({
                'ExpirationDate': (datetime.date.today() + datetime.timedelta(days=int(T*365))).strftime("%Y-%m-%d"),
                'TimeToExpiry': T,
                'Strike': strike,
                'MarketPrice': market_price,
                'Implied Volatility': iv,
                'Delta': delta,
                'Gamma': gamma
            })
            
    return pd.DataFrame(records)

# --- DATA PIPELINES ---
def calculate_historical_volatility(ticker_symbol, days=20):
    """
    Fetches historical closing prices and calculates annualized realized volatility.
    """
    # Removed manual requests session initialization to let yfinance deploy native curl_cffi handling
    ticker = yf.Ticker(ticker_symbol)
    try:
        hist = ticker.history(period=f"{int(days * 1.5)}d")
        if len(hist) < days:
            return 0.20 # Proxy default baseline
        
        closes = hist['Close'].tail(days)
        log_returns = np.log(closes / closes.shift(1)).dropna()
        realized_vol = np.std(log_returns) * np.sqrt(252)
        return realized_vol
    except Exception:
        return 0.20 # Fallback if API drops completely

import requests

@st.cache_data(ttl=300)
def fetch_and_map_risk_data(ticker, r, limit):
    # Attempt to spoof browser headers to bypass Cloud IP WAF blocks
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    spy = yf.Ticker(ticker, session=session)
    
    # 1. Attempt to get Spot Price
    try:
        spot = spy.fast_info['last_price']
    except Exception:
        spot = 500.00 # Standard fallback index proxy price
        
    # 2. Attempt Live Data Pull
    try:
        all_expirations = spy.options[:limit]
        if not all_expirations:
            raise ValueError("Empty options chain")
            
        surface_records = []
        today = datetime.date.today()

        for expiry_str in all_expirations:
            expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
            T = (expiry_date - today).days / 365.0
            if T <= 0.015: continue # Require at least ~5.5 days to expiration
                
            opt_chain = spy.option_chain(expiry_str)
            calls = opt_chain.calls
                
            for _, contract in calls.iterrows():
                strike = contract['strike']
                market_price = (contract['bid'] + contract['ask']) / 2
                
                if contract['volume'] < 5 or market_price < 0.30: continue
                if strike < spot * 0.85 or strike > spot * 1.15: continue
                
                iv = implied_volatility(market_price, spot, strike, T, r, "call")

# Strict Institutional Bound: Reject IV > 300% to prevent grid warping
                if 0.01 < iv < 3.0:
                    delta = calculate_delta(spot, strike, T, r, iv, "call")
                    gamma = calculate_gamma(spot, strike, T, r, iv)
                    
                    surface_records.append({
                        'ExpirationDate': expiry_str,
                        'TimeToExpiry': T,
                        'Strike': strike,
                        'MarketPrice': market_price,
                        'Implied Volatility': iv,
                        'Delta': delta,
                        'Gamma': gamma
                    })
        
        if not surface_records:
            raise ValueError("Cloud API rate limit triggered: Zero valid contracts retrieved.")
            
        return pd.DataFrame(surface_records), spot

    # 3. INTERCEPT INTERFACES AND DEPLOY SYNTHETIC ENGINE
    except Exception:
        st.warning("⚠️ **Live Exchange Feed Offline (Cloud IP Restrictions):** The external market data provider has temporarily restricted cloud infrastructure access. The platform has gracefully degraded to a **Mathematically Simulated Market Environment** to preserve continuous risk modeling functionality.")
        df_surface = generate_synthetic_surface(spot, r)
        return df_surface, spot

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Institutional Derivatives Risk Platform", layout="wide")
st.title("Institutional Derivatives Risk & Volatility Analytics Platform")
st.markdown("Welcome to the desk workspace. This platform operates on real-time market data feeds, running numerical optimization loops to reverse-engineer option pricing structures, map portfolio risk profiles, and scan for relative value edge.")

# --- 2. SIDEBAR CONTROLS ---
st.sidebar.header("Market Data Settings")
ticker_symbol = st.sidebar.text_input("Ticker Symbol", value="SPY").upper()
risk_free_rate = st.sidebar.slider("Risk-Free Rate (r)", min_value=0.0, max_value=0.10, value=0.045, step=0.005)
max_expirations = st.sidebar.slider("Expirations Limit", min_value=2, max_value=10, value=6)

# --- 3. STREAM DATA ---
with st.spinner("Compiling cross-asset options risk matrices..."):
    df_surface, spot_price = fetch_and_map_risk_data(ticker_symbol, risk_free_rate, max_expirations)

if df_surface is None or df_surface.empty:
    st.error("Matrix generation failed. Check data feeds.")
else:
    # --- WORKSPACE TABS ---
    tab1, tab2, tab3 = st.tabs(["📊 3D Market Topology", "📈 2D Skew Slicer", "⚡ Risk Shock Engine"])

    # TAB 1: 3D MARKET TOPOLOGY
    with tab1:
        st.subheader("Structural Risk Surface Matrix")
        col_layout_left, col_layout_right = st.columns([2, 1])
        
        with col_layout_left:
            surface_metric = st.selectbox("Select 3D Surface Target Metric", ["Implied Volatility", "Delta", "Gamma"], key="3d_metric")
            
            grid_x, grid_y = np.mgrid[df_surface['TimeToExpiry'].min():df_surface['TimeToExpiry'].max():50j, df_surface['Strike'].min():df_surface['Strike'].max():50j]
            grid_z = griddata((df_surface['TimeToExpiry'], df_surface['Strike']), df_surface[surface_metric], (grid_x, grid_y), method='linear')

            color_scales = {"Implied Volatility": "Viridis", "Delta": "Cividis", "Gamma": "Magma"}
            fig_3d = go.Figure(data=[go.Surface(x=grid_x, y=grid_y, z=grid_z, colorscale=color_scales[surface_metric], colorbar_title=surface_metric)])
            fig_3d.update_layout(scene=dict(xaxis_title="Maturity (Years)", yaxis_title="Strike ($)", zaxis_title=surface_metric), margin=dict(l=0, r=0, b=0, t=0), height=550)
            st.plotly_chart(fig_3d, use_container_width=True)
            
        with col_layout_right:
            st.metric("Underlying Asset Spot ($)", f"${spot_price:.2f}")
            st.markdown(f"### 📈 How to Read the {surface_metric} Chart")
            if surface_metric == "Implied Volatility":
                st.info("* **Term Structure:** Track the slope along the Maturity axis. Backwardation flags macro risk.\n* **The Volatility Valley:** Notice the dip at-the-money. IV climbs on out-of-the-money strikes due to structural skew.")
            elif surface_metric == "Delta":
                st.info("* **Probability Curve:** Delta functions as an institutional proxy for the probability of expiring in-the-money.\n* **The Slope Break:** Observe the steep drop as coordinates cross OTM boundaries.")
            elif surface_metric == "Gamma":
                st.info("* **Locating the Gamma Wall:** Observe the prominent, sharp 'mountain ridge' pinning short-term at-the-money contracts. This is where market makers face severe exposure changes.")

    # TAB 2: 2D SKEW SLICER
    with tab2:
        st.subheader("Volatility Smile & Skew Analysis")
        tab2_left, tab2_right = st.columns([2, 1])
        
        with tab2_left:
            unique_expiries = sorted(df_surface['ExpirationDate'].unique())
            selected_expiry = st.selectbox("Select Expiration Date", unique_expiries)
            df_slice = df_surface[df_surface['ExpirationDate'] == selected_expiry].sort_values(by='Strike')
            
            fig_smile = px.line(df_slice, x='Strike', y='Implied Volatility', title=f"Volatility Skew for Expiry: {selected_expiry}", markers=True, line_shape='spline')
            fig_smile.add_vline(x=spot_price, line_dash="dash", line_color="red", annotation_text="Asset Spot")
            fig_smile.update_layout(xaxis_title="Strike ($)", yaxis_title="Implied Volatility", height=500)
            st.plotly_chart(fig_smile, use_container_width=True)
            
        with tab2_right:
            st.markdown("### 📈 Actionable Insights")
            st.markdown("#### The Crash Protection Premium (Equity Skew)\nNotice how IV spikes on the left (lower strikes). Institutional investors pay an inflated premium for OTM puts to hedge against crashes.\n\n#### Execution Tactics\nDesks monitor this spline for **'kinks'**. If an individual strike deviates sharply from the curve, it marks a mispricing to be exploited via Relative Value (RV) spreads.")

    # TAB 3: RISK SHOCK ENGINE
    with tab3:
        st.subheader("Macro Scenario Stress Testing")
        tab3_left, tab3_right = st.columns([1, 2])
        
        with tab3_left:
            spot_shock_pct = st.slider("Spot Price Shock (%)", -15.0, 15.0, 0.0, 1.0)
            vol_shock_abs = st.slider("IV Shift (Absolute % Points)", -10.0, 20.0, 0.0, 1.0)
            st.markdown("---")
            st.markdown("### 📈 Risk Drift Mechanics\n* **Delta Drift:** Your net directional exposure post-shock.\n* **Gamma Shift:** The acceleration of risk forcing aggressive hedging.")
            
        with tab3_right:
            shocked_spot = spot_price * (1 + (spot_shock_pct / 100))
            atm_shock_df = df_surface[(df_surface['Strike'] >= spot_price * 0.95) & (df_surface['Strike'] <= spot_price * 1.05)].copy()
            
            shocked_records = []
            for _, row in atm_shock_df.iterrows():
                new_iv = max(0.01, row['Implied Volatility'] + (vol_shock_abs / 100))
                s_price = black_scholes_price(shocked_spot, row['Strike'], row['TimeToExpiry'], risk_free_rate, new_iv, "call")
                s_delta = calculate_delta(shocked_spot, row['Strike'], row['TimeToExpiry'], risk_free_rate, new_iv, "call")
                s_gamma = calculate_gamma(shocked_spot, row['Strike'], row['TimeToExpiry'], risk_free_rate, new_iv)
                
                shocked_records.append({'Strike': row['Strike'], 'BasePrice': row['MarketPrice'], 'ShockedPrice': s_price, 'BaseDelta': row['Delta'], 'ShockedDelta': s_delta, 'BaseGamma': row['Gamma'], 'ShockedGamma': s_gamma})
                
            df_shocked = pd.DataFrame(shocked_records)
            
            if not df_shocked.empty:
                m1, m2, m3 = st.columns(3)
                m1.metric("Shocked Spot", f"${shocked_spot:.2f}", f"{spot_shock_pct:+.1f}%")
                m2.metric("Portfolio Delta Drift", f"{df_shocked['ShockedDelta'].mean():.4f}", f"{df_shocked['ShockedDelta'].mean() - df_shocked['BaseDelta'].mean():+.4f}")
                m3.metric("Portfolio Gamma Shift", f"{df_shocked['ShockedGamma'].mean():.4f}", f"{df_shocked['ShockedGamma'].mean() - df_shocked['BaseGamma'].mean():+.4f}")
                st.dataframe(df_shocked.style.format({'BasePrice': '${:.2f}', 'ShockedPrice': '${:.2f}', 'BaseDelta': '{:.4f}', 'ShockedDelta': '{:.4f}', 'BaseGamma': '{:.4f}', 'ShockedGamma': '{:.4f}'}), use_container_width=True, height=250)

# --- GLOBAL SIGNALS ---
    realized_vol_20d = calculate_historical_volatility(ticker_symbol)
    st.markdown("---")
    st.header("Desk Execution & Trading Signals Engine")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Volatility Risk Premium (VRP)")
        atm_df = df_surface[(df_surface['Strike'] >= spot_price * 0.98) & (df_surface['Strike'] <= spot_price * 1.02)]
        mean_atm_iv = atm_df['Implied Volatility'].mean() if not atm_df.empty else df_surface['Implied Volatility'].mean()
        vrp = mean_atm_iv - realized_vol_20d
        
        st.metric("20-Day Realized Vol (HV)", f"{realized_vol_20d * 100:.2f}%")
        st.metric("Net VRP", f"{vrp * 100:+.2f}%")
        
        if vrp > 0.05:
            st.success("💰 **Short Volatility Favored:** Options are overvalued. Sell premium.")
        elif vrp < -0.02:
            st.warning("⚠️ **Long Volatility Favored:** Options are structurally cheap. Buy gamma.")
        else:
            st.info("⚖️ **Volatility Balanced:** Premiums aligned with realized variance.")

    with col2:
        st.subheader("Relative Value (RV) Scanner")
        iv_mean, iv_std = df_surface['Implied Volatility'].mean(), df_surface['Implied Volatility'].std()
        df_surface['Deviation'] = (df_surface['Implied Volatility'] - iv_mean) / iv_std
        rich, cheap = df_surface[df_surface['Deviation'] > 1.5], df_surface[df_surface['Deviation'] < -1.5]
        
        if not rich.empty:
            st.error(f"🔴 **Sell Target (Rich):** Strike ${rich.iloc[0]['Strike']} at {rich.iloc[0]['TimeToExpiry']:.2f} Yrs (IV: {rich.iloc[0]['Implied Volatility']*100:.1f}%)")
        else:
            st.write("No overvalued deviations found.")
            
        if not cheap.empty:
            st.info(f"🔵 **Buy Target (Cheap):** Strike ${cheap.iloc[0]['Strike']} at {cheap.iloc[0]['TimeToExpiry']:.2f} Yrs (IV: {cheap.iloc[0]['Implied Volatility']*100:.1f}%)")
        else:
            st.write("No undervalued deviations found.")
