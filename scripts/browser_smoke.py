"""Browser QA against a running local app; no live collection or AI calls."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "artifacts"
    output.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector(".pair-card")
        assert page.locator(".pair-card").count() > 0
        if page.locator("#more-pairs").is_visible():
            before = page.locator(".pair-card").count()
            page.locator("#more-pairs").click()
            assert page.locator(".pair-card").count() > before
        page.screenshot(path=str(output / "desktop-library.png"), full_page=True)
        page.locator(".pair-card").first.click()
        page.wait_for_selector("#report:not([hidden])")
        assert page.locator("#comparison tbody tr").count() == 6
        page.screenshot(path=str(output / "desktop-report.png"), full_page=True)
        page.get_by_role("tab", name="Runes & builds").click()
        assert page.locator("#builds .panel").count() == 2
        page.get_by_role("tab", name="Game evidence").click()
        page.locator(".game-detail").first.click()
        page.wait_for_selector("dialog[open]")
        assert page.locator("#match-detail h2").inner_text()
        page.screenshot(path=str(output / "match-detail.png"), full_page=True)
        page.get_by_role("button", name="Close match detail").click()
        page.get_by_role("tab", name="AI coach").click()
        assert page.locator("#coach-question").is_visible()
        page.locator('[data-view="collect"]').click()
        assert page.locator("#collect-form").is_visible()
        page.locator('[data-view="settings"]').click()
        assert page.locator("#riot-status").is_visible()
        page.locator('[data-view="explore"]').click()
        page.locator("#back-library").click()
        page.wait_for_selector("#library:not([hidden])")
        page.locator("#champion").fill("NoStoredChampion")
        page.locator("#opponent").fill("NoStoredOpponent")
        page.get_by_role("button", name="Explore matchup").click()
        expect(page.locator("#matchup-heading")).to_contain_text("0 unique games")
        assert "No recorded games" in page.locator("#observations").inner_text()
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#back-library").click()
        page.wait_for_selector("#library:not([hidden])")
        page.screenshot(path=str(output / "mobile-library.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile layout overflows horizontally"
        page.locator(".pair-card").first.click()
        page.wait_for_selector("#report:not([hidden])")
        page.screenshot(path=str(output / "mobile-report.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile report overflows horizontally"
        assert not errors, errors
        browser.close()
    print("Browser QA passed: library, report, builds, games, dialog, coach, collection, connections, empty sample, mobile layout.")
    print("Screenshots saved under artifacts/ (ignored by Git).")


if __name__ == "__main__":
    main()
