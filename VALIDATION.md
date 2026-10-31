# Validation

The standalone suite contains 142 automated tests for import/versioning, scoped retrieval, item-level partial answers, unknown blanks, preserved DOCX/XLSX output, named-SME approvals, collision review, stale contexts, repeat uploads and state isolation. Run `python -m unittest discover -s tests -v` after installing the project.

The separately packaged marketplace plugin includes two additional enclosing-plugin layout tests. Those tests are not applicable to this standalone repository.

No live Confluence, Notion, Jev or GPT Decisions connection is claimed. Automated workflow tests do not establish production answer accuracy or marketplace approval.
