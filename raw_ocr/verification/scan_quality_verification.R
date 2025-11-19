library(jsonlite)
library(tidyverse)

gemini = fromJSON("output/test_extraction_1967_pages_1_2.json") |> 
  as_tibble() |> 
  mutate(
    across(
      total_units:last_col(),
      \(col) col |> 
        str_replace_all(" ", "") |>
        str_replace_all("-", "0") |>
        as.numeric()
    ),
    line_number = as.numeric(line_number)
  )

truth = read_csv("scan_verification/truth.csv") |> 
  mutate(
    across(
      total_units:last_col(),
      \(col) col |> 
        str_replace_all(" ", "") |>
        str_replace_all("-", "0") |>
        as.numeric()
    )
  )

truth_val = read_csv("scan_verification/truth_val.csv") |> 
  mutate(
    across(
      1:last_col(offset = 1),
      \(col) col |> 
        str_replace_all(" ", "") |>
        str_replace_all("-", "0") |>
        as.numeric()
    )
  ) |> 
  pivot_longer(!line_number)

truth |> 
  select(line_number, where(is.numeric)) |> 
  pivot_longer(!line_number) |> 
  left_join(
    gemini |> 
      select(line_number, where(is.numeric)) |> 
      pivot_longer(!line_number),
    by = c("line_number", "name"),
    suffix = c("_truth", "_gemini")
  ) |> 
  filter(value_truth != value_gemini)

truth_val |> 
  select(line_number, where(is.numeric)) |> 
  pivot_longer(!line_number) |> 
  left_join(
    gemini |> 
      select(line_number, where(is.numeric)) |> 
      pivot_longer(!line_number),
    by = c("line_number", "name"),
    suffix = c("_truth", "_gemini")
  ) |> 
  filter(value_truth != value_gemini)



truth |> 
  mutate(
    private_sum = rowSums(pick(private_1_unit:private_5plus_units))
  ) |> 
  filter(private_sum != private_total)




  
gemini

gemini_units = gemini |> 
  select(1:10)

gemini_units == truth

gemini_units

truth




truth = read_csv("scan_verification/test_1967.csv")
haiku = read_csv("scan_verification/haiku.csv")
sonnet = read_csv("scan_verification/sonnet.csv")
opus = read_csv("scan_verification/opus.csv")
gemini = read_csv("scan_verification/gemini.txt")
gemini_vertex = read_csv("scan_verification/gemini_vertex.csv")

names(truth)

# Write a function that takes a path as input and computes the similarity as below
read_ocr = function(path) {
  raw = read_csv(path)
  clean = raw |>
    select(!standard_metropolitan_statistical_area) |>
    mutate(
      across(
        everything(),
        \(col) col |>
          as.character() |>
          str_replace_all("-", "0") |>
          replace_na("0")
      )
    ) |> 
    pivot_longer(cols = !line_number)
}

gemini_vertex2 = read_ocr("scan_verification/gemini_vertex2.csv")

datasets$truth |>
  left_join(gemini_vertex2, join_by(line_number, name), suffix = c("_truth", "_other")) |> 
  # summarize(mean(value_truth == value_other))
  filter(value_truth != value_other)

View(opus)


haiku |>
  filter(line_number == 4)

datasets$haiku |>
  filter(line_number == 4)
