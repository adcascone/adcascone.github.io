# adcascone.github.io

Source for my personal website, [adcascone.github.io](https://adcascone.github.io/), built with [Quarto](https://quarto.org), Python, and Observable JS.

## What's here

| Path | What it is |
|---|---|
| `index.qmd`, `about.qmd`, `projects.qmd`, `research.qmd`, `soccer.qmd` | The pages |
| `soccer_articles.yml`, `scientific_papers.yml` | Data the Soccer and Science pages are built from |
| `assets/` | Theme (light/dark SCSS), fonts and icons, the homepage network animation, project images |
| `scripts/update_articles.py` | Adds new articles to `soccer_articles.yml` |
| `.github/workflows/publish.yml` | Renders the site and publishes it to the `gh-pages` branch |

## Publishing

The workflow runs:

- on every push to `main`;
- every Monday and Thursday, after checking my Equalizer Soccer author feed for new articles (new ones are committed automatically);
- on demand, from the **Actions** tab → **Update articles and publish site** → **Run workflow**.

## Adding an ESPN article

ESPN doesn't publish an author feed, so add those by link:

```bash
pip install requests pyyaml
python scripts/update_articles.py --espn https://www.espn.com/soccer/story/_/id/...
```

Then commit and push `soccer_articles.yml`. Use `--dry-run` to preview without changing the file.

## Previewing locally

```bash
pip install pyyaml jupyter
quarto preview
```
