# Done

## Extraction
- Tried multiple LLMs -- Gemini 3 worked the best
- Extracted scanned BPS tables using Gemini OCR
 - Tried multiple times for connection errors, empty row files, consistently misread files
 - If a page failed to be read after 3+ tries, increased temperature to 1
  - 1972\pages_29_30.json: no rows
  - 1979\pages_09_10.json: no rows
  - 1979\pages_17_18.json: no rows
  - 1979\pages_27_28.json: no rows
  - 1978\pages_23_24.json: misinterpreted private structures as public permits


# To-dos

## Validation
- Validate specific pages of Gemini output against PDFs
- Rerun pages that failed
- Turn into CSV
- Manual correction at the end

## Cleaning
- Clean MSA names
- Set indicators for overall MSA, central city, outside central city (different for 1970)
 - Use "outside central city" cumsum
- Standardize MSA names across years + create IDs
- Extract and standardize states
- Create and join state NEPA adoption dates

## Data exploration
- Permit universe expansion
 - Plots of permits over time to check for discontinuities overall, at MSA level, across states/regions
 - Try imputation -- does it look okay?
 - Did imputation occur within MSAs or only across MSAs?
- MSA expansion
 - How did the number of MSAs represented in the data change over time?
 - What kinds of jumps were there around MSA definition changes?
  - When were the MSA definition changes?
- Get "Table 1" info
 - Population of MSAs, regional distribution. Map over time?

## First pass at effects
- Create derived columns with logs
- Event-time plots of log permits and valuations at MSA level

## Steps with time
- Add data from 1980-1983 (additional data cleaning and merging)

## Supplemental
- Check effects at city level -- spillover interepretation? Is triple diff interpretable?

# MSA definitions
- 1967-69: "as established in 1967"
- 1970: no information
- 1971-72: "as established in 1967 and amended to January 1972"
- 1973: "as established in 1967 and amended to November 1973"
- 1974: "as established in 1967 and amended to April 1974"
- 1975: "as established in 1974 and amended to August 1975"
- 1976: "as established in 1975"
- 1977: "as established in 1975 and amended to June 1977"
- 1978: "as established in 1975 and amended to November 1978"
- 1979: "as established in 1975 and amended to November 1979"


