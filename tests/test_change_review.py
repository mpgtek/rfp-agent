import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from openpyxl import load_workbook

from rfp_agent.adapters import ingest
from rfp_agent.change_review import HEADERS, apply_review, export_changes
from rfp_agent.cli import main
from rfp_agent.db import Store
from rfp_agent.excel import literal


class ChangeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.store = Store(self.root / "data")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def stage(self, question="How is data encrypted?", answer="We use AES-256.", scope="product-a", submitter="source-import", **kwargs):
        with self.store.db:
            return self.store.stage(question=question, answer=answer, scope=scope, submitter=submitter,
                                    provenance={"source": "policy.md", "location": "section 3"}, **kwargs)

    def approve_initial(self):
        pid = self.stage()
        return self.store.resolve([pid], "initial-sme", "Reviewed policy")[0]

    def edit_xlsx(self, exported, updates, filename="returned.xlsx", subset=None):
        book = load_workbook(exported["path"])
        ws = book["KB change review"]
        ids = {int(ws.cell(n, HEADERS.index("proposal_id") + 1).value): n for n in range(2, ws.max_row + 1)}
        for pid, edits in updates.items():
            for key, value in edits.items():
                literal(ws.cell(ids[pid], HEADERS.index(key) + 1), value)
        if subset is not None:
            for pid, n in sorted(ids.items(), key=lambda x: x[1], reverse=True):
                if pid not in subset:
                    ws.delete_rows(n)
        path = self.root / filename
        book.save(path)
        book.close()
        return path

    def test_export_old_new_and_apply_sme_correction_with_history_and_replay(self):
        entry = self.approve_initial()
        pid = self.stage(answer="We encrypt stored data with AES-256 and rotate keys.")
        new = self.stage("Do you support SAML?", "We support SAML 2.0.")
        packet = export_changes(self.store, [pid, new], "product-a")
        book = load_workbook(packet["path"])
        ws = book["KB change review"]
        self.assertEqual("We use AES-256.", ws["B2"].value)
        self.assertIn("rotate keys", ws["C2"].value)
        self.assertEqual(ws["C2"].value, ws["D2"].value)
        self.assertEqual("Pending", ws["E2"].value)
        book.close()
        final = "We encrypt stored data with AES-256 and rotate managed keys annually."
        returned = self.edit_xlsx(packet, {pid: {"review_status": "Approved", "sme_name": "security-sme", "final_answer": final}})
        result = apply_review(self.store, returned)
        self.assertEqual(1, result["approved"])
        self.assertEqual(1, result["deferred"])
        self.assertEqual(final, self.store.evidence(entry["entry"])["answer"])
        history = self.store.db.execute("SELECT * FROM revisions WHERE entry_id=? ORDER BY id", (entry["entry"],)).fetchall()
        self.assertEqual(2, len(history))
        self.assertEqual("We use AES-256.", history[0]["answer"])
        provenance = json.loads(history[1]["provenance"])
        self.assertEqual("security-sme", provenance["sme_change_review"]["sme_name"])
        self.assertTrue(Path(provenance["sme_change_review"]["snapshot"]).is_file())
        self.assertEqual("pending", self.store.db.execute("SELECT status FROM proposals WHERE id=?", (new,)).fetchone()[0])
        replay = apply_review(self.store, returned)
        self.assertEqual(1, replay["replayed"])
        self.assertEqual(0, replay["approved"])
        self.assertEqual(2, self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])

    def test_changed_decision_after_application_requires_new_review(self):
        pid = self.stage()
        packet = export_changes(self.store)
        returned = self.edit_xlsx(packet, {pid: {"review_status": "Approved", "sme_name": "sme"}})
        apply_review(self.store, returned)
        changed = self.edit_xlsx(packet, {pid: {"review_status": "Rejected", "sme_name": "sme"}}, filename="changed.xlsx")
        with self.assertRaisesRegex(ValueError, "different decision"):
            apply_review(self.store, changed)

    def test_stale_review_blocks_all_rows_atomically(self):
        self.approve_initial()
        old = self.stage(answer="Candidate B")
        new = self.stage("New capability?", "Yes")
        packet = export_changes(self.store)
        later = self.stage(answer="Approved C")
        self.store.resolve([later], "other-sme", "New policy")
        returned = self.edit_xlsx(packet, {p: {"review_status": "Approved", "sme_name": "sme"} for p in (old, new)})
        with self.assertRaisesRegex(ValueError, "Stale review"):
            apply_review(self.store, returned)
        self.assertEqual([], self.store.retrieve("New capability?", "product-a"))
        self.assertEqual("pending", self.store.db.execute("SELECT status FROM proposals WHERE id=?", (new,)).fetchone()[0])

    def test_refresh_shows_latest_base_and_can_approve_old_pending_candidate(self):
        entry = self.approve_initial()
        candidate = self.stage(answer="Candidate B")
        later = self.stage(answer="Approved C")
        self.store.resolve([later], "other-sme", "New policy")
        packet = export_changes(self.store, [candidate])
        book = load_workbook(packet["path"])
        self.assertEqual("Approved C", book["KB change review"]["B2"].value)
        book.close()
        returned = self.edit_xlsx(packet, {candidate: {"review_status": "Approved", "sme_name": "sme"}})
        self.assertEqual(1, apply_review(self.store, returned)["approved"])
        self.assertEqual("Candidate B", self.store.evidence(entry["entry"])["answer"])

    def test_tampered_context_unknown_workspace_and_proposal_change_are_rejected(self):
        pid = self.stage()
        packet = export_changes(self.store)
        returned = self.edit_xlsx(packet, {pid: {"question": "Hijacked?", "review_status": "Approved", "sme_name": "sme"}})
        with self.assertRaisesRegex(ValueError, "context was changed"):
            apply_review(self.store, returned)
        returned = self.edit_xlsx(packet, {pid: {"review_status": "Approved", "sme_name": "sme"}})
        other = Store(self.root / "other")
        try:
            with self.assertRaisesRegex(ValueError, "Unknown review"):
                apply_review(other, returned)
        finally:
            other.close()
        with self.store.db:
            self.store.db.execute("UPDATE proposals SET answer='Changed since export' WHERE id=?", (pid,))
        with self.assertRaisesRegex(ValueError, "Proposal changed"):
            apply_review(self.store, returned)

    def test_empty_answer_missing_reviewer_and_self_approval_block_batch(self):
        pid = self.stage(submitter="sme")
        packet = export_changes(self.store)
        for edits, message in [({"review_status": "Approved"}, "sme_name"),
                               ({"review_status": "Approved", "sme_name": "sme"}, "own proposal"),
                               ({"review_status": "Approved", "sme_name": "other", "final_answer": ""}, "cannot be blank")]:
            returned = self.edit_xlsx(packet, {pid: edits})
            with self.assertRaisesRegex(ValueError, message):
                apply_review(self.store, returned)
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])

    def test_rejected_and_needs_review_do_not_change_approved_kb(self):
        first = self.stage()
        second = self.stage("Another?", "Another answer")
        packet = export_changes(self.store)
        returned = self.edit_xlsx(packet, {first: {"review_status": "Rejected", "sme_name": "sme"},
                                          second: {"review_status": "Needs review", "final_answer": "Unapproved edit"}})
        result = apply_review(self.store, returned)
        self.assertEqual(1, result["rejected"])
        self.assertEqual(1, result["deferred"])
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
        self.assertEqual("Another answer", self.store.db.execute("SELECT answer FROM proposals WHERE id=?", (second,)).fetchone()[0])

    def test_partial_return_and_duplicate_rows(self):
        one = self.stage()
        two = self.stage("Another?", "Another answer")
        packet = export_changes(self.store)
        returned = self.edit_xlsx(packet, {two: {"review_status": "Approved", "sme_name": "sme"}}, subset={two})
        self.assertEqual(1, apply_review(self.store, returned)["approved"])
        packet = export_changes(self.store, [one])
        returned = self.edit_xlsx(packet, {one: {"review_status": "Approved", "sme_name": "sme"}})
        book = load_workbook(returned)
        ws = book["KB change review"]
        ws.append([c.value for c in ws[2]])
        book.save(returned)
        book.close()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            apply_review(self.store, returned)

    def test_multiple_approvals_for_same_question_are_not_silently_overwritten(self):
        one = self.stage(answer="Option one")
        two = self.stage(answer="Option two")
        packet = export_changes(self.store)
        returned = self.edit_xlsx(packet, {p: {"review_status": "Approved", "sme_name": "sme"} for p in (one, two)})
        with self.assertRaisesRegex(ValueError, "Multiple Approved"):
            apply_review(self.store, returned)
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def test_formula_cells_rejected_and_formula_looking_source_stored_as_text(self):
        pid = self.stage(question='=HYPERLINK("https://example.invalid")', answer='=not-a-formula')
        packet = export_changes(self.store)
        book = load_workbook(packet["path"])
        ws = book["KB change review"]
        self.assertEqual("s", ws["A2"].data_type)
        self.assertEqual("s", ws["D2"].data_type)
        ws["D2"] = "=1+1"
        ws["E2"] = "Approved"
        ws["F2"] = "sme"
        path = self.root / "formula.xlsx"
        book.save(path)
        book.close()
        with self.assertRaisesRegex(ValueError, "Formula"):
            apply_review(self.store, path)

    def test_csv_roundtrip_preserves_literal_answer_and_updates_kb(self):
        pid = self.stage(answer="=literal answer")
        packet = export_changes(self.store, file_format="csv")
        with Path(packet["path"]).open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream))
        self.assertTrue(records[0]["proposed_answer"].startswith("'="))
        records[0]["review_status"] = "Approved"
        records[0]["sme_name"] = "sme"
        returned = self.root / "returned.csv"
        with returned.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(records)
        self.assertEqual(1, apply_review(self.store, returned)["approved"])
        self.assertEqual("=literal answer", self.store.retrieve("How is data encrypted?", "product-a")[0]["answer"])

    def test_cli_ingest_generates_packet_and_recognizes_returned_review(self):
        with self.store.db:
            initial = self.store.stage(question="Do you support SAML?", answer="We do not support SAML.",
                                       scope="product-a", provenance={}, submitter="initial-source")
        self.store.resolve([initial], "initial-sme", "Initial existing answer")
        source = self.root / "qa.csv"
        source.write_text("Question,Answer\nDo you support SAML?,We support SAML 2.0\n")
        with redirect_stdout(io.StringIO()) as output:
            code = main(["--workspace", str(self.store.root), "ingest", str(source), "--scope", "product-a"])
        self.assertEqual(0, code)
        data = json.loads(output.getvalue())
        self.assertTrue(Path(data["change_review"]["path"]).is_file())
        pid = data["proposal_ids"][0]
        returned = self.edit_xlsx(data["change_review"], {pid: {"review_status": "Approved", "sme_name": "sme"}})
        with redirect_stdout(io.StringIO()) as output:
            code = main(["--workspace", str(self.store.root), "ingest", str(returned)])
        self.assertEqual(0, code)
        self.assertEqual(1, json.loads(output.getvalue())["review_applied"]["approved"])

    def test_unknown_status_aborts_without_updating_rows(self):
        one = self.stage()
        two = self.stage("Another?", "Another")
        packet = export_changes(self.store)
        returned = self.edit_xlsx(packet, {one: {"review_status": "Approved", "sme_name": "sme"},
                                          two: {"review_status": "Maybe"}})
        with self.assertRaisesRegex(ValueError, "Review status"):
            apply_review(self.store, returned)
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def test_unchanged_reimport_has_no_new_pending_review(self):
        source = self.root / "qa.csv"
        source.write_text("Question,Answer\nEncryption?,We use AES-256\n")
        ids = ingest(self.store, source, "product-a")
        self.store.resolve(ids, "sme", "Reviewed")
        self.assertIsNone(export_changes(self.store, ingest(self.store, source, "product-a")))

    def test_approval_of_edited_variant_answer_is_rejected(self):
        entry = self.approve_initial()
        pid = self.stage("Encrypted storage?", "We use AES-256.", kind="variant", target=entry["entry"])
        packet = export_changes(self.store, [pid])
        returned = self.edit_xlsx(packet, {pid: {"review_status": "Approved", "sme_name": "sme", "final_answer": "Different canonical answer"}})
        with self.assertRaisesRegex(ValueError, "Variant answer differs"):
            apply_review(self.store, returned)
        self.assertEqual("pending", self.store.db.execute("SELECT status FROM proposals WHERE id=?", (pid,)).fetchone()[0])
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
