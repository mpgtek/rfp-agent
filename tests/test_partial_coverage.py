from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from docx import Document
from openpyxl import Workbook,load_workbook
from rfp_agent.db import Store,digest
from rfp_agent.importing import import_source
from rfp_agent.questionnaire import extract
from rfp_agent.workflow import answer_rfp,ingest_feedback
from rfp_agent.retrieval import prepare
from rfp_agent.excel import literal
from rfp_agent.gap_review import GAP_HEADERS


class PartialCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'store')
        p=self.root/'kb.txt'
        p.write_text('Q: What are our recovery targets?\nA: We provide RPO of 1hour and RTO of 24 hours.\nQ: What is our availability?\nA: Our uptime SLA is 99.7%.\n')
        import_source(self.store,p,'a')
        e=self.store.retrieve('What are our recovery targets?','a')[0]
        self.part={'entry_id':e['id'],'revision':e['revision'],'quote':e['answer']}

    def tearDown(self):
        self.store.close();self.tmp.cleanup()

    def source(self,extension='docx',question='RPO/RTO, backup frequency, and disaster recovery testing'):
        p=self.root/('rfp.'+extension)
        if extension=='docx':
            d=Document();t=d.add_table(rows=2,cols=2)
            t.cell(0,0).text='Requirement';t.cell(0,1).text='Vendor Response';t.cell(1,0).text=question;d.save(p)
        else:
            b=Workbook();b.active.append(['Question','Response']);b.active.append([question,None]);b.save(p);b.close()
        return p

    def selected(self,path):
        row=extract(path)[1][0]
        requirements=[{'id':'targets','text':'RPO and RTO','state':'supported','part_indices':[0],'note':'Both targets are explicitly stated.'},
            {'id':'backup','text':'Backup frequency','state':'missing','sme_question':'How often are backups performed?','note':'No backup schedule in the KB.'},
            {'id':'dr-test','text':'Disaster recovery testing','state':'missing','sme_question':'How is disaster recovery tested and how often?','note':'Recovery targets do not establish testing.'}]
        response='Our RPO is 1 hour and our RTO is 24 hours.'
        return {'sheet':row['sheet'],'response_cell':row['response_cell'],'question':row['question'],
            'coverage':'partial','note':'Known recovery targets; backup frequency and DR testing require SME input.',
            'requirements':requirements,'parts':[self.part],'response':response,
            'claims':[{'text':response,'part_indices':[0],'requirement_ids':['targets'],'supported':True,'support_note':'Same source targets, spacing normalized.'}],
            'composition_review':{'supported':True,'complete':False,'coverage_checked':True,'relevant':True,'appropriate_detail':True}}

    def run_map(self,path,selected):
        p=self.root/'map.json'
        p.write_text(json.dumps({'format':'rfp-agent.evidence-map.v1','source_sha256':digest(path.read_bytes()),'scope':'a','mappings':[selected]}))
        return answer_rfp(self.store,path,'a',evidence_map=p)

    def test_partial_targets_written_to_word_and_excel_with_specific_sme_gaps(self):
        for extension in ('docx','xlsx'):
            path=self.source(extension);before=path.read_bytes()
            run=self.run_map(path,self.selected(path));output=Path(run['output'])
            drafts=json.loads((output/'drafts.json').read_text())
            self.assertEqual('partial',drafts[0]['status']);self.assertEqual(2,len(drafts[0]['sme_gaps']))
            if extension=='docx':value=Document(output/'completed.docx').tables[0].cell(1,1).text
            else:
                b=load_workbook(output/'completed.xlsx');value=b.active['B2'].value;b.close()
            self.assertEqual('Our RPO is 1 hour and our RTO is 24 hours.',value)
            self.assertNotIn('backup',value.lower());self.assertNotIn('testing',value.lower())
            self.assertEqual(before,path.read_bytes());self.assertEqual(0,run['external_calls'])
            b=load_workbook(output/'sme-review.xlsx')
            self.assertEqual(3,b['SME Review'].max_row);self.assertEqual(2,b['Supporting Evidence'].max_row);b.close()

    def test_wholly_unknown_response_stays_blank_and_routes_to_sme(self):
        path=self.source(question='Do you provide quantum payroll?')
        s=self.selected(path);s.update(coverage='none',parts=[],response='',claims=[],requirements=[{
            'id':'unknown','text':'Quantum payroll','state':'missing','note':'No evidence.', 'sme_question':'Do you provide quantum payroll?'}])
        run=self.run_map(path,s);out=Path(run['output'])
        self.assertEqual('',Document(out/'completed.docx').tables[0].cell(1,1).text)
        self.assertEqual({'insufficient':1},run['counts']);self.assertEqual(1,run['missing_items'])

    def test_none_coverage_cannot_smuggle_an_answer(self):
        p=self.source();s=self.selected(p);s.update(coverage='none',parts=[],requirements=[s['requirements'][1]])
        with self.assertRaisesRegex(ValueError,'No-evidence'):self.run_map(p,s)

    def test_known_dr_testing_is_included_while_only_backup_frequency_goes_to_sme(self):
        source=self.root/'dr.txt'
        source.write_text('Q: How is disaster recovery tested?\nA: Disaster recovery testing is performed annually.\n')
        import_source(self.store,source,'a')
        p=self.source();s=self.selected(p)
        e=self.store.retrieve('How is disaster recovery tested?','a')[0]
        s['parts'].append({'entry_id':e['id'],'revision':e['revision'],'quote':e['answer']})
        s['requirements'][2]={'id':'dr-test','text':'Disaster recovery testing','state':'supported','part_indices':[1],'note':'Annual testing explicitly confirmed.'}
        s['claims'].append({'text':e['answer'],'part_indices':[1],'requirement_ids':['dr-test'],'supported':True,'support_note':'Exact test cadence.'})
        s['response']+=' '+e['answer']
        run=self.run_map(p,s);draft=json.loads((Path(run['output'])/'drafts.json').read_text())[0]
        self.assertIn('testing is performed annually',draft['answer'])
        self.assertEqual(['Backup frequency'],[g['missing_item'] for g in draft['sme_gaps']])

    def test_cli_prepare_returns_scoped_evidence(self):
        from contextlib import redirect_stdout
        from rfp_agent.cli import main
        import io
        p=self.source()
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0,main(['--workspace',str(self.store.root),'prepare',str(p),'--scope','a']))
        self.assertEqual(2,json.loads(out.getvalue())['scoped_entry_count'])

    def test_partial_cannot_claim_complete_or_omit_gap_review(self):
        p=self.source()
        for key,value in [('complete',True),('coverage_checked',False)]:
            s=self.selected(p);s['composition_review'][key]=value
            with self.assertRaisesRegex(ValueError,'incomplete'):self.run_map(p,s)

    def test_partial_requires_citations_and_does_not_allow_claims_for_missing_items(self):
        p=self.source()
        for change in ('missing-claim','wrong-part','unsupported-item','uncited-supported-item'):
            s=self.selected(p)
            if change=='missing-claim':s.pop('response')
            elif change=='wrong-part':s['requirements'][0]['part_indices']=[99]
            elif change=='unsupported-item':s['claims'][0]['requirement_ids']=['backup']
            else:s['requirements'].append(dict(s['requirements'][0],id='another'))
            with self.assertRaises(ValueError):self.run_map(p,s)

    def test_partial_rejects_fabricated_backup_frequency(self):
        p=self.source();s=self.selected(p)
        s['response']=s['claims'][0]['text']='We perform daily backups.'
        with self.assertRaisesRegex(ValueError,'unsupported'):self.run_map(p,s)

    def test_coverage_labels_must_agree_and_supported_items_need_evidence(self):
        p=self.source()
        for change in ('complete','no-evidence','duplicate'):
            s=self.selected(p)
            if change=='complete':s['coverage']='complete'
            elif change=='no-evidence':s['requirements'][0]['part_indices']=[]
            else:s['requirements'][1]['id']='targets'
            with self.assertRaises(ValueError):self.run_map(p,s)

    def test_uptime_below_requested_threshold_is_written_without_claiming_compliance(self):
        p=self.source(question='Uptime SLA of 99.9% and service credits')
        s=self.selected(p);e=self.store.retrieve('What is our availability?','a')[0]
        s['parts']=[{'entry_id':e['id'],'revision':e['revision'],'quote':e['answer']}]
        s['requirements']=[{'id':'uptime','text':'99.9% uptime target','state':'supported','part_indices':[0],
            'meets_requirement':False,'note':'99.7% is below the requested 99.9%.'},
            {'id':'credits','text':'Service credits','state':'missing','sme_question':'What service credits apply?','note':'No credit terms in KB.'}]
        s['response']=s['claims'][0]['text']='Our uptime SLA is 99.7%.';s['claims'][0]['requirement_ids']=['uptime']
        run=self.run_map(p,s)
        self.assertEqual(s['response'],Document(Path(run['output'])/'completed.docx').tables[0].cell(1,1).text)
        b=load_workbook(Path(run['output'])/'sme-review.xlsx');self.assertIn('Known shortfall',b['Supporting Evidence']['D2'].value);b.close()

    def returned_gap(self,run,**updates):
        from rfp_agent.excel import review_book
        review_book(Path(run['output'])/'sme-review.xlsx',json.loads((Path(run['output'])/'drafts.json').read_text()))
        path=self.root/'returned.xlsx';b=load_workbook(Path(run['output'])/'sme-review.xlsx');ws=b['SME gaps']
        data=dict(action='propose',sme_answer='Backups are performed every 6 hours.',reviewer='sme',review_note='Confirmed policy',**updates)
        for key,value in data.items():literal(ws.cell(2,GAP_HEADERS.index(key)+1),value)
        b.save(path);b.close();return path

    def test_sme_gap_roundtrip_stages_only_specific_missing_answer_and_requires_approval(self):
        p=self.source();run=self.run_map(p,self.selected(p));path=self.returned_gap(run)
        count=self.store.db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
        proposals=ingest_feedback(self.store,path)
        self.assertEqual(proposals,ingest_feedback(self.store,path));self.assertEqual(1,len(proposals))
        proposal=self.store.db.execute('SELECT * FROM proposals WHERE id=?',(proposals[0],)).fetchone()
        self.assertEqual('How often are backups performed?',proposal['question']);self.assertEqual('pending',proposal['status'])
        self.assertEqual(count,self.store.db.execute('SELECT COUNT(*) FROM entries').fetchone()[0])
        with self.assertRaisesRegex(ValueError,'own proposal'):self.store.resolve(proposals,'sme','Reviewed')
        self.store.resolve(proposals,'approver','Confirmed SME policy')
        self.assertTrue(self.store.retrieve('How often are backups performed?','a')[0]['exact'])

    def test_sme_gap_context_tampering_is_rejected(self):
        p=self.source();run=self.run_map(p,self.selected(p));path=self.returned_gap(run,missing_item='A different question')
        with self.assertRaisesRegex(ValueError,'context'):ingest_feedback(self.store,path)

    def test_sme_gap_formulas_are_rejected(self):
        p=self.source();run=self.run_map(p,self.selected(p));path=self.returned_gap(run)
        b=load_workbook(path);b['SME gaps']['I2']='=1+1';b.save(path);b.close()
        with self.assertRaisesRegex(ValueError,'literal'):ingest_feedback(self.store,path)

    def test_stale_gap_review_is_rejected(self):
        p=self.source();run=self.run_map(p,self.selected(p));path=self.returned_gap(run)
        with self.store.db:
            pid=self.store.stage(question='What are our recovery targets?',answer='Our RPO is 2 hours.',scope='a',provenance={},submitter='source')
        self.store.resolve([pid],'approver','New policy')
        with self.assertRaisesRegex(ValueError,'stale'):ingest_feedback(self.store,path)

    def test_prepare_exposes_semantically_relevant_answers_even_without_keyword_overlap(self):
        p=self.source(question='Describe resilience objectives.')
        context=prepare(self.store,p,'a')
        self.assertEqual(2,context['scoped_entry_count']);self.assertEqual(2,len(context['scoped_kb']))
        self.assertTrue(any('RPO' in e['answer'] for e in context['scoped_kb']))
        self.assertIsNone(context['next_kb_offset'])
        self.assertTrue(all(e['scope']=='a' for e in context['scoped_kb']))

    def test_prepare_pagination_scope_and_unusable_evidence_flags(self):
        p=self.source()
        context=prepare(self.store,p,'a',kb_limit=1)
        self.assertEqual(1,context['next_kb_offset'])
        self.assertIsNone(prepare(self.store,p,'a',kb_limit=1,kb_offset=1)['next_kb_offset'])
        self.assertEqual([],prepare(self.store,p,'other')['scoped_kb'])
        with self.store.db:self.store.db.execute("UPDATE revisions SET approved_at='2000-01-01T00:00:00+00:00'")
        self.assertTrue(all(e['usability_problem'] for e in prepare(self.store,p,'a')['scoped_kb']))


if __name__=='__main__':unittest.main()
