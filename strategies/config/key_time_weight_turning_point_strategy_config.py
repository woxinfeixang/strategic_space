# Configuration for the Key Time Weight Turning Point Strategy
# Add strategy-specific parameters here 

# Configuration for the Key Time Weight Turning Point Strategy (KTWTP)

# Overall switch for KTWTP strategy's specific trading logic.
# If False, the strategy will not execute trades based on its key time / turning point conditions.
# Base EventDrivenSpaceStrategy logic (like space creation) might still run if applicable.
strategy_trading_enabled = True

# Primary timeframe the strategy operates on for identifying key times and turning points.
# This affects how event_time and current_bar_time are interpreted and aligned.
# Example: "M30", "H1".
# Note: The strategy code currently implies M30 in some argument names (e.g., `current_m30_bar_time`
# in `_confirm_with_m5_m15`). Ensure strategy logic consistently uses this parameter if it's made
# truly dynamic and read from here.
primary_timeframe = "M30"


# Main parameters for the Key Time Weight Turning Point (KTWTP) logic.
# In the main application configuration, these are typically expected to be nested under
# a 'ktwtp_params' key within the 'KeyTimeWeightTurningPointStrategy' section.
# Example structure in main YAML/DictConfig:
# strategy_params:
#   KeyTimeWeightTurningPointStrategy:
#     ktwtp_params: { ... contents below ... }
#     event_mapping: { ... contents from event_mapping section below ... }
ktwtp_params = {
    # Defines hours after a significant calendar event that are considered "Key Times" for this strategy.
    # Example: [1, 3, 5] means 1 hour, 3 hours, and 5 hours after the event's timestamp.
    "key_time_hours_after_event": [1, 3, 5],

    # Tolerance in minutes when checking if the current processing time aligns with a calculated key_time_hour_after_event.
    # E.g., if tolerance is 1, a key time calculated as 10:00:00 will be matched by current times from 09:59:00 to 10:00:59.
    # The code currently uses `abs((current_time - key_trigger_time).total_seconds()) < 60` (i.e., 1 minute tolerance).
    "key_time_tolerance_minutes": 1,

    # If True, the strategy uses the boundaries of博弈空间 (game spaces) created by the
    # parent EventDrivenSpaceStrategy as potential turning points.
    "use_space_boundaries_as_turning_points": True,
    # Future TODO in strategy: Extend to identify and use Node points or Natural Retracements as turning points.

    # Buffer in pips when checking if the price (high/low of current bar) is at a博弈空间 boundary.
    # Price is considered at upper_bound if: current_high >= upper_bound - buffer AND current_low <= upper_bound + buffer.
    # Similar logic for lower_bound.
    "turning_point_buffer_pips": 10,

    # --- Parameters for M5/M15 Confirmation Signals (Optional) ---
    # If True, after a potential turning point is identified on the `primary_timeframe` at a key time,
    # the strategy will look for confirming candlestick patterns on M5 (or M15) timeframe.
    "confirm_with_m5_m15": False,
    "confirmation_timeframe": "M5", # Timeframe for confirmation (e.g., "M5", "M15")

    # Number of bars on the `confirmation_timeframe` to look back for pattern confirmation.
    "confirmation_lookback_bars": 6,

    # For Pin Bar confirmation on `confirmation_timeframe`:
    # The wick (upper for sell, lower for buy) must be at least X times the size of the candle body.
    "confirmation_pinbar_min_wick_to_body_ratio": 1.5,
    # The candle body must be less than Y times the total bar range (high - low).
    "confirmation_pinbar_max_body_to_range_ratio": 0.4,
    # TODO: Add parameters for M5/M15 engulfing patterns if more flexibility is needed beyond current hardcoded logic.
    # E.g., "confirmation_engulfing_min_body_ratio_to_previous": 1.0 (body must fully engulf previous body)

    # --- Stop-Loss and Take-Profit Parameters ---
    # Pips to add beyond the high (for sells) or low (for buys) of the `primary_timeframe` bar
    # that triggered the entry signal (i.e., the bar at the turning point at key time).
    # SL for SELL = trigger_bar_high + (stop_loss_buffer_pips * pip_size)
    # SL for BUY  = trigger_bar_low  - (stop_loss_buffer_pips * pip_size)
    "stop_loss_buffer_pips": 15,

    # Defines how the Take-Profit level is determined.
    # "opposite_boundary": TP is set to the other side of the博弈空间.
    # "ratio": TP is calculated based on the `risk_reward_ratio` relative to the SL distance.
    "take_profit_target_type": "opposite_boundary",

    # Risk/Reward Ratio used if `take_profit_target_type` is "ratio".
    # TP_distance_from_entry = SL_distance_from_entry * risk_reward_ratio.
    "risk_reward_ratio": 1.5,
}

# Event to Symbol Mapping Configuration.
# Defines how calendar events are mapped to tradable symbols for this strategy.
# In the main application configuration, these are typically expected to be nested under
# an 'event_mapping' key within the 'KeyTimeWeightTurningPointStrategy' section.
event_mapping = {
    # Maps currency codes (from calendar events) to specific tradable symbols.
    # Key: Currency code (string, e.g., "USD", "EUR"). The strategy code converts input currency to uppercase for matching.
    # Value: Symbol string (e.g., "EURUSD").
    "currency_to_symbol": {
        "EUR": "EURUSD",
        "USD": "EURUSD", # Example: USD events are also mapped to EURUSD for this strategy's context
        "GBP": "GBPUSD",
        "JPY": "USDJPY",
        "AUD": "AUDUSD",
        "CAD": "USDCAD",
        "NZD": "NZDUSD",
        "CHF": "USDCHF",
        # Add other relevant currency-to-symbol mappings as needed.
    },

    # Default symbol to use if an event's currency is not found in the `currency_to_symbol` map.
    # If this is not set or is None, and a currency isn't mapped, no symbol will be returned for that event.
    "default_event_symbol": "EURUSD",

    # TODO: For more granular control, consider adding a map for specific event names to symbols,
    # which would override the currency-based mapping if an event name matches.
    # "specific_event_name_to_symbol_map": {
    #     "Non-Farm Payrolls": "USDJPY",
    #     "ECB Press Conference": "EURUSD",
    # }
}

# Note on Dependencies:
# This strategy (KTWTP) inherits from `EventDrivenSpaceStrategy` (EDSS).
# Therefore, parameters related to the fundamental creation, definition, and lifecycle management
# of the博弈空间 (game spaces) themselves—such as `space_definition_params` (e.g., `forward_bars`,
# `boundary_percentile`), `event_importance_threshold`, `max_space_duration_hours`, etc.—are
# typically configured within EDSS's own parameter section in the main application configuration.
# KTWTP consumes these spaces and applies its key-time and turning-point logic to them.
# Ensure that the configurations for EDSS are appropriately set up for KTWTP to function correctly. 