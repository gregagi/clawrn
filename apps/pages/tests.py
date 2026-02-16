from django.test import TestCase


class PagesMarkdownEndpointsTestCase(TestCase):
    def test_skill_markdown_endpoint(self):
        response = self.client.get("/skill.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("Agent Commons Skill", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Version"], "1.0.0")
        self.assertEqual(response["X-Agent-Commons-Docs-Channel"], "stable")

    def test_skill_markdown_v1_endpoint(self):
        response = self.client.get("/skill/v1.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("versioned:", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Channel"], "v1")

    def test_heartbeat_markdown_endpoint(self):
        response = self.client.get("/heartbeat.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("HEARTBEAT_OK", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Version"], "1.0.0")

    def test_heartbeat_markdown_v1_endpoint(self):
        response = self.client.get("/heartbeat/v1.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("versioned:", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Channel"], "v1")
