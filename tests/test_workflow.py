import io
import json
import subprocess
import sys
import tempfile
import unittest
import shutil
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation

from rfp_agent.adapters import ingest
from rfp_agent.cli import main
from rfp_agent.db import Store
from rfp_agent.demo import fixtures, run_demo
from rfp_agent.corpus import LEARNED_ANSWER, knowledge_records, rfp_cases
from rfp_agent.excel import REVIEW_HEADERS, extract, literal, patch_copy
from rfp_agent.providers import BridgeGenerator, GPTDecisionsAdapter, JevDecisionAdapter, TaskRouter
from rfp_agent.workflow import answer_rfp, draft, ingest_feedback


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data")
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def approved(self, q="Do you encrypt stored data?", a="Stored data uses synthetic encryption.", scope="product-a"):
        with self.store.db:
            pid = self.store.stage(question=q, answer=a, scope=scope, provenance={"location": "test:1"}, submitter="sme")
        return self.store.resolve([pid], "approver", "Reviewed test evidence")[0]

    def rfp(self, questions=None):
        book = Workbook()
        ws = book.active
        ws.title = "RFP"
        ws.append(["Question", "Response", "Other"])
        for q in questions or ["Do you encrypt stored data?"]:
            ws.append([q, None, "preserve"])
        ws["D2"] = "=1+2"
        path = self.inputs / "rfp.xlsx"
        book.save(path)
        book.close()
        return path

    def edit_review(self, run, updates):
        path = Path(run["output"]) / "feedback.xlsx"
        from rfp_agent.excel import review_book
        review_book(Path(run["output"])/"sme-review.xlsx",json.loads((Path(run["output"])/"drafts.json").read_text()))
        book = load_workbook(Path(run["output"]) / "sme-review.xlsx")
        ws = book["SME review"]
        for key, value in dict(reviewer="sme", review_note="Checked policy", **updates).items():
            literal(ws.cell(2, REVIEW_HEADERS.index(key) + 1), value)
        book.save(path)
        book.close()
        return path

    def test_pending_is_invisible_and_self_approval_forbidden(self):
        with self.store.db:
            pid = self.store.stage(question="Encryption?", answer="Yes", scope="a", provenance={}, submitter="sme")
        self.assertEqual([], self.store.retrieve("Encryption?", "a"))
        with self.assertRaisesRegex(ValueError, "Submitter"):
            self.store.resolve([pid], "SME", "reason")
        self.store.resolve([pid], "approver", "reviewed")
        self.assertEqual(1, len(self.store.retrieve("Encryption?", "a")))

    def test_import_idempotence_and_source_versioning(self):
        p = self.inputs / "kb.csv"
        p.write_text("Question,Answer\nEncryption?,Version one\n")
        ids = ingest(self.store, p, "a")
        self.store.resolve(ids, "approver", "first")
        self.assertEqual(ids, ingest(self.store, p, "a"))
        p.write_text("Question,Answer\nEncryption?,Version two\n")
        changed = ingest(self.store, p, "a")
        self.assertNotEqual(ids, changed)
        self.assertEqual("needs-review", draft(self.store, "Encryption?", "a")["status"])
        self.store.resolve(changed, "approver", "updated")
        self.assertEqual("Version two", self.store.retrieve("Encryption?", "a")[0]["answer"])
        revisions = self.store.db.execute("SELECT * FROM revisions ORDER BY id").fetchall()
        self.assertEqual(2, len(revisions))
        prov = json.loads(revisions[0]["provenance"])
        self.assertEqual("Question,Answer\nEncryption?,Version one\n", Path(prov["snapshot"]).read_text())
        self.assertEqual("record:2", prov["location"])

    def test_scope_isolation_and_no_external_calls_without_evidence(self):
        self.approved()
        router = TaskRouter()
        self.assertEqual("insufficient", draft(self.store, "Do you encrypt stored data?", "other", router)["status"])
        self.assertEqual(0, router.calls)

    def test_pending_conflicting_import_case_variant_blocks_confidence(self):
        source = self.inputs / "conflict.csv"
        source.write_text("Question,Answer\nEncryption?,Yes\nENCRYPTION?,No\n")
        ids = ingest(self.store, source, "a")
        self.store.resolve([ids[0]], "approver", "Reviewed first source record")
        self.assertEqual("needs-review", draft(self.store, "Encryption?", "a")["status"])

    def test_duplicate_question_records_merge_provenance_and_replay(self):
        source = self.inputs / "duplicates.csv"
        source.write_text("Question,Answer\nEncryption?,Yes\nENCRYPTION?,Yes\n")
        ids = ingest(self.store, source, "a")
        self.assertEqual(1, len(ids))
        self.store.resolve(ids, "approver", "Reviewed both source records")
        evidence = self.store.retrieve("Encryption?", "a")[0]
        self.assertEqual(2, len(json.loads(evidence["provenance"])["source_observations"]))
        self.assertEqual(ids, ingest(self.store, source, "a"))
        self.assertEqual(1, self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])

    def test_exact_variant_freshness_commitments(self):
        info = self.approved()
        self.assertEqual("high-confidence", draft(self.store, "Do you encrypt stored data?", "product-a")["status"])
        with self.store.db:
            pid = self.store.stage(question="Is storage encrypted?", answer="Stored data uses synthetic encryption.",
                scope="product-a", provenance={}, submitter="sme", kind="variant", target=info["entry"])
        self.assertNotEqual("high-confidence", draft(self.store, "Is storage encrypted?", "product-a")["status"])
        self.store.resolve([pid], "approver", "equivalence checked")
        self.assertEqual("high-confidence", draft(self.store, "Is storage encrypted?", "product-a")["status"])
        with self.store.db:
            self.store.db.execute("UPDATE revisions SET approved_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual("needs-review", draft(self.store, "Is storage encrypted?", "product-a")["status"])
        self.approved("Do you guarantee an SLA?", "See contract for SLA terms.")
        self.assertEqual("needs-review", draft(self.store, "Do you guarantee an SLA?", "product-a")["status"])

    def test_revision_change_invalidates_old_variants(self):
        info = self.approved()
        with self.store.db:
            variant = self.store.stage(question="Encrypted storage?", answer="Stored data uses synthetic encryption.",
                scope="product-a", provenance={}, submitter="sme", kind="variant", target=info["entry"])
        self.store.resolve([variant], "approver", "reviewed")
        with self.store.db:
            update = self.store.stage(question="Do you encrypt stored data?", answer="New approved answer", scope="product-a",
                provenance={"version": 2}, submitter="sme")
        self.store.resolve([update], "approver", "change reviewed")
        self.assertNotEqual("high-confidence", draft(self.store, "Encrypted storage?", "product-a")["status"])

    def test_stale_approval_is_atomic(self):
        self.approved()
        with self.store.db:
            ids = [self.store.stage(question="Do you encrypt stored data?", answer=f"Update {i}", scope="product-a",
                                   provenance={"v": i}, submitter="sme") for i in (1, 2)]
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.store.resolve(ids, "approver", "batch")
        self.assertEqual("Stored data uses synthetic encryption.", self.store.retrieve("Do you encrypt stored data?", "product-a")[0]["answer"])
        self.assertEqual(2, self.store.db.execute("SELECT COUNT(*) FROM proposals WHERE status='pending'").fetchone()[0])

    def test_conflicting_variant_cannot_hijack_canonical(self):
        one = self.approved("Alpha?", "Alpha answer")
        self.approved("Beta?", "Beta answer")
        with self.store.db:
            pid = self.store.stage(question="Beta?", answer="Alpha answer", scope="product-a", provenance={},
                                   submitter="sme", kind="variant", target=one["entry"])
        with self.assertRaisesRegex(ValueError, "different canonical"):
            self.store.resolve([pid], "approver", "bad equivalence")

    def test_retrieval_query_punctuation_and_fts(self):
        self.approved()
        self.assertTrue(self.store.retrieve('stored data " OR encrypt* -- (?', "product-a"))
        self.assertEqual([], self.store.retrieve('"*():', "product-a"))
        self.assertEqual([], self.store.retrieve("stored data", "wrong-scope"))

    def test_all_four_statuses(self):
        self.approved("Do you support encryption at rest?", "Encryption at rest is configured.")
        expected = [("Do you support encryption at rest?", "high-confidence"),
                    ("Describe encryption at rest", "needs-review"),
                    ("Explain encryption at rest and lunar gardens ocean submarines weather", "partial"),
                    ("Zyzzyva?", "insufficient")]
        for q, status in expected:
            self.assertEqual(status, draft(self.store, q, "product-a")["status"], q)

    def test_archive_preservation_and_literal_formula_text(self):
        source = self.rfp()
        before = source.read_bytes()
        dest = self.root / "patched.xlsx"
        patch_copy(source, dest, {"RFP": {"B2": '=HYPERLINK("https://example.invalid")'}})
        self.assertEqual(before, source.read_bytes())
        with ZipFile(source) as one, ZipFile(dest) as two:
            for name in one.namelist():
                if name != "xl/worksheets/sheet1.xml":
                    self.assertEqual(one.read(name), two.read(name), name)
        book = load_workbook(dest)
        self.assertEqual("s", book["RFP"]["B2"].data_type)
        self.assertEqual("=1+2", book["RFP"]["D2"].value)
        book.close()

    def test_existing_blank_cell_style_survives_patch(self):
        from openpyxl.styles import PatternFill
        source = self.rfp()
        book = load_workbook(source)
        book.active["B2"].fill = PatternFill("solid", fgColor="FF0000")
        book.save(source)
        book.close()
        patch_copy(source, self.root / "style.xlsx", {"RFP": {"B2": "hello & <world>"}})
        book = load_workbook(self.root / "style.xlsx")
        self.assertEqual("hello & <world>", book.active["B2"].value)
        self.assertEqual("00FF0000", book.active["B2"].fill.fgColor.rgb)
        book.close()

    def test_prefilled_validated_and_merged_cells_preserved(self):
        self.approved()
        source = self.rfp(["Do you encrypt stored data?"] * 4)
        book = load_workbook(source)
        ws = book.active
        ws["B2"] = "Existing customer answer"
        ws["B3"] = "=1+1"
        dv = DataValidation(type="list", formula1='"Yes,No"')
        ws.add_data_validation(dv)
        dv.add("B4")
        ws.merge_cells("B5:C5")
        book.save(source)
        book.close()
        run = answer_rfp(self.store, source, "product-a")
        book = load_workbook(Path(run["output"]) / "completed.xlsx")
        self.assertEqual("Existing customer answer", book.active["B2"].value)
        self.assertEqual("=1+1", book.active["B3"].value)
        self.assertIsNone(book.active["B4"].value)
        self.assertIsNone(book.active["B5"].value)
        book.close()

    def test_ambiguous_layout_refuses_and_explicit_mapping_works(self):
        source = self.rfp()
        book = load_workbook(source)
        book.active["D1"] = "Answer"
        book.save(source)
        book.close()
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            extract(source)
        layout, rows = extract(source, sheet="RFP", header_row=1, question_column="A", response_column="B")
        self.assertEqual(1, len(rows))

    def test_feedback_stages_then_approves_learning_with_replay(self):
        source = self.rfp(["Do you support a zyzzyva integration?"])
        run = answer_rfp(self.store, source, "product-a")
        path = self.edit_review(run, {"action": "canonical", "corrected_answer": "No zyzzyva integration is offered."})
        ids = ingest_feedback(self.store, path)
        self.assertEqual("insufficient", draft(self.store, "Do you support a zyzzyva integration?", "product-a")["status"])
        self.store.resolve(ids, "approver", "SME confirmed")
        self.assertEqual("high-confidence", draft(self.store, "Do you support a zyzzyva integration?", "product-a")["status"])
        self.assertEqual(ids, ingest_feedback(self.store, path))

    def test_canonical_feedback_updates_revision_and_history(self):
        first = self.approved()
        run = answer_rfp(self.store, self.rfp(), "product-a")
        path = self.edit_review(run, {"action": "canonical", "corrected_answer": "Updated synthetic encryption policy."})
        ids = ingest_feedback(self.store, path)
        self.assertEqual("needs-review", draft(self.store, "Do you encrypt stored data?", "product-a")["status"])
        self.store.resolve(ids, "approver", "Policy update")
        self.assertEqual("Updated synthetic encryption policy.", self.store.evidence(first["entry"])["answer"])
        self.assertEqual(2, self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])
        self.assertEqual(ids, ingest_feedback(self.store, path))

    def test_feedback_rejects_tampering_unknown_target_and_stale_revision(self):
        first = self.approved()
        run = answer_rfp(self.store, self.rfp(), "product-a")
        for changes, message in [({"question": "Changed question"}, "Question"),
                                 ({"target_entry": 999}, "Target")]:
            path = self.edit_review(run, dict(action="canonical", corrected_answer="Update", **changes))
            with self.assertRaisesRegex(ValueError, message):
                ingest_feedback(self.store, path)
        self.approved(a="Another revision")
        path = self.edit_review(run, {"action": "canonical", "corrected_answer": "Update"})
        with self.assertRaisesRegex(ValueError, "stale"):
            ingest_feedback(self.store, path)

    def test_feedback_requires_explicit_reviewer_and_correction(self):
        run = answer_rfp(self.store, self.rfp(), "product-a")
        path = self.edit_review(run, {"action": "canonical"})
        with self.assertRaisesRegex(ValueError, "corrected_answer"):
            ingest_feedback(self.store, path)
        path = self.edit_review(run, {"action": "reject"})
        self.assertEqual([], ingest_feedback(self.store, path))
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])

    def test_persistence_across_connections(self):
        self.approved()
        self.store.close()
        self.store = Store(self.root / "data")
        self.assertEqual("high-confidence", draft(self.store, "Do you encrypt stored data?", "product-a")["status"])

    def test_workspace_cannot_be_under_code(self):
        repo = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError, "outside"):
            Store(repo / "persistent-data")

    def test_directory_adapters_docx_text_csv_and_exports(self):
        directory = fixtures(self.inputs / "fixtures")
        adapter_inputs = self.inputs / "adapter-inputs"
        adapter_inputs.mkdir()
        for name in ("knowledge.xlsx", "explicit.md", "explicit.txt", "explicit.csv", "explicit.docx", "confluence.json", "notion.json"):
            shutil.copyfile(directory / name, adapter_inputs / name)
        ids = ingest(self.store, adapter_inputs, "synthetic")
        self.assertEqual(106, len(ids))
        self.store.resolve(ids, "approver", "Reviewed synthetic batch")
        self.assertTrue(self.store.retrieve("Who owns fictional operations?", "synthetic"))
        self.assertTrue(self.store.retrieve("What is the fictional notion process?", "synthetic"))

    def test_malformed_directory_rolls_back_entire_import(self):
        (self.inputs / "good.csv").write_text("Question,Answer\nQ?,A\n")
        (self.inputs / "bad.json").write_text('{"provider":"notion","records":[{}]}')
        with self.assertRaises(ValueError):
            ingest(self.store, self.inputs, "synthetic")
        self.assertEqual(0, self.store.db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0])

    def test_cli_error_exit_and_json_success(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, main(["--workspace", str(self.root / "cli"), "init"]))
        self.assertTrue(json.loads(output.getvalue())["fts5"])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(2, main(["--workspace", str(self.root / "cli"), "approve", "99", "--actor", "a", "--reason", "r"]))

    def test_cli_module_has_nonzero_error_exit(self):
        proc = subprocess.run([sys.executable, "-m", "rfp_agent", "--workspace", str(self.root / "cli"),
                               "ingest", str(self.root / "missing.xlsx"), "--scope", "a"], capture_output=True)
        self.assertEqual(2, proc.returncode)

    def test_synthetic_vertical_slice(self):
        result = run_demo(self.root / "full-demo")
        self.assertEqual(100, result["knowledge_records"])
        self.assertEqual(1, result["high_confidence_improvement"])
        self.assertEqual(["xl/worksheets/sheet1.xml"], result["workbook_parts_changed"])
        self.assertEqual([], result["retrieval_benchmark"]["incorrect_high_confidence_case_ids"])
        self.assertEqual(20, result["coverage_domains"])
        drafts = json.loads((Path(result["second"]["output"]) / "drafts.json").read_text())
        self.assertEqual(LEARNED_ANSWER, drafts[24]["answer"])
        self.assertEqual("needs-review", drafts[24]["status"])

    def test_realistic_corpus_is_distinct_substantive_and_varied(self):
        from rfp_agent.db import norm
        import re
        records = knowledge_records()
        self.assertEqual(100, len(records))
        self.assertEqual(100, len({norm(r["question"]) for r in records}))
        self.assertEqual(100, len({re.sub(r"\d+", "N", norm(r["question"])) for r in records}),
                         "Changing a service number must not count as a distinct requirement")
        self.assertEqual(100, len({r["answer"] for r in records}))
        self.assertEqual(20, len({r["category"] for r in records}))
        self.assertTrue(all(len(r["answer"]) >= 140 for r in records))
        self.assertGreaterEqual(sum(r["capability"] == "not supported" for r in records), 10)
        self.assertGreaterEqual(sum(r["capability"] == "conditional" for r in records), 20)
        self.assertTrue(all(r["owner"] and r["evidence_section"] and r["synthetic"] for r in records))
        self.assertFalse(any("service 1" in r["question"] or "zyzzyva" in r["question"] for r in records))
        self.assertEqual(30, len({r["question"] for r in rfp_cases()}))

    def test_realistic_excel_retains_source_owner_and_evidence_metadata(self):
        directory = fixtures(self.inputs / "fixtures")
        ids = ingest(self.store, directory / "knowledge.xlsx", "meridian")
        proposal = self.store.db.execute("SELECT provenance FROM proposals WHERE id=?", (ids[22],)).fetchone()
        meta = json.loads(proposal[0])["source_metadata"]
        self.assertEqual("not supported", meta["capability"])
        self.assertEqual("Platform security engineer", meta["owner"])
        self.assertEqual("5.3", meta["evidence section"])
        self.assertEqual("SIMULATED INTERNAL EVIDENCE", meta["evidence kind"])

    def test_regulatory_reports_and_negative_capabilities_are_not_overstated(self):
        directory = fixtures(self.inputs / "fixtures")
        ids = ingest(self.store, directory / "knowledge.xlsx", "meridian")
        self.store.resolve(ids, "approver", "Synthetic scenario, not actual attestations")
        self.assertEqual("needs-review", draft(self.store, "Is a SOC 2 Type II report available?", "meridian")["status"])
        negative = draft(self.store, "Are customer-managed encryption keys supported?", "meridian")
        self.assertEqual("high-confidence", negative["status"])
        self.assertTrue(negative["answer"].startswith("No."))
        for case in rfp_cases():
            if case["kind"] in {"compound-or-trap", "missing-knowledge", "commitment-review"}:
                self.assertNotEqual("high-confidence", draft(self.store, case["question"], "meridian")["status"])


