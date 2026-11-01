import unittest
import os

class TestMainViewSwitcher(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.html_path = os.path.join(self.base_dir, "app", "static", "index.html")
        self.css_path = os.path.join(self.base_dir, "app", "static", "css", "style.css")
        self.js_path = os.path.join(self.base_dir, "app", "static", "js", "app.js")

        with open(self.html_path, "r", encoding="utf-8") as f:
            self.html_content = f.read()

        with open(self.css_path, "r", encoding="utf-8") as f:
            self.css_content = f.read()

        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js_content = f.read()

    def test_html_view_switcher_structure(self):
        """Verify the segmented tab switcher toggle elements and views in index.html."""
        self.assertIn('class="main-view-switcher"', self.html_content)
        self.assertIn('id="tabMainViewDaily"', self.html_content)
        self.assertIn('id="tabMainViewAnalysis"', self.html_content)
        self.assertIn('id="viewDailyContainer"', self.html_content)
        self.assertIn('id="viewAnalysisContainer"', self.html_content)

        # Tab switcher is placed directly in the top header navbar alongside nav-actions and brand
        navbar_start = self.html_content.index('<header class="navbar">')
        navbar_end = self.html_content.index('</header>')
        switcher_idx = self.html_content.index('class="main-view-switcher"')
        nav_actions_idx = self.html_content.index('class="nav-actions"')
        self.assertTrue(navbar_start < switcher_idx < navbar_end)
        self.assertTrue(navbar_start < nav_actions_idx < navbar_end)

        # Ensure cards are partitioned into their respective view containers
        daily_idx = self.html_content.index('id="viewDailyContainer"')
        analysis_idx = self.html_content.index('id="viewAnalysisContainer"')

        whoop_idx = self.html_content.index('id="cardWhoop"')
        stage_idx = self.html_content.index('id="workoutStageSection"')
        workouts_idx = self.html_content.index('id="cardRecentWorkouts"')
        spiderweb_idx = self.html_content.index('id="cardPowerSpiderweb"')
        program_idx = self.html_content.index('id="cardProgram"')
        athlete_idx = self.html_content.index('id="cardAthlete"')

        # Daily container elements must precede analysis container
        self.assertTrue(daily_idx < whoop_idx < analysis_idx)
        self.assertTrue(daily_idx < stage_idx < analysis_idx)
        self.assertTrue(daily_idx < workouts_idx < analysis_idx)

        # Analysis container elements must follow analysis container start
        self.assertTrue(analysis_idx < spiderweb_idx)
        self.assertTrue(analysis_idx < program_idx)
        self.assertTrue(analysis_idx < athlete_idx)

    def test_css_view_switcher_styling(self):
        """Verify CSS contains view switcher styles and animation."""
        self.assertIn('.main-view-switcher', self.css_content)
        self.assertIn('.main-view-tab-btn', self.css_content)
        self.assertIn('.main-view-pane', self.css_content)
        self.assertIn('.hidden-pane', self.css_content)
        self.assertIn('@keyframes fadeInMainView', self.css_content)

    def test_js_view_switcher_implementation(self):
        """Verify app.js implements view switcher functions and state persistence."""
        self.assertIn('function switchMainDashboardView', self.js_content)
        self.assertIn('function initMainViewSwitcher', self.js_content)
        self.assertIn('powersync_main_view', self.js_content)
        self.assertIn('currentActiveMainView', self.js_content)

if __name__ == "__main__":
    unittest.main()
