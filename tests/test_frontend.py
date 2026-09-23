from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


class FrontendTests(unittest.TestCase):
    def test_calculate_change_and_restore(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")
        self.assertEqual(len(app.dataframe[0].value), 50)
        app.selectbox(key="measure_0").select("M9").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertNotEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")
        app.button[0].click().run()
        app.button[1].click().run()
        self.assertEqual(app.session_state["evaluation"]["result"]["score_exact"], "56.54307")

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