class ProviderTests(unittest.TestCase):
    def settings(self, provider="json_bridge"):
        return {"provider": provider, "model": "test-only", "endpoint": "http://localhost:8888/test", "allow_network": True}

    def evidence(self):
        return [{"id": 1, "revision": 3, "answer": "Stored data is encrypted."}]

    def test_generator_accepts_only_cited_verbatim_evidence(self):
        bridge = BridgeGenerator(self.settings(), "answer_generation", transport=lambda payload: {
            "answer": "Stored data is encrypted.", "revision_ids": [3]})
        self.assertEqual("Stored data is encrypted.", bridge.generate("q", self.evidence())["answer"])
        for output in [{"answer": "We guarantee universal compliance.", "revision_ids": [3]},
                       {"answer": "Stored data is encrypted.", "revision_ids": [999]},
                       {"answer": "text", "revision_ids": []}]:
            bridge.transport = lambda payload: output
            with self.assertRaises(ValueError):
                bridge.generate("q", self.evidence())

    def test_optional_decision_adapters_use_bridge_contract(self):
        for cls, provider in [(JevDecisionAdapter, "jev_bridge"), (GPTDecisionsAdapter, "gpt_decisions_bridge")]:
            captured = []
            def transport(payload):
                captured.append(payload)
                return {"supported": True, "requires_review": True}
            bridge = cls(self.settings(provider), "verification", transport=transport)
            self.assertTrue(bridge.evaluate("q", self.evidence(), "a")["requires_review"])
            self.assertEqual("rfp-agent.bridge.v1", captured[0]["contract"])
            bridge.transport = lambda payload: {"supported": "true", "requires_review": 0}
            with self.assertRaises(ValueError):
                bridge.evaluate("q", [], "a")

    def test_task_models_and_call_limit(self):
        router = TaskRouter({"limits": {"max_external_calls": 1}, "tasks": {
            "answer_generation": self.settings(), "verification": self.settings("jev_bridge")}})
        with patch("rfp_agent.providers.JsonBridge._http", return_value={"answer": "Stored data is encrypted.", "revision_ids": [3]}):
            self.assertTrue(router.generate("q", self.evidence())["answer"])
        with self.assertRaisesRegex(ValueError, "budget"):
            router.evaluate("verification", "q", [], "a")
        self.assertEqual(1, len(router.usage))

    def test_no_network_without_explicit_opt_in(self):
        settings = dict(self.settings(), allow_network=False)
        with self.assertRaisesRegex(ValueError, "allow_network"):
            JevDecisionAdapter(settings, "verification")

    def test_task_config_is_routed_and_invalid_provider_task_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "models.toml"
            config.write_text('[limits]\nmax_external_calls=2\n[tasks.answer_generation]\nprovider="extractive"\n'
                              '[tasks.verification]\nprovider="gpt_decisions_bridge"\nmodel="decision-test"\n'
                              'endpoint="http://localhost:8888/test"\nallow_network=true\n')
            router = TaskRouter.load(config)
            captured = []
            def fake(payload):
                captured.append(payload)
                return {"supported": True, "requires_review": True}
            with patch("rfp_agent.providers.JsonBridge._http", side_effect=fake):
                router.evaluate("verification", "q", [], "a")
            self.assertEqual("decision-test", captured[0]["model"])
            self.assertEqual("verification", captured[0]["operation"])
            config.write_text('[tasks.answer_generation]\nprovider="jev_bridge"\n')
            with self.assertRaisesRegex(ValueError, "cannot generate"):
                TaskRouter.load(config)

    def test_provider_failure_and_rejection_fail_conservatively(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            try:
                with store.db:
                    pid = store.stage(question="Encryption at rest?", answer="Stored data is encrypted.",
                        scope="a", provenance={}, submitter="sme")
                store.resolve([pid], "a", "reviewed")
                router = TaskRouter()
                with patch.object(router, "evaluate", side_effect=RuntimeError("secret-never-reported")):
                    result = draft(store, "Encryption at rest?", "a", router)
                    self.assertEqual("needs-review", result["status"])
                    self.assertNotIn("secret", result["reason"])
                with patch.object(router, "evaluate", return_value={"supported": False, "requires_review": True}):
                    result = draft(store, "Encryption at rest?", "a", router)
                    self.assertEqual("insufficient", result["status"])
                    self.assertEqual("", result["answer"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
