# Economic Calendar Data Directory Structure

This directory stores all data related to the economic calendar module.

```
data/calendar/
├── raw/                     # Raw data downloaded or placed
│   ├── live/                # Raw data for the real-time workflow
│   │   └── upcoming.csv     # Default output of download_investing_calendar.py. Contains current day's data, date column is runtime date, importance is numeric.
│   └── history/             # Raw data for the historical workflow
│       └── *.html           # Historical HTML files (needs to be placed manually, processed by process_calendar.py)
│
├── processed/             # Intermediate processed data
│   ├── live/                # (Currently unused as the HTML processing step was removed from the realtime workflow)
│   │   #└── processed_live.csv # Example of potential intermediate file if processing step existed
│   └── history/             # Processed data from historical HTMLs
│       └── economic_calendar_history.csv # Default output of process_calendar.py. Merged, deduplicated, and sorted data from raw history HTMLs.
│
├── filtered/              # Final filtered data after applying rules
│   ├── live/                # Filtered data from the real-time workflow
│   │   └── filtered_live.csv # Default output of filter_data_step.py (when run via realtime workflow). Contains events passing the filters.
│   └── history/             # Filtered data from the historical workflow
│       └── filtered_historical.csv # Default output of main.py --action filter (when run via history workflow). Contains events passing the filters.
│
└── db/                      # SQLite Databases
    └── economic_calendar.db # Default SQLite database file.
        ├── events_live      # Table storing filtered real-time events.
        └── events_history   # Table storing filtered historical events.

```

**Key File Descriptions:**

*   **`raw/live/upcoming.csv`**: The direct output of the real-time download script (`download_investing_calendar.py`). Contains the economic events for the day the script was run. This is the input for the real-time filtering step.
*   **`raw/history/*.html`**: Raw HTML files containing historical economic calendar data. These need to be obtained and placed here manually. They serve as input for a separate historical data processing script (e.g., `process_calendar.py`, not part of the automated workflows described in the main README).
*   **`processed/history/economic_calendar_history.csv`**: The output of processing the raw historical HTML files. This file typically contains cleaned, merged, and sorted historical data and serves as the input for the historical filtering workflow (`main.py --action filter`).
*   **`filtered/live/filtered_live.csv`**: The final output of the real-time workflow (`run_realtime_workflow.py`). Contains only the events from `upcoming.csv` that passed the filtering rules defined in `config/processing.yaml`.
*   **`filtered/history/filtered_historical.csv`**: The final output of the historical workflow (`run_history_workflow.py`). Contains only the events from `economic_calendar_history.csv` that passed the filtering rules.
*   **`db/economic_calendar.db`**: An SQLite database containing two tables (`events_live` and `events_history`) mirroring the content of the corresponding filtered CSV files.

**Configuration:**

Specific file names and the exact paths for these directories (relative to a base data path) are typically configured in `config/common.yaml` and `economic_calendar/config/processing.yaml`. 