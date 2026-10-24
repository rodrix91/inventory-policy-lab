# Security

`inventory-policy-lab` is a local command-line tool. It reads demand-history CSV files, performs inventory-policy analysis, and writes reports. The runtime uses the Python standard library, does not open network connections, and does not store credentials.

## Reporting a problem

If you find a security issue, open a private GitHub security advisory on this repository, or use the contact information on the [profile README](https://github.com/rodrix91/rodrix91). Please do not open a public issue for an unfixed vulnerability.

## Scope

In scope: unsafe path handling, unintended input-file overwrite, unsafe report-file replacement, malformed input that causes an unexpected crash, and behavior that could produce materially misleading output in an automated workflow.

Out of scope: the contents of data files intentionally supplied by the user and forecasting or inventory-model limitations that are already documented as analytical assumptions rather than security defects.
