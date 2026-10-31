from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from openpyxl import Workbook

from rfp_agent.db import Store,digest
from rfp_agent.importing import import_source
from rfp_agent.questionnaire import extract
from rfp_agent.workflow import answer_rfp
from rfp_agent.cli import main


class WordAnswerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.store=Store(self.root/"store")
        source=self.root/"kb.txt"
        source.write_text("Q: Is SAML supported?\nA: We support SAML 2.0.\nQ: Are webhooks supported?\nA: We do not support webhooks.\n")
        import_source(self.store,source,"a")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def doc(self,questions=None):
        d=Document()
        d.add_heading("Customer questionnaire",0)
        d.sections[0].header.paragraphs[0].text="Customer header"
        table=d.add_table(rows=1,cols=3)
        table.style="Table Grid"
        for cell,text in zip(table.rows[0].cells,["Requirement","Vendor Response","Code"]):
            cell.text=text
        for question in questions or ["Is SAML supported?","Is SAML and OIDC supported?","Is quantum payroll available?"]:
            table.add_row().cells[0].text=question
        pricing=d.add_table(rows=1,cols=2)
        pricing.cell(0,0).text="Price"
        pricing.cell(0,1).text="Unchanged pricing placeholder"
        path=self.root/"input.docx"
        d.save(path)
        return path

    def mapping(self,path,parts,coverage="complete",index=1,question=None):
        row=extract(path)[1][index]
        data={"format":"rfp-agent.evidence-map.v1","source_sha256":digest(path.read_bytes()),"scope":"a",
              "mappings":[dict(sheet=row["sheet"],response_cell=row["response_cell"],question=question or row["question"],
                               coverage=coverage,note="Every requested capability was checked against the selected source.",parts=parts)]}
        target=self.root/"mapping.json"
        target.write_text(json.dumps(data))
        return target

    def part(self,q="Is SAML supported?",quote="We support SAML 2.0."):
        evidence=self.store.retrieve(q,"a")[0]
        return {"entry_id":evidence["id"],"revision":evidence["revision"],"quote":quote}

    def test_known_only_word_fill_skips_compound_unknowns_and_preserves_package(self):
        path=self.doc()
        before=path.read_bytes()
        run=answer_rfp(self.store,path,"a")
        completed=Path(run["output"])/"completed.docx"
        d=Document(completed)
        self.assertEqual("We support SAML 2.0.",d.tables[0].cell(1,1).text)
        self.assertEqual("",d.tables[0].cell(2,1).text)
        self.assertEqual("",d.tables[0].cell(3,1).text)
        self.assertEqual("",d.tables[0].cell(1,2).text)
        self.assertEqual(before,path.read_bytes())
        self.assertEqual(0,run["external_calls"])
        self.assertEqual(1,run["write_counts"]["written"])
        with ZipFile(path) as original,ZipFile(completed) as result:
            self.assertEqual(original.namelist(),result.namelist())
            for name in original.namelist():
                if name!="word/document.xml":
                    self.assertEqual(original.read(name),result.read(name),name)
            before_xml=etree.fromstring(original.read("word/document.xml"))
            after_xml=etree.fromstring(result.read("word/document.xml"))
            ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            original_cell=before_xml.xpath("./w:body/w:tbl[1]/w:tr[2]/w:tc[2]",namespaces=ns)[0]
            edited_cell=after_xml.xpath("./w:body/w:tbl[1]/w:tr[2]/w:tc[2]",namespaces=ns)[0]
            edited_cell.getparent().replace(edited_cell,deepcopy(original_cell))
            self.assertEqual(etree.tostring(before_xml,method="c14n"),etree.tostring(after_xml,method="c14n"))
        self.assertEqual("Unchanged pricing placeholder",d.tables[1].cell(0,1).text)

    def test_negative_known_answer_is_written_without_invented_yes_or_code(self):
        run=answer_rfp(self.store,self.doc(["Are webhooks supported?"]),"a")
        row=Document(Path(run["output"])/"completed.docx").tables[0].rows[1]
        self.assertEqual("We do not support webhooks.",row.cells[1].text)
        self.assertEqual("",row.cells[2].text)

    def test_verified_paraphrase_reuses_verbatim_evidence_without_learning_variant(self):
        path=self.doc(["Unrelated?","Describe enterprise SAML login."])
        selection=self.mapping(path,[self.part()])
        before=self.store.db.execute("SELECT COUNT(*) FROM variants").fetchone()[0]
        run=answer_rfp(self.store,path,"a",evidence_map=selection)
        self.assertEqual("We support SAML 2.0.",Document(Path(run["output"])/"completed.docx").tables[0].cell(2,1).text)
        self.assertEqual(before,self.store.db.execute("SELECT COUNT(*) FROM variants").fetchone()[0])
        self.assertEqual("needs-review",json.loads((Path(run["output"])/"drafts.json").read_text())[1]["status"])

    def test_partial_evidence_selection_leaves_response_blank(self):
        path=self.doc()
        run=answer_rfp(self.store,path,"a",evidence_map=self.mapping(path,[self.part()],coverage="partial"))
        self.assertEqual("",Document(Path(run["output"])/"completed.docx").tables[0].cell(2,1).text)

    def test_fabricated_or_negation_stripped_selected_text_is_rejected(self):
        path=self.doc(["Unknown?","Describe event notifications."])
        for part in [self.part(quote="We support SAML and OIDC."),
                     self.part("Are webhooks supported?","support webhooks.")]:
            with self.assertRaisesRegex(ValueError,"verbatim"):
                answer_rfp(self.store,path,"a",evidence_map=self.mapping(path,[part]))

    def test_wrong_question_checksum_scope_and_unknown_cells_are_rejected(self):
        path=self.doc()
        for key,value in [("source_sha256","wrong"),("scope","other")]:
            selection=self.mapping(path,[self.part()])
            data=json.loads(selection.read_text()); data[key]=value; selection.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                answer_rfp(self.store,path,"a",evidence_map=selection)
        for key,value in [("question","Changed question"),("response_cell","T99:R1:C1")]:
            selection=self.mapping(path,[self.part()])
            data=json.loads(selection.read_text()); data["mappings"][0][key]=value; selection.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                answer_rfp(self.store,path,"a",evidence_map=selection)

    def test_stale_revision_and_cross_scope_evidence_are_rejected(self):
        path=self.doc()
        part=self.part(); part["revision"]+=100
        with self.assertRaisesRegex(ValueError,"stale"):
            answer_rfp(self.store,path,"a",evidence_map=self.mapping(path,[part]))
        with self.store.db:
            pid=self.store.stage(question="Other product",answer="Different data",scope="other",provenance={},submitter="source")
        item=self.store.resolve([pid],"sme","Reviewed")[0]
        with self.assertRaisesRegex(ValueError,"scope"):
            answer_rfp(self.store,path,"a",evidence_map=self.mapping(path,[{"entry_id":item["entry"],"revision":item["revision"],"quote":"Different data"}]))

    def test_bare_yes_is_not_repurposed_for_a_different_question(self):
        with self.store.db:
            pid=self.store.stage(question="A specific requirement?",answer="Yes.",scope="a",provenance={},submitter="source")
        self.store.resolve([pid],"sme","Specific source question")
        path=self.doc()
        part=self.part("A specific requirement?","Yes.")
        with self.assertRaisesRegex(ValueError,"Bare yes/no"):
            answer_rfp(self.store,path,"a",evidence_map=self.mapping(path,[part]))

    def test_existing_merged_and_protected_responses_are_preserved(self):
        path=self.doc(["Is SAML supported?"]*3)
        d=Document(path)
        d.tables[0].cell(1,1).text="Customer's existing answer"
        d.tables[0].cell(2,1).merge(d.tables[0].cell(2,2))
        d.save(path)
        run=answer_rfp(self.store,path,"a")
        output=Document(Path(run["output"])/"completed.docx")
        self.assertEqual("Customer's existing answer",output.tables[0].cell(1,1).text)
        self.assertEqual("",output.tables[0].cell(2,1).text)
        protection=OxmlElement("w:documentProtection");protection.set(qn("w:enforcement"),"1")
        d.settings.element.append(protection);d.save(path)
        run=answer_rfp(self.store,path,"a")
        self.assertNotIn("written",run["write_counts"])

    def test_unknown_only_docx_package_is_unchanged(self):
        path=self.doc(["A previously unknown product feature?"])
        run=answer_rfp(self.store,path,"a")
        with ZipFile(path) as a,ZipFile(Path(run["output"])/"completed.docx") as b:
            self.assertTrue(all(a.read(name)==b.read(name) for name in a.namelist()))

    def test_signed_word_is_rejected_instead_of_invalidating_signature(self):
        path=self.doc()
        with ZipFile(path,"a") as archive:
            archive.writestr("_xmlsignatures/sig1.xml","<signature/>")
        with self.assertRaisesRegex(ValueError,"Signed Word"):
            answer_rfp(self.store,path,"a")

    def test_stale_and_conflicting_known_answers_are_skipped(self):
        path=self.doc(["Is SAML supported?"])
        with self.store.db:
            self.store.stage(question="Is SAML supported?",answer="Pending changed capability",scope="a",provenance={},submitter="source")
        run=answer_rfp(self.store,path,"a")
        self.assertEqual("",Document(Path(run["output"])/"completed.docx").tables[0].cell(1,1).text)
        with self.store.db:
            self.store.db.execute("UPDATE proposals SET status='rejected' WHERE status='pending'")
            self.store.db.execute("UPDATE revisions SET approved_at='2000-01-01T00:00:00+00:00'")
        run=answer_rfp(self.store,path,"a")
        self.assertEqual("",Document(Path(run["output"])/"completed.docx").tables[0].cell(1,1).text)

    def test_explicit_word_column_mapping_and_paragraph_only_limitation(self):
        path=self.doc(["Is SAML supported?"])
        d=Document(path);d.tables[0].cell(0,0).text="Prompt";d.tables[0].cell(0,1).text="Reply";d.save(path)
        with self.assertRaisesRegex(ValueError,"No Word"):
            answer_rfp(self.store,path,"a")
        run=answer_rfp(self.store,path,"a",sheet="Table 1",header_row=1,question_column="A",response_column="B")
        self.assertEqual("We support SAML 2.0.",Document(Path(run["output"])/"completed.docx").tables[0].cell(1,1).text)
        d=Document();d.add_paragraph("What is your price?");d.save(path)
        with self.assertRaisesRegex(ValueError,"paragraph-only"):
            answer_rfp(self.store,path,"a")

    def test_xlsx_default_also_skips_unsupported_related_answers(self):
        path=self.root/"rfp.xlsx"
        book=Workbook();book.active.append(["Question","Response"])
        book.active.append(["Is SAML and OIDC supported?",None]);book.save(path);book.close()
        run=answer_rfp(self.store,path,"a")
        from openpyxl import load_workbook
        result=load_workbook(Path(run["output"])/"completed.xlsx")
        self.assertIsNone(result.active["B2"].value);result.close()

    def test_cli_detect_and_answer_word_with_evidence_selection(self):
        path=self.doc(["Is SAML supported?","Describe enterprise SAML login."])
        mapping=self.mapping(path,[self.part()])
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0,main(["detect",str(path)]))
        self.assertEqual(2,json.loads(output.getvalue())["question_count"])
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0,main(["--workspace",str(self.store.root),"answer",str(path),"--scope","a","--evidence-map",str(mapping)]))
        result=json.loads(output.getvalue())
        self.assertTrue((Path(result["output"])/"completed.docx").is_file())
        self.assertEqual(2,result["write_counts"]["written"])

    def test_composed_response_is_written_with_claim_evidence_and_without_kb_mutation(self):
        path=self.doc(["Unrelated?","Describe SAML support."])
        mapping=self.mapping(path,[self.part()])
        data=json.loads(mapping.read_text())
        selected=data["mappings"][0]
        selected.update(response="Our platform supports SAML 2.0.",
                        claims=[{"text":"Our platform supports SAML 2.0.","part_indices":[0],
                                 "supported":True,"support_note":"Same protocol support, rewritten in company voice."}],
                        composition_review={k:True for k in ("supported","complete","relevant","appropriate_detail")})
        mapping.write_text(json.dumps(data))
        run=answer_rfp(self.store,path,"a",evidence_map=mapping)
        self.assertEqual("Our platform supports SAML 2.0.",Document(Path(run["output"])/"completed.docx").tables[0].cell(2,1).text)
        drafts=json.loads((Path(run["output"])/"drafts.json").read_text())
        self.assertTrue(drafts[1]["composition"]["claims"])
        from openpyxl import load_workbook
        review=load_workbook(Path(run["output"])/"sme-review.xlsx")
        self.assertEqual(3,review["Supporting Evidence"].max_row)
        self.assertEqual("Our platform supports SAML 2.0.",review["Supporting Evidence"]["C3"].value)
        review.close()
        self.assertEqual("We support SAML 2.0.",self.store.retrieve("Is SAML supported?","a")[0]["answer"])

    def test_composed_response_without_claim_review_cannot_bypass_grounding(self):
        path=self.doc()
        mapping=self.mapping(path,[self.part()])
        data=json.loads(mapping.read_text())
        data["mappings"][0]["response"]="Our platform supports SAML 2.0."
        mapping.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"claim"):
            answer_rfp(self.store,path,"a",evidence_map=mapping)


if __name__=="__main__":
    unittest.main()
