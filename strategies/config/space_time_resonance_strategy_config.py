# Configuration for the Space-Time Resonance Strategy
# Add strategy-specific parameters here 

# Configuration for the Space-Time Resonance Strategy (STRS)

# Overall switch for STRS specific trading logic.
# If False, the strategy might still log information based on key times and resonance,
# but it won't execute its unique trading conditions (S1, S2, S3, confluence).
# Note: The base EventDrivenSpaceStrategy logic for space creation/expiration will still run.
strategy_trading_enabled = True

# General settings for Key Time identification and Resonance logic.
# These settings are typically loaded under a 'resonance' key in the main strategy parameters.
# Example in main config:
# strategy_params:
#   SpaceTimeResonanceStrategy:
#     resonance:
#       key_time_hours_after_event: [1, 2, 4]
#       # ... other settings from below
resonance_settings = {
    # Defines hours after a significant calendar event that are considered "Key Times".
    # Example: [2, 4] means 2 hours and 4 hours after the event.
    "key_time_hours_after_event": [2, 4],

    # Defines fixed time windows (e.g., market opens) as "Key Times".
    # Each entry should be a dictionary.
    # 'name': Descriptive name for the fixed key time.
    # 'start_time': HH:MM format.
    # 'end_time': HH:MM format.
    # 'timezone': IANA timezone string (e.g., 'Europe/London', 'America/New_York').
    # 'days_of_week': List of integers [0-6] where Monday is 0 and Sunday is 6.
    "fixed_key_times": [
        # Example: First hour of London trading session
        # {"name": "LondonOpen_H1", "start_time": "08:00", "end_time": "09:00", "timezone": "Europe/London", "days_of_week": [0,1,2,3,4]},
        # Example: First hour of New York trading session
        # {"name": "NYOpen_H1", "start_time": "13:00", "end_time": "14:00", "timezone": "America/New_York", "days_of_week": [0,1,2,3,4]},
    ],

    # When checking if a Key Time (derived from 'key_time_hours_after_event') falls within
    # the current k-line, this window (in minutes) is used.
    # The k-line's end time is `current_time`. The key_time_point must be > (current_time - window) and <= current_time.
    "key_time_check_window_minutes": 30,

    # Minimum number of active博弈空间 (game spaces) that must show directional confluence
    # (e.g., all broken upwards) to trigger a multi-space resonance signal.
    "min_confluence_spaces": 2,
}

# Settings for how calendar events are mapped to tradable symbols.
# This is crucial for the strategy to associate event-driven spaces with the correct instruments.
# Loaded under 'event_to_symbol_mapping' key within 'resonance' settings or at strategy's top level.
event_to_symbol_mapping = {
    # If True, the strategy will use its internal simple currency-to-symbol map as a fallback
    # if a more specific mapping isn't found below.
    "default_map_by_currency": True,

    # Prioritized mapping: Maps currency codes (from events) to specific symbols.
    "currency_map": {
        "USD": "EURUSD", # Default symbol for USD-related events
        "EUR": "EURUSD",
        "GBP": "GBPUSD",
        "JPY": "USDJPY",
        "AUD": "AUDUSD",
        "CAD": "USDCAD",
        "NZD": "NZDUSD",
        "CHF": "USDCHF",
        # Add other relevant currency mappings
    },

    # Most specific mapping: Maps exact event names (or keywords in event names) to symbols.
    # This overrides 'currency_map' if a match is found.
    "event_name_map": {
        # Example: "Non-Farm Payrolls": "USDJPY",
        # "ECB Interest Rate Decision": "EURUSD",
        # "FOMC Statement": "EURUSD", # Could also be mapped to gold or indices
    }
}

# Configuration for how STRS invokes its sub-strategy checkers (Exhaustion and ReverseCrossover).
# These settings allow STRS to use these sub-strategies with potentially different parameters
# than their global configurations, specifically for STRS's logic (e.g., S3 exhaustion check).
# If a parameter is not specified here, STRS will rely on the sub-strategy's own configured parameters.
# Loaded under 'sub_strategy_invocation_params' within 'resonance' or at strategy's top level.
sub_strategy_invocation_params = {
    "exhaustion_checker_for_s3": {
        # "exhaustion_lookback": 5, # Example: Override lookback period for S3 exhaustion check.
        # "stop_loss_pip_buffer": 10, # Example: Override SL pip buffer for S3 exhaustion.
        # If not specified, uses ExhaustionStrategy's own config.
    },
    "reverse_crossover_checker_for_s1": {
        # Parameters for when ReverseCrossover is potentially invoked after S1 condition (price inside space at key time).
        # This part of STRS logic is currently passive ("pass"), awaiting RC to trigger on next bar.
        # If STRS were to actively manage RC invocation here, params could be set.
    }
}

