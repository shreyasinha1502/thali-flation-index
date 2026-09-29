# Unit evidence

Primary documents that confirm the units used in `config/commodity_map.yaml`. They are stored
byte-exact. Each file's sha256 was recorded when it was fetched.

| file | source (fetched 2026-09-29) | sha256 | what it confirms |
|---|---|---|---|
| `2025_LS_B_4366.pdf` | https://fcainfoweb.nic.in/PMS/writereaddata/2025_LS_B_4366.pdf. Lok Sabha Unstarred Q. 4366, answered 26.03.2025 by the Ministry of Consumer Affairs and hosted on DoCA's own Price Monitoring site | `26fa9b5aaf9ca6d3eb41e1ba766cd1f37439605d13c5d7334f321d70fa26111e` | DoCA reports its all-India average retail price of **egg per dozen** (₹75.96 on 21.03.2025) and of **milk per litre** (₹58.34 on 21.03.2025) |

**Caveat.** This is DoCA's own statement of its reporting units as of March 2025. The live
homepage values are consistent with it in magnitude: Eggs ₹83.81 and Milk ₹61.31 on
29.09.2026. If DoCA ever changes units, the homepage header will not say so, so this should be
rechecked if a large level shift appears.
