# Validation

The standalone suite contains 142 automated tests for import/versioning, scoped retrieval, item-level partial answers, unknown blanks, preserved DOCX/XLSX output, named-SME approvals, collision review, stale contexts, repeat uploads and state isolation. Run `python -m unittest discover -s tests -v` after installing the project.

The separately packaged marketplace plugin includes two additional enclosing-plugin layout tests. Those tests are not applicable to this standalone repository.

No live Confluence, Notion, Jev or GPT Decisions connection is claimed. Automated workflow tests do not establish production answer accuracy or marketplace approval.

## Installation package

The allowlisted installation ZIP excludes tests, examples, scenario documents, Git history and development tools. A fresh extraction passed dependency-free discovery, offline bootstrap with installed libraries, fixture generation and the full synthetic demo in an isolated temporary workspace. No production workspace was used. The 142-test suite passed again after packaging changes. CI runs the same package checks.
