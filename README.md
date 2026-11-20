# Housing Index Lab

An independently compiled comparison of residential resale price measures using the Housing & Development Board open dataset. This is a NovAsia Estate research tool. It is separate from the official Singapore price index.

## Run and reproduce

Install NumPy in a project environment. Download the HDB CSV from the official source in the app, then run:

```bash
python prepare.py hdb.csv --cutoff 2026-11-20 --out public/data.json
python -m unittest test_prepare.py
python -m http.server 8000 --directory public
```

The browser displays a precomputed snapshot. It sends no entered data to a server. The dataset source, SHA-256, sample sizes and assumptions are recorded in the app and data release. Site publishing directory: `public`.

The raw series is the quarter median relative to 2017 Q1. The matched-stratum series chains median changes across adjacent quarters using transaction weights fixed at the reference quarter. Unavailable strata are omitted from a link only above the coverage threshold. Hedonic links use two-quarter least-squares fits on log price, controlling for floor area, storey, remaining lease, town and flat type. Invalid time links halt each adjusted chain rather than bridging missing periods. The source dataset is provided under Singapore’s Open Data Licence. See the links in the app for coverage and the methodological reference.
