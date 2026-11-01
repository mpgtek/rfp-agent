# OpenAI marketplace packaging

`plugin.json` is the listing source; `assets/` contains the RFP icon. Runtime code is taken from the repository's small installation package instead of maintaining another skill copy.

Build with `python3 tools/build_marketplace.py`. Output goes to ignored `dist/`. Check with `python3 tools/check_marketplace.py`. Development tests and examples are not included.

Version 0.1.1 removes pricing language from the description. The previously uploaded 0.1.0 draft reported that OpenAI was not accepting additional skills-only submissions; rebuilding cannot remove that portal restriction. No marketplace submission or approval is claimed. Uploading a new version, completing policy attestations, submitting and publishing are separate actions.
