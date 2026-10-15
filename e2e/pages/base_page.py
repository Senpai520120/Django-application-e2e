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
        """Click a button that sends a form, and wait for the server's answer.

        Without the wait, the next step of a test can open another page
        before the form has reached the server, and the action is lost.
        Fast browsers (WebKit) show this at once. So every Page Object
        method that sends a form clicks through submit().
        """
        with self.page.expect_response(
            lambda response: response.request.method == "POST"
        ):
            button.click()

    def sign_out(self) -> None:
        self.submit(self.sign_out_button)
