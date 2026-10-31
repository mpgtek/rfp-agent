import copy
import unittest
from rfp_agent.composition import compose


class CompositionTests(unittest.TestCase):
    def selected(self,text,indices=None):
        return {"response":text,"claims":[{"text":text,"part_indices":indices or [0],
                 "supported":True,"support_note":"Claim follows from the cited source fact."}],
                "composition_review":{k:True for k in ("supported","complete","relevant","appropriate_detail")}}

    def test_architecture_summary_omits_unrequested_log_and_identifier_details(self):
        quotes=["Fable is a multi-tenant SaaS application and so we don't share customer logs.",
                "Our application is hosted in AWS in us-east-1 (us-west-1 failover)."]
        text="Fable is a multi-tenant SaaS platform hosted on AWS."
        answer,audit=compose(self.selected(text,[0,1]),quotes)
        self.assertEqual(text,answer)
        self.assertNotIn("logs",answer)
        self.assertTrue(audit["review"]["appropriate_detail"])

    def test_unsupported_protocol_vendor_or_marketing_claim_is_rejected(self):
        for text in ("We support SAML and OIDC.","We host on Azure.","We provide unlimited availability."):
            with self.assertRaises(ValueError):
                compose(self.selected(text),["We support SAML 2.0 on AWS."])

    def test_new_numeric_commitment_is_rejected(self):
        with self.assertRaises(ValueError):
            compose(self.selected("Our SLA is 99.99%."),["Our SLA is 99.7%."])

    def test_negative_capability_cannot_be_rewritten_as_supported(self):
        with self.assertRaisesRegex(ValueError,"negation"):
            compose(self.selected("We support OIDC."),["We do not support OIDC."])

    def test_negative_answer_can_be_rephrased_without_adding_unrelated_claim(self):
        text="PCI-DSS is not applicable to our application."
        answer,_=compose(self.selected(text),["HIPAA and PCI-DSS is not applicable to our application."])
        self.assertEqual(text,answer)
        self.assertNotIn("HIPAA",answer)

    def test_future_or_plan_limited_capability_does_not_become_unconditional(self):
        for quote in ("OIDC support is planned.","OIDC support is available only on Enterprise."):
            with self.assertRaises(ValueError):
                compose(self.selected("We support OIDC."),[quote])

    def test_uncited_text_or_invalid_citation_is_rejected(self):
        selected=self.selected("We support SAML 2.0.")
        selected["response"]+=" We support OIDC."
        with self.assertRaisesRegex(ValueError,"uncited"):
            compose(selected,["We support SAML 2.0."])
        with self.assertRaises(ValueError):
            compose(self.selected("We support SAML 2.0.",[99]),["We support SAML 2.0."])

    def test_composition_requires_explicit_support_relevance_and_detail_review(self):
        for key in ("supported","complete","relevant","appropriate_detail"):
            selected=self.selected("We support SAML 2.0.")
            selected["composition_review"][key]=False
            with self.assertRaisesRegex(ValueError,"review"):
                compose(selected,["We support SAML 2.0."])
