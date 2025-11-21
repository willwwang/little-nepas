library(jsonlite)
library(tidyverse)

years = as.character(1967:1979) |> set_names()

process_year = function(year_path) {
  pages = list.files(year_path, full.names = TRUE) |>
    map(\(x) fromJSON(x) |> as_tibble()) |> 
    bind_rows() |> 
    mutate(
      across(
        total_units:public_valuation,
        \(col) col |>
          str_replace_all(" ", "") |>
          str_replace_all("-|\\*", "0") |> # "*" for Phoenix in 1977
          na_if("(X)") |>
          na_if("(S)") |> 
          as.integer()
      ),
      outside_indicator = as.numeric(str_detect(smsa_name, "OUTSIDE")),
      inside_indicator = as.numeric(str_detect(smsa_name, "INSIDE"))
    )
  if (str_detect(year_path, "1970")) {
    pages = pages |> 
      mutate(
        smsa_group = cumsum(inside_indicator) |> lead(default = sum(inside_indicator))
      )
  } else {
    pages = pages |> 
      mutate(
        smsa_group = cumsum(outside_indicator) |> lag(default = 0)
      )
  }
  pages |> 
    mutate(
      .by = smsa_group,
      smsa_indicator = as.numeric(row_number() == 1),
      city_indicator = as.numeric(
        smsa_indicator == 0 & outside_indicator == 0 & inside_indicator == 0
      )
    ) |> 
    filter(.by = smsa_group, !any(str_detect(smsa_name, "TOTAL")))
}

bps = map(
  years,
  \(year) process_year(str_glue("raw_ocr/{year}"))
) |> bind_rows()


bps = bps |> 
  mutate(
    total_units_diff = total_units - rowSums(pick(private_total, public_units)),
    private_total_diff = private_total - rowSums(pick(private_1_unit:private_5plus_units)),
    total_valuation_diff = total_valuation - rowSums(pick(private_valuation, public_valuation)),
    private_valuation_diff = private_valuation - rowSums(pick(private_1_unit_val:private_5plus_units_val))
  )

bps |> 
  pivot_longer(contains("diff"), names_to = "diff_type", values_to = "diff_value") |> 
  filter(diff_value != 0)

#' 




bps |>
  filter(.by = smsa_group, !any(str_detect(smsa_name, "TOTAL"))) |> 
  nrow()

bps |> 
  filter(smsa_indicator == 1) |> 
  ggplot() +
  geom_histogram(aes(x = total_units))



list.files("raw_ocr/1977", full.names = TRUE) |>
  map(\(x) fromJSON(x) |> as_tibble()) |> 
  bind_rows() |> 
  mutate(
    across(
      total_units:public_valuation,
      \(col) col |>
        str_replace_all(" ", "") |>
        str_replace_all("-", "0") |>
        na_if("(X)") |>
        na_if("(S)")
    )
  ) |> 
  pivot_longer(
    total_units:public_valuation
  ) |> 
  filter(as.numeric(value) |> is.na() & !is.na(value))




