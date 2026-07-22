# Manual search and distribution routine

This directory records the ongoing manual work from Plan 06: search-console
ownership and health, content/distribution decisions, and the monthly
AI-search benchmark.

## Current launch decisions

- External product and guide copy launch in English. Members may still write
  activity names and entries in Korean.
- Mushin speaks to people tracking martial arts, reading, water and alcohol,
  general habits, and solo-founder work. Alcohol and water content must stay
  factual and non-medical.
- All eight current guides are approved. Do not feature member screenshots or
  real-record examples until a meaningful public record exists and its owner
  explicitly approves the use.
- There is no About or press page at launch.
- Search discovery is enabled by default for public accounts. Owners can opt
  out freely. A public, non-secret activity is eligible after its first visible
  public entry; private, fellows-only, secret, and hidden content is excluded.
  This differs from the current implementation and requires a product change
  before launch.
- On a valid removal request or report, immediately remove search eligibility,
  remove affected URLs from the sitemap, confirm `noindex`, use a temporary
  Google removal for urgent cases, and explain that external removal is not
  immediate.

## Open follow-ups

1. **Google sitemap:** Google Search Console currently reports "Couldn't
   fetch" for `https://mushin.aqnas.xyz/sitemap.xml`. The live endpoint has
   been checked externally: it returns `200 OK` as XML, does not redirect, and
   is declared by `robots.txt`. Leave the submission in place, check again
   after 24 hours, and inspect Cloudflare Security Events for a blocked
   Googlebot request if the error persists.
2. **Indie Hackers post:** prepare a useful, transparent solo-founder build
   story later. Explain how Mushin is used to track work, share an honest
   lesson or template, and follow the community's current promotion rules.
3. **Community participation:** the chosen initial communities are the
   founder's Kendo/dojo community, Indie Hackers, and one reading-tracker or
   book-club community where the founder already participates. Contribute a
   useful template or reflection, not generic launch promotion.

## Monthly review

Review on the first business day of each month, starting Monday, 3 August 2026.

- Check Search Console for sitemap processing errors, crawl exclusions,
  canonical disagreements, and `noindex` leaks.
- Record indexed pages, impressions, clicks, queries, and referring domains.
- Compare organic/referral acquisition with completed signups, first entries,
  and seven-day retention. These product metrics are not yet instrumented, so
  record them as unavailable rather than estimating them from visitor counts.
- Expand only guides and topics that bring visitors who create an activity and
  keep logging; improve or retire pages that only earn impressions.

## AI-search benchmark

This is Mushin's monthly manual benchmark for whether AI-search products cite,
link to, and accurately describe Mushin.

The benchmark deliberately uses browser-assisted human review. It does not
attempt to bypass sign-in, CAPTCHA, rate limits, or platform protections, and
it leaves the editorial judgment of whether a description is accurate to the
reviewer.

## Files

- `ai-search-benchmark.csv` is the benchmark record. It contains 15 fixed
  English-language questions and one set of result fields for Google AI,
  ChatGPT, Perplexity, and Bing/Copilot.
- `run_ai_search_benchmark.py` opens each question with Playwright CLI,
  saves screenshots, and records the reviewer's answers.
- `screenshots/` is created automatically and contains local evidence for
  each completed run.

## Run the benchmark

Install and make sure `playwright-cli` is available, then run this from the
repository root:

```sh
uv run python manual-routine/run_ai_search_benchmark.py --country "South Korea"
```

The runner starts a persistent browser session. Sign in only where you choose
to, submit each question, wait for the full result, then return to the
terminal. For every result, enter whether Mushin was cited, linked, and
accurately described. The runner saves the CSV after every reviewed result, so
it is safe to stop and resume.

ChatGPT and Perplexity open at their home pages. Paste and submit the printed
question yourself; their query URLs and page controls are not treated as stable
automation targets.

## Useful options

```sh
# Show the planned checks without opening a browser.
uv run python manual-routine/run_ai_search_benchmark.py --dry-run

# Run only one platform.
uv run python manual-routine/run_ai_search_benchmark.py --platform chatgpt

# Resume a particular monthly run.
uv run python manual-routine/run_ai_search_benchmark.py --date 2026-08-23 --country "South Korea"
```

Use a consistent signed-out or private browser context where practical, record
the country/region, and retain screenshots when Mushin appears. Do not treat a
missing citation as a failure to be corrected through manipulation; it is
baseline evidence.
