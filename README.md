# Birmingham Healthy Life

### [Visit the live site ↗](https://tidyweb.github.io/Birmingham-Healthy-Life/)


The project site for my Code Institute Unit 2 assessment. It's served by GitHub Pages at https://tidyweb.github.io/Birmingham-Healthy-Life/.

The notebooks and data are in the assessment repository: https://github.com/TidyWeb/Code-Institute-DA-with-AI-Unit-2-Assessment

## What's where

- `content/`: the text for the home page and each chapter, in Markdown. Edit these.
- `tools/build_site.py`: turns `content/` and the executed notebooks into the HTML pages.
- `assets/site.css`, `assets/site.js`: the look and the small page behaviours.
- `assets/img/`: screenshots, kept by hand.
- `dashboard/`: my own dashboard, unchanged apart from a "Back" button that the build adds. It returns to whichever page you came from.
- `index.html`, `story/`, `notebooks/`, `assets/figures/`, `assets/nb/`: built by the script. Don't edit these; they're rewritten on every build.

## Rebuild after editing

```
"/home/Phil/C_C/Learn_Python_Data/Working Files/Unit 2/MAIN_PROJECT/Birmingham HLE/VS_CODE/.venv/bin/python" tools/build_site.py
```

To check every link and image afterwards, run `tools/check_links.py` with the same Python. Add `--web` to check the external sites too. GitHub sometimes refuses scripted checks with a 503 even when the page exists.

To look at it locally, run `python3 -m http.server 8765` in this folder and open http://localhost:8765/.

## Block markers in the content files

Use these alongside ordinary Markdown:

- `::: keypoints`: the "In short" box at the top of a chapter.
- `::: stats nb04#cellid`: a slate panel of numbers. Each line is `value | label`.
- `::: figure folder/name [wide] nb05#cellid`: a saved notebook figure on a plate. The folder is one of `wide`, `neighbours`, `ml` or `hotspots`. Add `alt:` and `caption:` lines.
- `::: image file.webp [wide]`: a screenshot from `assets/img`, with `alt:` and `caption:` lines.
- `::: callout`: one sentence set large.
- `::: tableau`: the Tableau embed with its screenshot.
- `:::`: closes a block.
- `^ nb04#cellid | note`: a margin note for the paragraph after it. It links to that cell on the notebook page.

The cell ids come from the notebooks themselves, so every note points at the cell that produced the number.
