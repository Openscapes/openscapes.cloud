
# Openscapes JupyterHub Usage Reports

This directory contains quarto documents that generates
a report of the usage and costs of AWS resources in the NASA-Openscapes and NMFS-Openscapes JupyterHubs.

The report is generated automatically on the first day of every month using a GitHub Actions [workflow](../.github/workflows/create-pdf-report.yml), summarizing usage for the preceding month. The report can also be created on demand by triggering the workflow manually, by visiting the ["Render and Save PDF" workflow page](https://github.com/openscapes/openscapes.cloud/actions/workflows/create-pdf-report.yml), and clicking the "Run Workflow" button in the upper right corner.

Reports are stored in the [reports](reports/) directory.

## Monthly NASA reports

- [Usage report for 2024-07](reports/aws-usage-report_2024-07.pdf)
- [Usage report for 2024-08](reports/aws-usage-report_2024-08.pdf)
- [Usage report for 2024-09](reports/aws-usage-report_2024-09.pdf)
- [Usage report for 2024-10](reports/aws-usage-report_2024-10.pdf)
- [Usage report for 2024-11](reports/aws-usage-report_2024-11.pdf)
- [Usage report for 2024-12](reports/aws-usage-report_2024-12.pdf)
- [Usage report for 2025-01](reports/aws-usage-report_2025-01.pdf)
