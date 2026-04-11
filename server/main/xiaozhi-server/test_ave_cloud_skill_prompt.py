import os
import tempfile
import unittest
from pathlib import Path

from core.providers.intent.intent_llm.intent_llm import IntentProvider
from core.utils import ave_cloud_skill_prompt as skill_prompt
from core.utils.prompt_manager import PromptManager


class AveCloudSkillPromptTests(unittest.TestCase):
    def test_default_skill_root_uses_repo_relative_path(self):
        expected = Path(__file__).resolve().parent / "ave-cloud-skill"
        self.assertEqual(skill_prompt._default_skill_root(), expected)

    def test_append_ave_cloud_skill_corpus_reads_raw_files_verbatim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "skills" / "ave-wallet-suite").mkdir(parents=True)
            (root / "skills" / "data-rest").mkdir(parents=True)
            (root / "references").mkdir(parents=True)
            (root / "skills" / "ave-wallet-suite" / "SKILL.md").write_text(
                "wallet-suite raw text",
                encoding="utf-8",
            )
            (root / "skills" / "data-rest" / "SKILL.md").write_text(
                "data-rest raw text",
                encoding="utf-8",
            )
            (root / "references" / "operator-playbook.md").write_text(
                "operator raw text",
                encoding="utf-8",
            )

            previous = os.environ.get("AVE_CLOUD_SKILL_DIR")
            os.environ["AVE_CLOUD_SKILL_DIR"] = str(root)
            skill_prompt.load_ave_cloud_skill_corpus.cache_clear()
            try:
                prompt = skill_prompt.append_ave_cloud_skill_corpus("BASE")
            finally:
                if previous is None:
                    os.environ.pop("AVE_CLOUD_SKILL_DIR", None)
                else:
                    os.environ["AVE_CLOUD_SKILL_DIR"] = previous
                skill_prompt.load_ave_cloud_skill_corpus.cache_clear()

        self.assertIn("BASE", prompt)
        self.assertIn("wallet-suite raw text", prompt)
        self.assertIn("data-rest raw text", prompt)
        self.assertIn("operator raw text", prompt)

    def test_prompt_manager_includes_raw_skill_corpus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "skills" / "ave-wallet-suite").mkdir(parents=True)
            (root / "skills" / "ave-wallet-suite" / "SKILL.md").write_text(
                "wallet-suite raw text",
                encoding="utf-8",
            )

            previous = os.environ.get("AVE_CLOUD_SKILL_DIR")
            os.environ["AVE_CLOUD_SKILL_DIR"] = str(root)
            skill_prompt.load_ave_cloud_skill_corpus.cache_clear()
            try:
                manager = PromptManager({"prompt_template": ""}, None)
                prompt = manager.get_quick_prompt("BASE")
            finally:
                if previous is None:
                    os.environ.pop("AVE_CLOUD_SKILL_DIR", None)
                else:
                    os.environ["AVE_CLOUD_SKILL_DIR"] = previous
                skill_prompt.load_ave_cloud_skill_corpus.cache_clear()

        self.assertIn("BASE", prompt)
        self.assertIn("wallet-suite raw text", prompt)

    def test_intent_prompt_includes_raw_skill_corpus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "skills" / "ave-wallet-suite").mkdir(parents=True)
            (root / "skills" / "ave-wallet-suite" / "SKILL.md").write_text(
                "wallet-suite raw text",
                encoding="utf-8",
            )

            previous = os.environ.get("AVE_CLOUD_SKILL_DIR")
            os.environ["AVE_CLOUD_SKILL_DIR"] = str(root)
            skill_prompt.load_ave_cloud_skill_corpus.cache_clear()
            try:
                provider = IntentProvider({})
                prompt = provider.get_intent_system_prompt([])
            finally:
                if previous is None:
                    os.environ.pop("AVE_CLOUD_SKILL_DIR", None)
                else:
                    os.environ["AVE_CLOUD_SKILL_DIR"] = previous
                skill_prompt.load_ave_cloud_skill_corpus.cache_clear()

        self.assertIn("wallet-suite raw text", prompt)


if __name__ == "__main__":
    unittest.main()
