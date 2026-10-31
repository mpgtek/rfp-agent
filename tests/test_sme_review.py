from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
import io,json,tempfile,unittest
from openpyxl import Workbook,load_workbook
from rfp_agent.db import Store,digest
from rfp_agent.excel import literal
from rfp_agent.importing import import_source
from rfp_agent.workflow import answer_rfp,ingest_feedback
from rfp_agent.sme_review import HEADERS,apply_sme_review,export_sme_review,looks_like_sme_review
from rfp_agent.cli import main


class SimpleSMEReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'store')
        p=self.root/'kb.txt';p.write_text('Q: What are the recovery targets?\nA: Our RPO is 1 hour and our RTO is 24 hours.\n')
        import_source(self.store,p,'a');self.target=self.store.retrieve('What are the recovery targets?','a')[0]
        self.source=self.root/'rfp.xlsx';b=Workbook();b.active.append(['Question','Response']);b.active.append(['RPO/RTO, backup frequency, and disaster recovery testing',None]);b.save(self.source);b.close()
        self.selection={'sheet':'Sheet','response_cell':'B2','question':'RPO/RTO, backup frequency, and disaster recovery testing',
            'coverage':'partial','note':'Known recovery targets; two SME questions remain.',
            'parts':[{'entry_id':self.target['id'],'revision':self.target['revision'],'quote':self.target['answer']}],
            'requirements':[{'id':'targets','text':'RPO/RTO','state':'supported','part_indices':[0],'note':'Known targets.'},
                {'id':'backup','text':'Backup frequency','state':'missing','sme_question':'How often are backups performed?','note':'Not established.'},
                {'id':'dr','text':'DR testing','state':'missing','sme_question':'How is disaster recovery tested?','note':'Not established.'}],
            'response':self.target['answer'],'claims':[{'text':self.target['answer'],'part_indices':[0],'requirement_ids':['targets'],'supported':True,'support_note':'Exact targets.'}],
            'composition_review':{'supported':True,'complete':False,'coverage_checked':True,'relevant':True,'appropriate_detail':True}}
        self.run=self.generate(self.selection);self.review=Path(self.run['output'])/'sme-review.xlsx'

    def tearDown(self):self.store.close();self.tmp.cleanup()

    def generate(self,selection):
        p=self.root/'map.json';p.write_text(json.dumps({'format':'rfp-agent.evidence-map.v1','source_sha256':digest(self.source.read_bytes()),'scope':'a','mappings':[selection]}))
        return answer_rfp(self.store,self.source,'a',evidence_map=p)

    def returned(self,rows=None):
        b=load_workbook(self.review);ws=b['SME Review']
        for row,updates in (rows or {2:{'SME Response':'Backups are performed every 6 hours.','Review Status':'Approved','Reviewed By':'Security SME'}}).items():
            for key,value in updates.items():literal(ws.cell(row,HEADERS.index(key)+1),value)
        p=self.root/'returned.xlsx';b.save(p);b.close();return p

    def count(self):return self.store.db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]

    def test_three_plain_language_visible_tabs_and_protected_editable_fields(self):
        b=load_workbook(self.review)
        self.assertEqual(['SME Review','Instructions','Supporting Evidence'],[s.title for s in b if s.sheet_state=='visible'])
        ws=b['SME Review'];self.assertEqual(HEADERS,[c.value for c in ws[1]][:8])
        self.assertTrue(ws.protection.sheet);self.assertTrue(ws['A2'].protection.locked)
        self.assertTrue(all(not ws.cell(2,c).protection.locked for c in range(5,9)))
        self.assertTrue(ws.column_dimensions['I'].hidden);self.assertEqual('veryHidden',b['_Review data'].sheet_state)
        self.assertIn('Approved',ws.data_validations.dataValidation[0].formula1)
        self.assertEqual('Pending',ws['F2'].value)
        self.assertTrue(all(any(row[0].value==h for row in b['Instructions']) for h in HEADERS))
        self.assertFalse(any(c.data_type=='f' for s in b for row in s for c in row));b.close()

    def test_approved_new_answer_updates_kb_pending_stays_unresolved_and_reupload_is_idempotent(self):
        p=self.returned();result=apply_sme_review(self.store,p)
        self.assertEqual((1,1,1),(result['approved'],result['added'],result['pending']))
        self.assertEqual(2,self.count());e=self.store.retrieve('How often are backups performed?','a')[0]
        self.assertEqual('Backups are performed every 6 hours.',e['answer']);self.assertEqual('Security SME',e['approved_by'])
        self.assertTrue(json.loads(e['provenance'])['acceptance']['sme_approval'])
        self.assertEqual(1,apply_sme_review(self.store,p)['replayed']);self.assertEqual(2,self.count())

    def test_pending_answers_never_change_kb(self):
        p=self.returned({2:{'SME Response':'Unconfirmed response','Reviewed By':'SME'}})
        result=apply_sme_review(self.store,p);self.assertEqual(2,result['pending']);self.assertEqual(1,self.count())

    def test_approved_requires_answer_and_name(self):
        for updates in [{'Review Status':'Approved','Reviewed By':'SME'}, {'Review Status':'Approved','SME Response':'Every 6 hours.'}]:
            with self.assertRaises(ValueError):apply_sme_review(self.store,self.returned({2:updates}))
        self.assertEqual(1,self.count())

    def test_not_applicable_requires_explanation_and_does_not_become_kb_fact(self):
        with self.assertRaisesRegex(ValueError,'Comments'):
            apply_sme_review(self.store,self.returned({2:{'Review Status':'Not Applicable','Reviewed By':'SME'}}))
        p=self.returned({2:{'Review Status':'Not Applicable','Reviewed By':'SME','Comments':'This requirement is outside the contracted scope.'}})
        self.assertEqual(1,apply_sme_review(self.store,p)['not_applicable']);self.assertEqual(1,self.count())

    def test_invalid_later_row_rolls_back_entire_batch(self):
        p=self.returned({2:{'Review Status':'Approved','Reviewed By':'SME','SME Response':'Every 6 hours.'},3:{'Review Status':'Approved'}})
        with self.assertRaises(ValueError):apply_sme_review(self.store,p)
        self.assertEqual(1,self.count());self.assertEqual(1,self.store.db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0])

    def test_context_and_hidden_row_binding_tampering_rejected(self):
        for col in ('B','I'):
            p=self.returned();b=load_workbook(p);b['SME Review'][col+'2']='Changed';b.save(p);b.close()
            with self.assertRaises(ValueError):apply_sme_review(self.store,p)

    def test_duplicate_rows_and_formulas_rejected(self):
        p=self.returned();b=load_workbook(p);ws=b['SME Review'];ws.append([c.value for c in ws[2]]);b.save(p);b.close()
        with self.assertRaisesRegex(ValueError,'Duplicate'):apply_sme_review(self.store,p)
        p=self.returned();b=load_workbook(p);b['SME Review']['E2']='=1+1';b.save(p);b.close()
        with self.assertRaisesRegex(ValueError,'literal'):apply_sme_review(self.store,p)

    def test_changed_decision_after_application_is_rejected(self):
        apply_sme_review(self.store,self.returned())
        with self.assertRaisesRegex(ValueError,'already applied'):
            apply_sme_review(self.store,self.returned({2:{'Review Status':'Approved','Reviewed By':'Security SME','SME Response':'Every 3 hours.'}}))

    def test_stale_source_and_new_concurrent_answer_are_rejected(self):
        p=self.returned()
        with self.store.db:pid=self.store.stage(question='How often are backups performed?',answer='Every 12 hours.',scope='a',provenance={},submitter='source')
        self.store.resolve([pid],'approver','New policy')
        with self.assertRaisesRegex(ValueError,'changed'):apply_sme_review(self.store,p)
        with self.store.db:self.store.db.execute('UPDATE entries SET head=head+100 WHERE id=?',(self.target['id'],))
        with self.assertRaisesRegex(ValueError,'stale'):apply_sme_review(self.store,p)

    def test_existing_different_answer_goes_to_comparison_instead_of_overwrite(self):
        with self.store.db:pid=self.store.stage(question='How often are backups performed?',answer='Every 12 hours.',scope='a',provenance={},submitter='source')
        self.store.resolve([pid],'approver','Existing policy')
        self.review=self.root/'fresh.xlsx';drafts=json.loads((Path(self.run['output'])/'drafts.json').read_text());export_sme_review(self.store,self.review,drafts)
        result=apply_sme_review(self.store,self.returned())
        self.assertEqual(1,result['needs_comparison']);self.assertIsNotNone(result['comparison_review'])
        self.assertEqual('Every 12 hours.',self.store.retrieve('How often are backups performed?','a')[0]['answer'])
        replay=apply_sme_review(self.store,self.returned())
        self.assertEqual(1,replay['needs_comparison']);self.assertEqual(result['comparison_review'],replay['comparison_review'])

    def test_whole_row_reordering_preserves_hidden_binding(self):
        p=self.returned();b=load_workbook(p);ws=b['SME Review'];first=[c.value for c in ws[2]];second=[c.value for c in ws[3]]
        for r,values in [(2,second),(3,first)]:
            for c,value in enumerate(values,1):literal(ws.cell(r,c),value)
        b.save(p);b.close();self.assertEqual(1,apply_sme_review(self.store,p)['added'])

    def test_unrecognized_packet_is_rejected(self):
        p=self.returned();b=load_workbook(p);b['_Review data']['B2']='unknown-packet';b.save(p);b.close()
        with self.assertRaisesRegex(ValueError,'Unknown review'):apply_sme_review(self.store,p)

    def test_existing_identical_answer_is_unchanged(self):
        with self.store.db:pid=self.store.stage(question='How often are backups performed?',answer='Backups are performed every 6 hours.',scope='a',provenance={},submitter='source')
        self.store.resolve([pid],'approver','Existing policy')
        self.review=self.root/'fresh.xlsx';export_sme_review(self.store,self.review,json.loads((Path(self.run['output'])/'drafts.json').read_text()))
        before=self.store.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0]
        self.assertEqual(1,apply_sme_review(self.store,self.returned())['unchanged'])
        self.assertEqual(before,self.store.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0])

    def test_wrong_workspace_is_rejected(self):
        other=Store(self.root/'other')
        try:
            with self.assertRaisesRegex(ValueError,'original company workspace'):apply_sme_review(other,self.returned())
        finally:other.close()

    def test_ingest_and_feedback_recognize_new_review_without_an_extra_approval_command(self):
        p=self.returned();self.assertTrue(looks_like_sme_review(p))
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0,main(['--workspace',str(self.store.root),'ingest',str(p)]))
        self.assertEqual(1,json.loads(output.getvalue())['sme_review_applied']['added'])
        self.assertEqual(1,ingest_feedback(self.store,p)['replayed'])

    def test_explicit_sme_import_cannot_replace_an_existing_answer_or_approve_a_variant(self):
        with self.store.db:pid=self.store.stage(question='What are the recovery targets?',answer='Changed targets.',scope='a',provenance={},submitter='SME')
        with self.assertRaisesRegex(ValueError,'new canonical'):self.store.resolve([pid],'SME','Approved',approved_sme_import=True)

    def test_approved_gap_fact_is_available_for_rfp_rerun_while_unknown_testing_stays_a_gap(self):
        apply_sme_review(self.store,self.returned());e=self.store.retrieve('How often are backups performed?','a')[0]
        s=json.loads(json.dumps(self.selection));s['parts'].append({'entry_id':e['id'],'revision':e['revision'],'quote':e['answer']})
        s['requirements'][1]={'id':'backup','text':'Backup frequency','state':'supported','part_indices':[1],'note':'Approved SME fact.'}
        s['claims'].append({'text':e['answer'],'part_indices':[1],'requirement_ids':['backup'],'supported':True,'support_note':'Approved cadence.'})
        s['response']+=' '+e['answer'];run=self.generate(s);b=load_workbook(Path(run['output'])/'completed.xlsx')
        self.assertIn('every 6 hours',b.active['B2'].value);self.assertNotIn('tested',b.active['B2'].value);b.close()
        b=load_workbook(Path(run['output'])/'sme-review.xlsx');self.assertEqual(2,b['SME Review'].max_row);b.close()


if __name__=='__main__':unittest.main()
