# Building the colby! tour book

The live site is the files at the repo root (GitHub Pages, main branch, `/` root).
`index.html` holds the tour data encrypted with the band password (AES-GCM, PBKDF2 250k),
so nothing readable about dates, contacts or travel is in this public repo.

What lives here:
- `template.html` – the whole app (HTML/CSS/JS). No tour data.
- `build_site.py` – encrypts `data.js` into `index.html` and writes icons, manifest, service worker.
- `Code.gs` – optional Google Apps Script backend for shared guest lists and travel screenshots.

The tour data (`data.js`), photos and password are kept privately in the Colby! project files
(`colby/tour-app/`), not in this repo.

Rebuild:

    python3 -I _build/build_site.py <abs source dir> <abs repo dir> '<password>' [api.json]

The source dir holds only template.html, data.js, logo-mask.png, photo-hero.jpg, photo-wide.jpg
and the PDFs. Then commit and push to main; phones pick up the new version on next open.
