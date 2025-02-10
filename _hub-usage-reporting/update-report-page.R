args <- setdiff(commandArgs(TRUE), "--args")

ym <- args[1]
target_filename <- args[2]

org <- sub(".+-((nasa)|(noaa))_.+\\.pdf", "\\1", target_filename)

new_report_line <- sprintf(
  "- [Usage report for %s](_hub-usage-reporting/reports/%s)",
  ym,
  target_filename
)

lines <- readLines("usage-reporting.qmd")

if (!any(grepl(target_filename, lines, fixed = TRUE))) {
  cat(
    sprintf(
      "Adding report %s to %s monthly reports",
      target_filename,
      toupper(org)
    )
  )
  # split on html comment marking end of org reports
  org_insert_line <- grep(sprintf("<!-- last-%s-report -->", org), lines)
  org_before <- lines[seq_len(org_insert_line - 1)]
  org_after <- lines[seq(org_insert_line, length(lines))]

  # recombine with new report at the end of the list
  outlines <- c(org_before, new_report_line, org_after)
  writeLines(outlines, "usage-reporting.qmd", sep = "\n")
} else {
  cat(sprintf("No new report to add for %s\n", org))
}
