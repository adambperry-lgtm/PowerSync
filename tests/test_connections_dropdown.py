import unittest
import os

class TestConnectionsDropdown(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.html_path = os.path.join(self.base_dir, "app", "static", "index.html")
        self.css_path = os.path.join(self.base_dir, "app", "static", "css", "style.css")
        self.js_path = os.path.join(self.base_dir, "app", "static", "js", "app.js")

        with open(self.html_path, "r", encoding="utf-8") as f:
            self.html = f.read()

        with open(self.css_path, "r", encoding="utf-8") as f:
            self.css = f.read()

        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js = f.read()

    def test_dropdown_html_elements(self):
        """Verify the connections dropdown wrapper, button, badge, and menu in index.html."""
        self.assertIn('id="connectionsDropdownWrapper"', self.html)
        self.assertIn('id="btnConnectionsDropdown"', self.html)
        self.assertIn('id="connectionsSummaryDot"', self.html)
        self.assertIn('id="connectionsCountBadge"', self.html)
        self.assertIn('id="connectionsDropdownMenu"', self.html)
        self.assertIn('id="btnDropdownManage"', self.html)

        # Service item IDs must be preserved inside the dropdown
        self.assertIn('id="badgeWhoop"', self.html)
        self.assertIn('id="whoopStatusText"', self.html)
        self.assertIn('id="badgeStrava"', self.html)
        self.assertIn('id="stravaStatusText"', self.html)
        self.assertIn('id="badgeZwift"', self.html)
        self.assertIn('id="zwiftStatusText"', self.html)
        self.assertIn('id="zwiftNavDot"', self.html)
        self.assertIn('id="badgeGemini"', self.html)
        self.assertIn('id="geminiNavStatusText"', self.html)
        self.assertIn('id="geminiNavDot"', self.html)

    def test_tab_switcher_and_dropdown_in_same_navbar_row(self):
        """Verify that the tab switcher and connections dropdown are both within the top navbar."""
        navbar_start = self.html.index('<header class="navbar">')
        navbar_end = self.html.index('</header>')
        switcher_pos = self.html.index('class="main-view-switcher"')
        dropdown_pos = self.html.index('id="connectionsDropdownWrapper"')

        self.assertTrue(navbar_start < switcher_pos < navbar_end)
        self.assertTrue(navbar_start < dropdown_pos < navbar_end)

    def test_dropdown_css_styles(self):
        """Verify CSS contains connections dropdown styles and light theme rules."""
        self.assertIn('.connections-dropdown-wrapper', self.css)
        self.assertIn('.connections-dropdown-btn', self.css)
        self.assertIn('.connections-dropdown-menu', self.css)
        self.assertIn('.connections-count-badge', self.css)
        self.assertIn('.connections-dropdown-item', self.css)
        self.assertIn('[data-theme="light"] .connections-dropdown-btn', self.css)
        self.assertIn('[data-theme="light"] .connections-dropdown-menu', self.css)

    def test_dropdown_js_behavior(self):
        """Verify JavaScript implements dropdown interactions and summary status calculations."""
        self.assertIn('function initConnectionsDropdown()', self.js)
        self.assertIn('connectionsSummaryDot', self.js)
        self.assertIn('connectionsCountBadge', self.js)
        self.assertIn('connectionsDropdownWrapper', self.js)

if __name__ == "__main__":
    unittest.main()
