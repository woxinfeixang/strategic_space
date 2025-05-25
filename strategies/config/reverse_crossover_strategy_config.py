# Configuration for the Reverse Crossover Strategy
# Add strategy-specific parameters here 

# Configuration for the Reverse Crossover Strategy (RCS)

# Overall switch for RCS trading logic.
# If False, the strategy will not attempt to place trades based on reverse crossover signals.
# This is useful for disabling the strategy or parts of it during testing or specific market conditions.
strategy_trading_enabled = True

# --- Entry Conditions ---

# Defines the entry behavior after a博弈空间 (game space) boundary is broken by price.
# - If False (default): The strategy attempts to enter on the close of the bar that breaks out
#   of the博弈空间, provided the bar opened within or at the boundary.
# - If True: The strategy will wait for the price to retrace back towards the broken boundary
#   before considering an entry. 
#   NOTE: The specific logic for retrace entry (e.g., how close to boundary, confirmation signals)
#   is currently marked as TODO in the strategy code (reverse_crossover_strategy.py).
#   If this is set to True with the current code, no trades will be placed for retrace scenarios.
entry_on_retrace = False

# --- Stop-Loss (SL) and Take-Profit (TP) Parameters (Primarily for Immediate Entry) ---

# Stop-Loss placement factor, relative to the height of the博弈空间.
# This factor determines how far from the broken boundary the stop-loss is placed.
# Calculation for BUY after upper boundary breakout:
#   SL_price = upper_bound - (space_height * stop_loss_factor)
# Calculation for SELL after lower boundary breakout:
#   SL_price = lower_bound + (space_height * stop_loss_factor)
# - A `stop_loss_factor` of 0.5 means SL is placed at 50% of the space height away from the
#   broken boundary, effectively in the middle of the original space.
# - A value of 0 would place SL exactly at the broken boundary.
# - A value of 1.0 would place SL at the opposite boundary of the space.
# - A negative value (e.g., -0.2) would place SL *outside* the original space, on the other side
#   of the entry bar, further away from the broken boundary by (space_height * abs(stop_loss_factor)).
stop_loss_factor = 0.5

# Take-Profit ratio, defining the target profit relative to the calculated Stop-Loss distance (Risk/Reward Ratio).
# TP_distance_from_entry = abs(entry_price - SL_price) * take_profit_ratio
# Calculation for BUY:
#   TP_price = entry_price + TP_distance_from_entry
# Calculation for SELL:
#   TP_price = entry_price - TP_distance_from_entry
# Example: A `take_profit_ratio` of 2.0 aims for a Risk:Reward ratio of 1:2.
# If SL distance is 50 pips, TP distance will be 100 pips.
take_profit_ratio = 2.0

# --- Parameters for Retrace Entry (Future Implementation) ---
# These parameters would be relevant if `entry_on_retrace` is True and the
# corresponding logic is fully implemented in the strategy code.
# retrace_entry_config = {
#     # Maximum distance (e.g., in pips or as a factor of space_height) price can be from the broken boundary
#     # for a retrace to be considered valid for entry.
#     "max_retrace_distance_from_boundary_factor": 0.1, # e.g., 10% of space_height
#     # "max_retrace_distance_from_boundary_pips": 10,

#     # Type of confirmation signal required after price retraces to the zone.
#     # Examples: 'candle_pattern_rejection', 'momentum_divergence', 'ma_cross_confirm'. (Requires specific implementation)
#     "retrace_confirmation_signal_type": None,

#     # Number of k-lines to wait for a valid retrace and confirmation signal before abandoning the setup.
#     "retrace_timeout_bars": 5,
# }

# --- Breakout Confirmation Logic (Current hardcoded behavior) ---
# The strategy currently defines a breakout based on the open and close of the bar relative to space boundaries:
# - Upward Breakout: Bar opens inside or at the upper_bound AND closes above the upper_bound.
# - Downward Breakout: Bar opens inside or at the lower_bound AND closes below the lower_bound.
#
# If more sophisticated breakout confirmation is desired (e.g., breakout by X pips, minimum bar body size,
# volume confirmation), the strategy code (`_execute_trading_logic`) would need to be modified,
# and corresponding new parameters could be added here.
# Example future parameters for enhanced breakout confirmation:
# advanced_breakout_confirmation = {
#     "min_pips_beyond_boundary": 1, # e.g., close must be at least 1 pip beyond the boundary.
#     "min_breakout_bar_body_ratio": 0.3, # e.g., body of the breakout bar must be at least 30% of its total range.
#     "require_volume_increase_factor": 1.0, # e.g., 1.5 means breakout bar volume must be 50% > average volume (Not implemented)
# }

# Note: This strategy is a child of `EventDrivenSpaceStrategy`.
# Parameters related to the creation, definition, and expiration of the 博弈空间 (game spaces)
# themselves are typically configured within the `EventDrivenSpaceStrategy` specific parameters
# or its general application configuration section, not directly in this RCS config file. 