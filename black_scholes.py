import numpy as np
from scipy.stats import norm

def black_scholes_price(S, K, T, r, sigma, option_type="call"):
    """
    Calculates the exact theoretical analytical Black-Scholes price 
    for European call and put options.
    """
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
        
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == "call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
    return max(0.0, price)

def calculate_delta(S, K, T, r, sigma, option_type="call"):
    """
    Calculates Option Delta (First derivative of price with respect to spot).
    Functions as an institutional proxy for ITM expiry probability.
    """
    if T <= 0 or sigma <= 0:
        return 1.0 if (option_type == "call" and S > K) else 0.0
        
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    
    if option_type == "call":
        return float(norm.cdf(d1))
    else:
        return float(norm.cdf(d1) - 1.0)

def calculate_gamma(S, K, T, r, sigma):
    """
    Calculates Option Gamma (Second derivative of price with respect to spot).
    Isolates risk acceleration boundaries for market makers.
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
        
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return float(gamma)

def implied_volatility(market_price, S, K, T, r, option_type="call", max_iterations=100, precision=1e-5):
    """
    Uses the Newton-Raphson numerical optimization method to reverse-engineer 
    implied volatility from a given market premium price string.
    """
    # Baseline intrinsic check to avoid impossible optimization bounds
    intrinsic_value = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    if market_price <= intrinsic_value:
        return 0.0
        
    # Initial baseline volatility guess (50% annualized variance proxy)
    sigma = 0.50
    
    for _ in range(max_iterations):
        theoretical_price = black_scholes_price(S, K, T, r, sigma, option_type)
        price_error = theoretical_price - market_price
        
        # Calculate Vega (partial derivative of option price with respect to volatility)
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        vega = S * norm.pdf(d1) * np.sqrt(T)
        
        # Guard against zero-division errors in out-of-the-money or illiquid tails
        if abs(vega) < 1e-6:
            # Fall back to a minor structural bisection nudge if slope goes flat
            sigma += 0.05 if price_error < 0 else -0.05
            if sigma <= 0: sigma = 0.01
            continue
            
        sigma_update = price_error / vega
        sigma -= sigma_update
        
        # Enforce physical boundary conditions
        if sigma <= 0:
            sigma = 0.005
            
        if abs(sigma_update) < precision:
            return float(sigma)
            
    return float(sigma)
