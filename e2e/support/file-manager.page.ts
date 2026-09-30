import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Page Object of the file manager.
 *
 * Every locator goes through a role, a label or an aria-label: those survive
 * markup edits, unlike the CSS selectors codegen hands out.
 */
export class FileManagerPage {
  constructor(readonly page: Page) {}

  async goto(path = ""): Promise<void> {
    const url = path ? `/files/?path=${encodeURIComponent(path)}` : "/files/";
    await this.page.goto(url);
    await expect(this.heading).toBeVisible();
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: "Files" });
  }

  get status(): Locator {
    return this.page.getByRole("status");
  }

  /** The table row holding an entry with this name. */
  row(name: string): Locator {
    return this.page
      .getByRole("row")
      .filter({ has: this.page.getByRole("link", { name, exact: true }) });
  }

  entryLink(name: string): Locator {
    return this.page.getByRole("link", { name, exact: true });
  }

  async createFolder(name: string): Promise<void> {
    await this.page.getByLabel("New folder").fill(name);
    await this.page.getByRole("button", { name: "Create folder" }).click();
  }

  async openFolder(name: string): Promise<void> {
    await this.entryLink(name).click();
    await expect(this.breadcrumbCurrent).toHaveText(name);
  }

  get breadcrumbCurrent(): Locator {
    return this.page.locator("[aria-current='page']");
  }

  async goToRootCrumb(): Promise<void> {
    await this.page.getByRole("link", { name: "Root", exact: true }).click();
  }

  async goUp(): Promise<void> {
    await this.page.getByRole("link", { name: "← Up" }).click();
  }

  /** Upload files assembled right in the test's memory. */
  async uploadFiles(
    files: { name: string; mimeType: string; buffer: Buffer }[],
  ): Promise<void> {
    await this.page.getByLabel("Upload files").setInputFiles(files);
    await this.page.getByRole("button", { name: "Upload", exact: true }).click();
  }

  async renameEntry(name: string, newName: string): Promise<void> {
    await this.page.getByRole("link", { name: `Rename ${name}` }).click();
    await this.page.getByLabel("New name").fill(newName);
    await this.page.getByRole("button", { name: "Save" }).click();
  }

  async deleteEntry(name: string, confirm = true): Promise<void> {
    await this.page.getByRole("link", { name: `Delete ${name}` }).click();
    if (confirm) {
      await this.page.getByRole("button", { name: "Delete" }).click();
    } else {
      await this.page.getByRole("link", { name: "Cancel" }).click();
    }
  }

  /** Deletion during cleanup: do not fail if the entry is already gone. */
  async removeIfExists(name: string): Promise<void> {
    await this.goto();
    if ((await this.entryLink(name).count()) > 0) {
      await this.deleteEntry(name);
    }
  }
}
