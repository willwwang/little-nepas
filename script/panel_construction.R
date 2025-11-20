library(jsonlite)
library(tidyverse)

years = as.character(1967:1979) |> set_names()

process_year = function(year_path) {
  pages = list.files(year_path, full.names = TRUE) |> map(\(x) fromJSON(x) |> as_tibble())
  pages
}

x = process_year("raw_ocr/1967")

df = x[[7]]

df |> 
  mutate(
    across(
      total_units:public_valuation,
      \(col) col |> 
        str_replace_all(" ", "") |>
        str_replace_all("-", "0") |>
        na_if("(X)") |>
        as.integer()
    ),
    smsa_group = cumsum(str_detect(smsa_name, "OUTSIDE") |> lag(default = 0)),
    outside_indicator = as.numeric(str_detect(smsa_name, "OUTSIDE")),
    inside_indicator = as.numeric(str_detect(smsa_name, "INSIDE"))
  ) |> 
  mutate(
    .by = smsa_group,
    smsa_indicator = as.numeric(row_number() == 1),
    city_indicator = as.numeric(
      smsa_indicator == 0 & !str_detect(smsa_name, "INSIDE|OUTSIDE")
    ),
  )
  
  
x



x[[7]]
