from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from backend.ai_analyst import AnalysisUnavailable


APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.ai_patch = patch("backend.ai_analyst.generate_analysis", return_value="Тестовый ответ API")
        self.ai = self.ai_patch.start()
        self.addCleanup(self.ai_patch.stop)

    def test_calculate_change_and_restore(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")
        self.assertEqual(len(app.dataframe[0].value), 50)
        self.ai.assert_called_once()
        app.run()
        app.button[1].click().run()
        self.ai.assert_called_once()
        app.selectbox(key="measure_0").select("M9").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertNotEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")
        app.button[0].click().run()
        app.button[1].click().run()
        self.assertEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")

    def test_ai_failure_keeps_calculation_and_can_retry(self):
        self.ai.side_effect = [AnalysisUnavailable("Нет связи с OpenAI"), "Повторный ответ API"]
        app = AppTest.from_file(str(APP)).run()
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")
        self.assertEqual(len(app.dataframe[0].value), 50)
        self.assertIn("Нет связи", app.warning[0].value)
        self.assertIsNotNone(app.button(key="retry_ai"))
        app.run()
        self.ai.assert_called_once()
        app.button(key="retry_ai").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["evaluation"]["ai_analysis"], "Повторный ответ API")
        self.assertNotIn("ai_error", app.session_state["evaluation"])
        self.assertEqual(self.ai.call_count, 2)

    def test_backend_error_visible_without_result(self):
        app = AppTest.from_file(str(APP)).run()
        app.selectbox(key="measure_4").select("M4").run()
        app.selectbox(key="district_4").select("nura").run()
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertIn("M4 и M7", app.error[0].value)
        self.assertEqual(len(app.dataframe), 0)


if __name__ == "__main__":
    unittest.main()