# --- Stop-Loss (SL) and Take-Profit (TP) Parameters for STRS-Specific Trades ---
# These define SL/TP for trades triggered directly by STRS's unique conditions.

# For S3 condition (Price outside space, already crossed, waiting for exhaustion signal)
s3_exhaustion_trade_config = {
    # If True, Take Profit is set to the opposite boundary of the violated博弈空间.
    "use_space_boundary_as_tp": True,
    # "fixed_tp_pips": 100,  # Alternative: Fixed TP in pips (if use_space_boundary_as_tp is False)

    # If True, Stop Loss is based on the extremum (high/low) of the exhaustion period + a buffer.
    # The buffer itself comes from the (potentially overridden) exhaustion_checker params.
    "sl_based_on_exhaustion_extremum": True,
    # "fixed_sl_pips": 50,     # Alternative: Fixed SL in pips
}

# For S1 condition (Price inside space at key time, waiting for breakout)
# STRS currently waits for ReverseCrossoverStrategy (RCS) to handle post-breakout.
# If STRS were to place its own trade immediately on breakout at key time:
s1_keytime_breakout_trade_config = {
    "enabled": False, # Currently, logic defers to RCS. Set to True to enable direct S1 trades.
    # "tp_target_ratio_of_space_width": 1.0, # e.g., TP = space_width * ratio
    # "sl_outside_space_pips": 10, # e.g., SL is X pips beyond the broken boundary
}

# For S2 condition (Price outside space, NOT yet crossed, monitoring for return and reverse signal)
# This logic is marked as TODO in the strategy code.
s2_return_and_reverse_trade_config = {
    "enabled": False, # Set to True if/when S2 trading logic is implemented.
    # Define parameters for detecting "return to space" and "reverse signal".
    # "min_bars_for_return_confirmation": 1,
    # "reversal_signal_lookback": 5, # e.g., lookback for a reversal pattern
    # "tp_target_opposite_boundary": True,
    # "sl_fixed_pips_from_entry": 30,
}

# For trades triggered by Multi-Space Confluence
multi_space_confluence_trade_config = {
    "enabled": False, # Set to True to enable direct trading on confluence signals.
                      # Current code logs confluence but doesn't place trades directly.
    # "tp_multiplier_of_average_space_size": 1.0,
    # "sl_based_on_outermost_confluent_space_boundary_pips": 15, # SL X pips beyond the combined structure
}


# Symbol-specific 'key_time_weight' settings.
# This section is loaded under the 'key_time_weight' key in the main strategy parameters.
# It primarily acts as an enable/disable switch per symbol for the key-time dependent logic within STRS.
# It can also hold symbol-specific overrides for 'resonance_settings' if the strategy code is adapted to look for them here.
# Example in main config:
# strategy_params:
#   SpaceTimeResonanceStrategy:
#     key_time_weight: # This name is a bit confusing, inherited from init.
#       enabled: True # Global master switch for all STRS key-time features.
#       settings_per_symbol:
#         EURUSD:
#           process_key_times: True # Enable key-time logic for EURUSD
#           # key_time_hours_after_event: [1, 3] # Symbol-specific override example
#         GBPUSD:
#           process_key_times: True
#         USDJPY:
#           process_key_times: False # Disable key-time logic for USDJPY
symbol_specific_processing_flags = {
    # This 'enabled' is a global switch for all symbol-specific key-time processing.
    # If False, the 'settings_per_symbol' are ignored.
    # This is read by self.key_time_enabled = self.key_time_params.get('enabled', False)
    "master_enabled_for_key_time_logic": True,

    "settings_per_symbol": {
        "EURUSD": {
            "process_this_symbol": True, # If master_enabled is True, this further gates processing for EURUSD
            # "key_time_hours_after_event": [1, 3], # Example of a symbol-specific override for resonance_settings
                                                  # Strategy code would need to be adapted to look for such overrides here.
        },
        "GBPUSD": {
            "process_this_symbol": True,
        },
        # Example: Disable for USDJPY specifically
        "USDJPY": {
            "process_this_symbol": False,
        },
        # Add other symbols as needed
    }
}

# Note: The strategy's __init__ currently loads:
# self.key_time_params = self.params.get('key_time_weight', {})
# self.key_time_enabled = self.key_time_params.get('enabled', False)  <- This suggests 'enabled' is at top of 'key_time_weight'
# self.resonance_params = self.params.get('resonance', {}) <- This is where most resonance_settings above would go.
#
# To use the `symbol_specific_processing_flags` as defined above, the main config structure for SpaceTimeResonanceStrategy would be:
# SpaceTimeResonanceStrategy:
#   strategy_trading_enabled: true
#   resonance: { ... resonance_settings ... event_to_symbol_mapping ... sub_strategy_invocation_params ... SL/TP settings ... }
#   key_time_weight: { ... symbol_specific_processing_flags ... } # 'key_time_weight' used as per strategy code. 