# Seed copy of NSE's equity list

`nse_equity_list_2023-11-05.csv` is NSE's public list of listed equities
(`EQUITY_L.csv`, published at https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv),
as committed on 5 November 2023 to the public GitHub repository
`bhavansh/isin-database` (file `csv-data/equity.csv`). 1,949 rows.

FINN uses it only when NSE can't be reached and no copy was cached from a
live fetch. Reports built on it say so. It is out of date: companies listed
after November 2023 are missing and some names, series or ISINs have changed.
For those, a live run falls back to NSE's quote metadata.
