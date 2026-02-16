from django.test import TestCase


class DocsNavigationTestCase(TestCase):
    def test_docs_home_redirects_to_getting_started(self):
        response = self.client.get("/docs/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/docs/getting-started/introduction/")

    def test_docs_navigation_excludes_deployment_category(self):
        response = self.client.get("/docs/getting-started/introduction/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Getting Started")
        self.assertContains(response, "Features")
        self.assertNotContains(response, "Deployment")

    def test_agent_qa_loop_page_is_available(self):
        response = self.client.get("/docs/features/agent-qa-loop/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agent Q&amp;A Loop")
