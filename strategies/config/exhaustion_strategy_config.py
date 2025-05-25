# Configuration for the Exhaustion Strategy
# Add strategy-specific parameters here 

# Overall switch for the Exhaustion Strategy's trading logic.
# If False, the strategy will not place trades based on exhaustion signals.
strategy_trading_enabled = True

# Primary timeframe on which the strategy identifies exhaustion patterns.
# Example: "M30", "H1". This affects data queries and pattern recognition scope.
primary_timeframe = "M30"

# Number of bars on the `primary_timeframe` to look back for identifying exhaustion patterns
# (e.g., Pin Bars, Engulfing patterns).
exhaustion_lookback_bars = 20

# When querying historical data for the lookback period, an additional buffer of bars
# is requested beyond what's strictly needed for `exhaustion_lookback_bars` (and RSI periods if used).
# This helps ensure enough data is available for calculations.
# Original code: `max_lookback_needed + 5_bar_buffer` where max_lookback was derived from exhaustion and RSI settings.
data_query_buffer_bars = 5

# --- Stop-Loss (SL) and Take-Profit (TP) Parameters ---

# Buffer in pips to add beyond the extremum (highest high for sells, lowest low for buys)
# of the `exhaustion_lookback_bars` period when an exhaustion signal is confirmed and a trade is placed.
# SL for SELL = max_high_in_lookback_period + (stop_loss_pip_buffer * pip_size)
# SL for BUY  = min_low_in_lookback_period  - (stop_loss_pip_buffer * pip_size)
stop_loss_pip_buffer = 5

# Defines how the Take-Profit (TP) level is determined for trades.
# - "opposite_boundary": TP is set to the other side (opposite boundary) of the active博弈空间 (game space).
# - "ratio": TP is calculated based on the `take_profit_ratio` relative to the Stop-Loss distance.
take_profit_target_type = "opposite_boundary"  # Options: "opposite_boundary", "ratio"

# Risk/Reward Ratio used if `take_profit_target_type` is set to "ratio".
# TP_distance_from_entry = SL_distance_from_entry * take_profit_ratio.
# For example, a ratio of 1.5 means the TP distance is 1.5 times the SL distance.
take_profit_ratio = 1.5

# --- Candlestick Pattern Parameters for Exhaustion Detection ---
# These parameters define the criteria for identifying specific candlestick patterns
# that may indicate market exhaustion near博弈空间 boundaries.

# Configuration for Pin Bar detection.
# A Pin Bar is a candle with a long wick and a small body, indicating rejection.
pinbar_config = {
    "enabled": True,  # Master switch to enable/disable Pin Bar pattern detection.

    # For a bearish Pin Bar (potential top exhaustion signal near upper_bound):
    # - The upper wick must be at least `primary_wick_to_body_ratio` times the body size.
    # - The upper wick must also be at least `primary_wick_to_secondary_wick_ratio` times the lower wick size.
    # - The high of the Pin Bar must be at or have touched the博弈空间's upper_bound.
    # For a bullish Pin Bar (potential bottom exhaustion signal near lower_bound):
    # - The lower wick must be at least `primary_wick_to_body_ratio` times the body size.
    # - The lower wick must also be at least `primary_wick_to_secondary_wick_ratio` times the upper wick size.
    # - The low of the Pin Bar must be at or have touched the博弈空间's lower_bound.
    "primary_wick_to_body_ratio": 2.0,      # Default in code: factor of 2
    "primary_wick_to_secondary_wick_ratio": 2.0, # Default in code: factor of 2
}

# Configuration for Engulfing Pattern detection.
# An Engulfing pattern suggests a potential reversal.
engulfing_config = {
    "enabled": True,  # Master switch to enable/disable Engulfing pattern detection.

    # Current hardcoded logic for Bearish Engulfing (near upper_bound):
    #   1. Current bar is bearish (close < open).
    #   2. Previous bar was bullish (close > open).
    #   3. Current bar's open is > previous bar's close (suggests a gap up or open above prior close).
    #   4. Current bar's close is < previous bar's open (current body engulfs previous body).
    #   5. The high of either the current or previous bar is at or above the博弈空间's upper_bound.
    # Current hardcoded logic for Bullish Engulfing (near lower_bound - with fixed conditions):
    #   1. Current bar is bullish (close > open).
    #   2. Previous bar was bearish (close < open).
    #   3. Current bar's open is < previous bar's close (corrected from original: `last_bar['open'] < prev_bar['close']`).
    #   4. Current bar's close is > previous bar's open (corrected from original: `last_bar['close'] > prev_bar['open']`).
    #   5. The low of either the current or previous bar is at or below the博弈空间's lower_bound.
    # If more flexible engulfing definitions are needed (e.g., minimum body engulfment ratio,
    # consideration of wicks), additional parameters would be required here, and the
    # strategy's `_check_bearish_exhaustion` / `_check_bullish_exhaustion` methods updated.
    # "min_engulfing_body_ratio": 1.0, # Example: Current body must be at least 1x the previous body.
}

# --- RSI Divergence Parameters (Optional Feature) ---
# This section is for configuring RSI divergence detection, which can be an additional
# confirmation for exhaustion signals. TA-Lib installation is implied for this feature.
# NOTE: The strategy code's TA-Lib integration and RSI divergence logic is currently
# marked as not fully implemented or inactive ("RSI Divergence Check: Not implemented or disabled").
rsi_divergence_config = {
    "enabled": False,  # Master switch to enable/disable RSI divergence checks.
    "rsi_period": 14,
    "divergence_lookback_bars": 5,  # Number of recent price/RSI peaks/troughs to compare for divergence.
    # "min_rsi_level_for_bearish_divergence": 60, # e.g., RSI must be above this level to consider bearish divergence.
    # "max_rsi_level_for_bullish_divergence": 40, # e.g., RSI must be below this level to consider bullish divergence.
}

# --- Other Potential Parameters & Notes ---

# The parameter `exhaustion_threshold_factor` (defaulted to 0.75 in the strategy's __init__)
# is fetched from parameters but is NOT currently used in the exhaustion detection logic (v1.0 code).
# It might be a remnant or intended for a future, more nuanced exhaustion strength calculation.
# unused_exhaustion_threshold_factor = 0.75

# "Double Push No New Extremum" detection is marked as TODO in the strategy code.
# If implemented, it would require its own set of parameters, e.g.:
# double_push_config = {
#     "enabled": False,
#     "push_lookback_bars": 5, # Lookback for first push
#     "max_bars_between_pushes": 10,
#     "min_retracement_depth_factor": 0.382, # Minimum retracement after first push
# }

# Pip size determination is currently hardcoded in the `_get_pip_size` method:
# `return 0.0001 if 'JPY' not in symbol else 0.01`.
# For broader instrument support, this might need to be configurable per symbol/asset class
# or fetched from instrument metadata if available.
# pip_size_determination_note = "Currently hardcoded based on JPY in symbol name."

# This ExhaustionStrategy inherits from `EventDrivenSpaceStrategy`.
# It relies on the博弈空间 (game spaces) created and managed by the parent strategy.
# Thus, configurations for space definition (e.g., `space_definition_params` like
# `forward_bars`, `boundary_percentile`), event filtering (`event_importance_threshold`),
# and space lifecycle (`max_space_duration_hours`) should be set in the
# `EventDrivenSpaceStrategy`'s parameter section in the main application configuration. 