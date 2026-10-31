import csv
import json
from pathlib import Path
import tempfile
import unittest

from rfp_agent.change_review import read_packet, apply_review
from rfp_agent.db import Store
from rfp_agent.importing import import_source


class SourceImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root / "data")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def source(self, rows, name="qa.csv"):
        path = self.root / name
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Question", "Answer"])
            writer.writerows(rows)
        return path

    def test_new_answers_are_immediately_retrievable_verbatim_without_review(self):
        result = import_source(self.store, self.source([["Supports webhooks?", "No."]]), "a")
        self.assertEqual((1,0,0), (result["imported"],result["unchanged"],result["collisions"]))
        self.assertIsNone(result["change_review"])
        evidence = self.store.retrieve("Supports webhooks?", "a")[0]
        self.assertEqual("No.", evidence["answer"])
        self.assertFalse(json.loads(evidence["provenance"])["acceptance"]["sme_approval"])
        self.assertEqual(0,self.store.db.execute("SELECT COUNT(*) FROM change_reviews").fetchone()[0])

    def test_same_source_and_same_answer_new_source_need_no_review_or_revision(self):
        path = self.source([["Encryption?", "AES-256"]])
        import_source(self.store,path,"a")
        repeat = import_source(self.store,path,"a")
        another = import_source(self.store,self.source([["ENCRYPTION?", "AES-256"]],"second.csv"),"a")
        self.assertEqual(1,repeat["unchanged"])
        self.assertEqual(1,another["unchanged"])
        self.assertIsNone(another["change_review"])
        self.assertEqual(1,self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])

    def test_mixed_document_imports_new_and_reviews_only_changed_existing_answer(self):
        import_source(self.store,self.source([["Encryption?", "AES-256"]]),"a")
        result = import_source(self.store,self.source([["Encryption?", "New encryption answer"],
                                                      ["SSO?", "SAML 2.0"]],"new.csv"),"a")
        self.assertEqual((1,1),(result["imported"],result["collisions"]))
        rows = read_packet(Path(result["change_review"]["path"]))
        self.assertEqual(1,len(rows))
        self.assertEqual("AES-256",rows[0]["current_answer"])
        self.assertEqual("New encryption answer",rows[0]["proposed_answer"])
        self.assertEqual("AES-256",self.store.retrieve("Encryption?","a")[0]["answer"])
        self.assertEqual("SAML 2.0",self.store.retrieve("SSO?","a")[0]["answer"])

    def test_current_variant_collision_targets_existing_canonical(self):
        import_source(self.store,self.source([["Encryption?", "AES-256"]]),"a")
        entry = self.store.retrieve("Encryption?","a")[0]
        with self.store.db:
            pid = self.store.stage(question="Stored data encryption?",answer="AES-256",scope="a",
                                   provenance={},submitter="source",kind="variant",target=entry["id"])
        self.store.resolve([pid],"sme","Equivalent question")
        result = import_source(self.store,self.source([["Stored data encryption?", "Changed"]],"variant.csv"),"a")
        rows = read_packet(Path(result["change_review"]["path"]))
        self.assertEqual("AES-256",rows[0]["current_answer"])
        self.assertEqual(1,self.store.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def test_scope_and_similar_question_do_not_create_false_collision(self):
        import_source(self.store,self.source([["Encryption?", "AES-256"]]),"a")
        other = import_source(self.store,self.source([["Encryption?", "Other product"]],"other.csv"),"b")
        similar = import_source(self.store,self.source([["How is data encrypted in transit?", "TLS 1.2"]],"similar.csv"),"a")
        self.assertIsNone(other["change_review"])
        self.assertIsNone(similar["change_review"])
        self.assertEqual(1,similar["imported"])

    def test_repeated_question_different_answers_reviews_later_collision(self):
        result = import_source(self.store,self.source([["SSO?", "SAML"],["SSO?", "No SSO"]]),"a")
        self.assertEqual((1,1),(result["imported"],result["collisions"]))
        rows = read_packet(Path(result["change_review"]["path"]))
        self.assertEqual("SAML",rows[0]["current_answer"])
        self.assertEqual("No SSO",rows[0]["proposed_answer"])

    def test_direct_import_cannot_bypass_existing_answer_approval(self):
        import_source(self.store,self.source([["Encryption?", "AES-256"]]),"a")
        with self.store.db:
            pid = self.store.stage(question="Encryption?",answer="Unreviewed overwrite",scope="a",provenance={},submitter="source")
        with self.assertRaisesRegex(ValueError,"only create new"):
            self.store.resolve([pid],"source","Bypass",direct_import=True)
        self.assertEqual("AES-256",self.store.retrieve("Encryption?","a")[0]["answer"])

    def test_invalid_directory_does_not_partially_import(self):
        directory = self.root / "sources"
        directory.mkdir()
        (directory / "valid.csv").write_text("Question,Answer\nSSO?,SAML\n")
        (directory / "invalid.csv").write_text("Wrong,Headers\nBad,Data\n")
        with self.assertRaises(ValueError):
            import_source(self.store,directory,"a")
        self.assertEqual(0,self.store.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def test_withdrawn_review_cannot_be_applied(self):
        import_source(self.store,self.source([["Encryption?", "AES-256"]]),"a")
        result = import_source(self.store,self.source([["Encryption?", "Changed"]],"changed.csv"),"a")
        with self.store.db:
            self.store.audit("operator","change_review_withdrawn",{"review_id":result["change_review"]["review_id"]})
        with self.assertRaisesRegex(ValueError,"Withdrawn review"):
            apply_review(self.store,result["change_review"]["path"])


if __name__ == "__main__":
    unittest.main()
