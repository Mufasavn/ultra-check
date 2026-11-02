# Validation

The original 2.9 release reported 84 passing Python tests and the executable checks recorded in `validation/`. Its EXE SHA-256 is included there.

The UI checks use isolated data and simulated search/API responses. They cover saved-list restart persistence, backup creation, combined saved CSV contents, ten API fields, no preflight modal, 23 results paginated 10/10/3, English UI, mobile layout and no browser runtime errors. CSV content was checked, not an interactive Save dialog. No paid Actor run was created by those UI checks.

Unit coverage includes stable storage when the EXE folder changes, migration of the five-slot vault, failover through slot ten, backup recovery, cache behavior, run-history persistence, source/filter validation and bounded proxy error handling.

Run on Windows with Python 3.12 after installing requirements:

```powershell
python -m unittest discover -p "test_*.py"
```

No real credentials or personal datasets are required for unit tests. Original benchmark datasets and personal runtime folders are excluded.
