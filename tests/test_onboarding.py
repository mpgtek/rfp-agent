import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from openpyxl import Workbook

from rfp_agent.cli import main
from rfp_agent.db import Store
from rfp_agent.onboarding import active_workspace, configure, status, state_directory


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / "state"
        self.workspace = self.root / "company"
        self.env = patch.dict(os.environ, {"RFP_AGENT_STATE_DIR": str(self.state)})
        self.env.start()
        self.default_patch = patch("rfp_agent.onboarding.default_workspace", return_value=self.root / "known-store")
        self.default_patch.start()

    def tearDown(self):
        self.default_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def command(self, args):
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as error:
            code = main(args)
        return code, json.loads(output.getvalue()) if output.getvalue() else error.getvalue()

    def test_first_run_prompts_for_workspace_without_creating_a_kb(self):
        self.assertEqual("choose_company_workspace", status()["next_step"])
        self.assertFalse(self.state.exists())
        self.assertFalse(self.workspace.exists())

    def test_setup_saves_company_scope_and_resumes_source_prompt(self):
        result = configure(self.workspace, "ExampleCompany")
        self.assertEqual("provide_sources", result["next_step"])
        self.assertEqual("examplecompany", result["scope"])
        self.assertEqual(str(self.workspace), active_workspace())
        self.assertEqual("ExampleCompany", status()["company"])
        self.assertTrue((self.workspace / "inputs").is_dir())
        self.assertEqual(0, result["counts"]["approved_answers"])

    def test_source_selection_does_not_ingest_or_approve(self):
        configure(self.workspace, "ExampleCompany")
        source = self.root / "qa.csv"
        source.write_text("Question,Answer\nDo you support SAML?,Yes SAML 2.0\n")
        result = configure(self.workspace, sources=[source])
        self.assertEqual("prepare_and_ingest", result["next_step"])
        self.assertEqual([str(source)], result["source_paths"])
        self.assertEqual(0, result["counts"]["pending_proposals"])
        self.assertFalse(result["can_answer_rfp"])

    def test_no_sources_routes_to_company_profile(self):
        configure(self.workspace, "ExampleCompany", defer_sources=True)
        self.assertEqual("describe_application", status()["next_step"])

    def test_saved_defaults_advance_through_ingestion_approval_rfp_and_feedback(self):
        configure(self.workspace, "ExampleCompany")
        source = self.root / "qa.csv"
        source.write_text("Question,Answer\nDo you support SAML?,We support SAML 2.0\n")
        configure(self.workspace, sources=[source])
        code, result = self.command(["ingest", str(source)])
        self.assertEqual(0, code)
        self.assertEqual(1, result["imported"])
        self.assertIsNone(result["change_review"])
        self.assertEqual("provide_rfp", status()["next_step"])
        book = Workbook()
        book.active.append(["Question", "Response"])
        book.active.append(["Do you support SAML?", None])
        rfp = self.root / "rfp.xlsx"
        book.save(rfp)
        book.close()
        code, run = self.command(["answer", str(rfp)])
        self.assertEqual(0, code)
        self.assertEqual("review_rfp", status()["next_step"])
        store = Store(self.workspace)
        try:
            with store.db:
                store.stage(question="Do you support SAML?", answer="We support SAML 2.0 for Control Center",
                    scope="examplecompany", provenance={"run_id": run["id"]}, submitter="sme")
        finally:
            store.close()
        self.assertEqual("review_feedback", status()["next_step"])

    def test_company_isolation_missing_source_and_managed_paths(self):
        configure(self.workspace, "ExampleCompany")
        with self.assertRaisesRegex(ValueError, "another company"):
            configure(self.workspace, "AnotherCompany")
        with self.assertRaisesRegex(ValueError, "does not exist"):
            configure(self.workspace, sources=[self.root / "missing.txt"])
        with self.assertRaisesRegex(ValueError, "managed workspace"):
            configure(self.workspace, sources=[self.workspace])
        source = self.workspace / "inputs" / "source.md"
        source.write_text("Company source")
        self.assertEqual("prepare_and_ingest", configure(self.workspace, sources=[source])["next_step"])

    def test_missing_saved_database_is_not_silently_recreated(self):
        configure(self.workspace, "ExampleCompany")
        db = self.workspace / "knowledge.sqlite3"
        db.unlink()
        code, error = self.command(["proposals"])
        self.assertEqual(2, code)
        self.assertIn("missing", error)
        self.assertFalse(db.exists())

    def test_demo_never_populates_saved_company_workspace(self):
        configure(self.workspace, "ExampleCompany")
        code, error = self.command(["demo"])
        self.assertEqual(2, code)
        self.assertIn("explicit fresh", error)
        self.assertEqual(0, status()["counts"]["pending_proposals"])

    def test_saved_state_resumes_in_another_process(self):
        configure(self.workspace, "ExampleCompany")
        p = subprocess.run([sys.executable, "-m", "rfp_agent", "onboarding-status"],
                           capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertEqual("ExampleCompany", json.loads(p.stdout)["company"])

    def test_discovery_in_fresh_process_needs_no_optional_libraries(self):
        configure(self.workspace,"ExampleCompany")
        script=Path(__file__).resolve().parents[1]/"scripts/discover_workspace.py"
        p=subprocess.run([sys.executable,"-S",str(script)],capture_output=True,text=True)
        self.assertEqual(0,p.returncode,p.stderr)
        result=json.loads(p.stdout)
        self.assertEqual(str(self.workspace),result["onboarding"]["workspace"])
        self.assertTrue(result["onboarding"]["configured"])

    def test_discovery_missing_kb_is_access_problem_not_first_run(self):
        configure(self.workspace,"ExampleCompany")
        database=self.workspace/"knowledge.sqlite3"
        database.unlink()
        script=Path(__file__).resolve().parents[1]/"scripts/discover_workspace.py"
        p=subprocess.run([sys.executable,"-S",str(script)],capture_output=True,text=True)
        self.assertEqual(2,p.returncode)
        result=json.loads(p.stderr)
        self.assertEqual("restore_workspace_access",result["next_step"])
        self.assertFalse(result["create_new_workspace"])
        self.assertFalse(database.exists())

    def test_known_store_resumes_without_registry_or_optional_libraries(self):
        from rfp_agent.onboarding import default_workspace
        known = default_workspace()
        configure(known,"ExampleCompany")
        (self.state/"settings.json").unlink()
        self.assertEqual(str(known),active_workspace())
        self.assertTrue(status()["configured"])
        self.assertEqual("ExampleCompany",status()["company"])

    def test_unselected_state_uses_known_location_instead_of_stale_registry(self):
        configure(self.workspace,"Old test")
        with patch.dict(os.environ,{"RFP_AGENT_STATE_DIR":""}):
            self.assertEqual(str(self.root/"known-store"),active_workspace())


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("rfp_bootstrap", Path(__file__).resolve().parents[1] / "scripts/bootstrap.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / "state"
        runtime = self.state / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        runtime.parent.mkdir(parents=True)
        runtime.touch()

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_dependencies_are_installed_and_readiness_is_verified(self):
        before = {"fts5": True, "missing": ["openpyxl", "python-docx"]}
        after = {"fts5": True, "missing": [], "dependencies": {"openpyxl": "3.1.5", "python-docx": "1.2.0"}}
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, json.dumps({"next_step": "choose_company_workspace"}), "")
        with patch.object(self.module, "probe", side_effect=[before, before, after]), patch.object(self.module.subprocess, "run", side_effect=run):
            result = self.module.bootstrap(self.state)
        self.assertTrue(result["ready"])
        self.assertEqual(["openpyxl>=3.1,<4", "python-docx>=1.1,<2"], result["installed_this_run"])
        self.assertIn("pip", calls[0])
        self.assertTrue((self.state / "runtime.json").exists())
        self.assertIn("RFP_AGENT_STATE_DIR", (self.state / "run.py").read_text())

    def test_offline_missing_dependency_and_fts_failure_do_not_claim_success(self):
        for result, message in [({"fts5": True, "missing": ["openpyxl"]}, "Offline setup"),
                                ({"fts5": False, "missing": []}, "FTS5")]:
            with patch.object(self.module, "probe", return_value=result), self.assertRaisesRegex(RuntimeError, message):
                self.module.bootstrap(self.state, offline=True)
            self.assertFalse((self.state / "runtime.json").exists())

    def test_failed_install_never_writes_ready_marker(self):
        with patch.object(self.module, "probe", return_value={"fts5": True, "missing": ["openpyxl"]}), \
             patch.object(self.module.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "failed")), \
             self.assertRaisesRegex(RuntimeError, "installation failed"):
            self.module.bootstrap(self.state)
        self.assertFalse((self.state / "runtime.json").exists())

    def test_compatible_current_python_recovers_broken_venv_without_download(self):
        broken={"fts5":True,"missing":["openpyxl","python-docx"]}
        healthy={"fts5":True,"missing":[]}
        response=subprocess.CompletedProcess([],0,json.dumps({"configured":True,"company":"ExampleCompany"}),"")
        with patch.object(self.module,"probe",side_effect=[broken,healthy,healthy]), \
             patch.object(self.module.subprocess,"run",return_value=response) as run:
            result=self.module.bootstrap(self.state,offline=True)
        self.assertEqual("compatible-host",result["runtime_mode"])
        self.assertEqual([],result["installed_this_run"])
        self.assertTrue(result["onboarding"]["configured"])
        self.assertFalse(any("pip" in call.args[0] for call in run.call_args_list))

    def test_saved_documents_fallback_is_recovered_consistently(self):
        home=Path(self.temp.name)/"home"
        fallback=home/"Documents/Codex/rfp-agent-runtime"
        fallback.mkdir(parents=True)
        (fallback/"settings.json").write_text('{}')
        with patch.dict(os.environ,{"RFP_AGENT_STATE_DIR":""}),patch.object(Path,"home",return_value=home),patch.object(sys,"platform","darwin"):
            self.assertEqual(fallback,state_directory())
            self.assertEqual(fallback,self.module.state_directory())

    def test_explicit_state_selection_takes_priority_over_saved_fallback(self):
        with patch.dict(os.environ,{"RFP_AGENT_STATE_DIR":str(self.state)}):
            self.assertEqual(self.state.resolve(),state_directory())
            self.assertEqual(self.state.resolve(),self.module.state_directory())


if __name__ == "__main__":
    unittest.main()
