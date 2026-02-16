from django.test import TestCase


class PagesMarkdownEndpointsTestCase(TestCase):
    def test_skill_markdown_endpoint(self):
        response = self.client.get("/skill.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("Agent Commons Skill", response.content.decode())

    def test_heartbeat_markdown_endpoint(self):
        response = self.client.get("/heartbeat.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("HEARTBEAT_OK", response.content.decode())
