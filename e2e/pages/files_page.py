"""File manager: /files/"""

from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Page

from pages.base_page import BasePage


class FilesPage(BasePage):
    path = "/files/"

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name="Files")
        self.new_folder_input = page.get_by_label("New folder")
        self.create_folder_button = page.get_by_role("button", name="Create folder")
        self.file_input = page.get_by_label("Upload files")
        self.upload_button = page.get_by_role("button", name="Upload", exact=True)
        self.empty_folder_text = page.get_by_text("Folder is empty.")

        # Breadcrumbs: "Root / folder / subfolder". The current folder
        # is marked with aria-current="page".
        self.breadcrumbs = page.get_by_role("navigation", name="Path")
        self.current_folder = self.breadcrumbs.locator("[aria-current='page']")

        # Confirmation page that opens after clicking "Delete <name>".
        self.confirm_delete_button = page.get_by_role("button", name="Delete")
        self.cancel_delete_link = page.get_by_role("link", name="Cancel")
        self.folder_contents_warning = page.get_by_text(
            "The folder will be deleted with everything inside"
        )

        # Rename page that opens after clicking "Rename <name>".
        self.new_name_input = page.get_by_label("New name")
        self.save_button = page.get_by_role("button", name="Save")

    def open_folder_by_path(self, folder_path: str):
        """Open a folder straight by its address, for example "e2e_workspace_1a2b"."""
        self.page.goto(f"{self.path}?path={quote(folder_path)}")
        return self

    # --- one entry of the list (a file or a folder) ---

    def entry(self, name: str):
        """The link with the name of a file or a folder."""
        return self.page.get_by_role("link", name=name, exact=True)

    def entry_row(self, name: str):
        """The whole table row of a file or a folder: name, type, size, date."""
        return self.page.get_by_role("row").filter(has=self.entry(name))

    # --- actions ---

    def create_folder(self, name: str) -> None:
        self.new_folder_input.fill(name)
        self.submit(self.create_folder_button)

    def open_folder(self, name: str) -> None:
        self.entry(name).click()

    def upload(self, *files: Path) -> None:
        """Upload one or several files from the disk."""
        self.file_input.set_input_files(list(files))
        self.submit(self.upload_button)

    def start_delete(self, name: str) -> None:
        """Click "Delete" next to an entry. A confirmation page opens."""
        self.page.get_by_role("link", name=f"Delete {name}").click()

    def delete(self, name: str) -> None:
        """Delete an entry and confirm."""
        self.start_delete(name)
        self.submit(self.confirm_delete_button)

    def rename(self, name: str, new_name: str) -> None:
        self.page.get_by_role("link", name=f"Rename {name}").click()
        self.new_name_input.fill(new_name)
        self.submit(self.save_button)

    def breadcrumb(self, name: str):
        """A link in the breadcrumbs, for example "Root"."""
        return self.breadcrumbs.get_by_role("link", name=name, exact=True)
