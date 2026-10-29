"""What every page of the app has: an address, a header and status messages."""

from playwright.sync_api import Page


class BasePage:
    # Address of the page. Every page class sets its own.
    path = "/"

    def __init__(self, page: Page):
        self.page = page

        # The green or red message the app shows after an action,
        # for example "User demo_user disabled."
        self.status_message = page.get_by_role("status")

        self.sign_out_button = page.get_by_role("button", name="Sign out")

    def open(self):
        """Go to this page's address and return the page object itself.

        Returning `self` lets us write `LoginPage(page).open().sign_in(...)`.
        """
        self.page.goto(self.path)
        return self

    def header_link(self, name: str):
        """A link in the top bar: "Files", "Users", "Roles" or "Audit"."""
        return self.page.get_by_role("banner").get_by_role(
            "link", name=name, exact=True
        )

    def submit(self, button) -> None:
        """Click a button that sends a form, and wait for the page it leads to.

        Every form of the app answers with a new page (after a redirect, or
        the same page with errors). We wait until that page has loaded, not
        only until the server answered. Otherwise the next step of a test
        can still see the old page: a check passes on stale content, or a
        field is filled just before the page is replaced. Fast browsers
        (WebKit) show this at once. So every Page Object method that sends
        a form, GET or POST, clicks through submit().
        """
        with self.page.expect_navigation():
            button.click()

    def sign_out(self) -> None:
        self.submit(self.sign_out_button)
