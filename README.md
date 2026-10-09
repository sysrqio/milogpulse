# milogpulse

**MiLoG / FKS pre-audit** for German hospitality timesheet CSV exports — local CLI, no cloud.

```bash
pip install .
milogpulse audit --export timesheet.csv --profile generic
```

Exit codes: `0` OK, `2` policy violation, `1` error.

## Profiles

- `generic` — `work_date`, `start`, `end`, optional `recorded_at`
- `takt` / `personio` — common export column names

## License

MIT — [sysrqio](https://github.com/sysrqio)
