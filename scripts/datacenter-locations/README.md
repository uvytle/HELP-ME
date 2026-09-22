# US data center locations

Scrapes US data center locations — colocation, hyperscale, cloud, managed
services, edge — from several open sources and writes one spreadsheet:
`Data Center Name`, `Location`, `Type`.

## Run it

```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
./.venv/Scripts/python.exe build_dataset.py
```

Output: `data/datacenters_us.xlsx`.

## Sources used, and why

| Source | What it gives us | Why it's used this way |
| --- | --- | --- |
| [usdatamap.com](https://usdatamap.com/) | ~450 named US facilities (colocation + hyperscale) | Its robots.txt explicitly allows crawling, and the whole dataset ships as a public static JS file (`/assets/data-facilities-*.js`) — there's no HTML to scrape, we just parse that file directly. `sources/usdatamap.py` finds the current hashed filename from the homepage each run so it survives their next deploy. |
| [PeeringDB](https://www.peeringdb.com/) | ~1,400 US colocation / carrier-neutral facilities | Public, purpose-built API for exactly this data (`api/fac`). Fetched in one request with a high `limit` (rather than paginating) since PeeringDB rate-limits unauthenticated traffic hard — fewer requests means less chance of tripping it. |
| [OpenStreetMap](https://www.openstreetmap.org/) (Overpass API) | Nodes/ways tagged `telecom=data_center` | Open (ODbL) data, queried in one bulk request. The public Overpass mirrors are flaky (timeouts/gateway errors are common); this source is best-effort and the build continues without it if all mirrors fail. |
| Cloud provider docs (AWS / Azure / GCP / OCI / IBM) | US cloud region metros | Hardcoded in `sources/cloud_regions.py` from each provider's own region-list page. Hyperscalers don't publish street addresses for these campuses — the region *is* the published location — so there's nothing to scrape. |

### Sources requested but NOT automated: datacenters.com, datacentermap.com

Both sites are Vercel-hosted and both returned a **Vercel Security
Checkpoint** bot-detection page on even a single plain request
(`datacenters.com` on the homepage, `datacentermap.com` on `/usa/` — the
latter also 429'd on a bare `robots.txt` fetch). That's active anti-bot
protection, not a fluke — getting past it means solving a JS challenge, which
is bypassing a site's explicit bot defenses. This script doesn't do that.

If you have a paid `datacenters.com` account, they may offer a manual CSV
export from the dashboard — that's the legitimate path to that data, and it
can be dropped in and merged by hand later if it's worth it.

## Notes

- `Location` is `City, State` where available, falling back to a street
  address or bare state name.
- `Type` is whatever the source calls it (`colocation`, `hyperscale`,
  `cloud`, ...) — coverage is uneven. usdatamap.com and PeeringDB skew toward
  colocation and hyperscale; there isn't yet a good open source specifically
  for edge/managed-services deployments, since those are usually announced
  in press releases rather than listed anywhere structured.
- No de-duplication across sources — the same physical campus can appear
  more than once (e.g. once from usdatamap.com, once from PeeringDB) since
  each source names and locates it slightly differently. Sort/filter in
  Excel if that matters for what you're doing with it.

## Extending this

Each source lives in its own file under `sources/`, exposing a single
`fetch() -> list[dict]` function (fields: `name`, `city`, `state_code`,
`address`, `state`, `type`, ...). To add a source, drop in a new module and
register it in `SOURCE_FETCHERS` in `build_dataset.py`.
