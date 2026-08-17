# Benchmark Data

The input PDFs are intentionally ignored by Git because source licences or business confidentiality
must be checked before redistribution. Put the following files in `spike/data/inputs/`:

| File | Pages | SHA-256 | Public source |
|---|---:|---|---|
| `01_GSA_VA_Chiller_Maintenance_Solicitation.pdf` | 60 | `766e6f369abe50fcdb9541f18402a852685d08b8fbed3e6983908aff71fd90e2` | [GSA source PDF](https://buy.gsa.gov/api/system/files/documents/561210FAC%20-%20Chiller%20Plant%20Preventive%20Maintenance%20-%20VA%20Medical%20Center%20-%20Willington%20DE_Redacted.pdf) |
| `02_DOE_NNSA_RFP_Section_L.pdf` | 28 | `c0fa7bef79bb8915a26e18024b7c5c14909661691b06a27f912ee6ce7231c6a9` | [DOE source PDF](https://www.energy.gov/sites/prod/files/migrated/nnsa/2017/11/f46/draft_de-sol-0011206_section_l_-_instructions.pdf) |
| `03_NASA_Fastener_Procurement_Standard.pdf` | 16 | `16ca2509462c997669a580e3644620e23471ab2ec81f586bc40c7e53e9a5d9c0` | [NASA source PDF](https://standards.nasa.gov/sites/default/files/standards/NASA/Baseline/0/nasa-std-873914.pdf) |

The parsing spike also uses two generated seven-page fixtures:

- `04_GSA_Table_Scan_Fixture.pdf`: source pages 13–15 and 24–27 rasterized at 180 DPI.
- `05_GSA_Mixed_Table_Fixture.pdf`: the same seven pages with source pages 14, 25, and 27
  rasterized and the other pages left native.

They contain no invented document content. `spike/src/benchmark/fixture_builder.py` builds them from
the GSA PDF using Poppler `pdftoppm`. After setting up the local virtual environment, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\build_parsing_fixtures.ps1
```

If `pdftoppm` is not on `PATH`, pass its exact executable path with `-PdftoppmPath`. SHA/page
inventory artifacts from the frozen dataset are preserved in `spike/results/pdf_inventory.json`
and `spike/results/fixture_inventory.json`.

Before a benchmark, verify that the source SHA-256 values match. A changed upstream PDF must be
treated as a new dataset version; do not silently compare its results with the frozen runs.
