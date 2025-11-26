process_year = function(year, root = "data/raw_ocr") {
  # Read all pages for a given year and process them into a single tibble
  year_path = file.path(root, as.character(year))
  pages = list.files(year_path) |>
    map(\(page_set) fromJSON(file.path(year_path, page_set)) |> as_tibble() |> mutate(page_numbers = page_set)) |> 
    bind_rows() |> 
    mutate(
      year = year,
      # Clean numeric columns
      across(
        total_units:public_valuation,
        \(col) col |>
          str_replace_all(" ", "") |>
          str_replace_all("-|\\*", "0") |> # "*" for Phoenix in 1977
          na_if("(X)") |>
          na_if("(S)") |> 
          as.integer()
      )
    ) |>
    relocate(year, page_numbers, line_number)
  # Remove metropolitan summary rows
  if (year == "1970") {
    pages = pages |>
      slice(-1)
  } else {
    pages = pages |>
      slice(-1:-3)
  }
  return(pages)
}

add_smsa_indicators = function(bps_cleaned) {
  # 
  bps = bps_cleaned |>
    mutate(
      outside_indicator = as.numeric(str_detect(smsa_name, "OUTSIDE")),
      inside_indicator = as.numeric(str_detect(smsa_name, "INSIDE")),
      smsa_group = if_else(year != 1970, outside_indicator, inside_indicator) |> cumsum() |> lag(default = 0)
    ) |>
    mutate(
      .by = smsa_group,
      smsa_indicator = as.numeric(row_number() == 1),
      city_indicator = as.numeric(
        smsa_indicator == 0 & outside_indicator == 0 & inside_indicator == 0
      )
    )
  return(bps)
}

custom_theme = function() {
  theme_bw() +
    theme(
      legend.position = "bottom"
    )
}

