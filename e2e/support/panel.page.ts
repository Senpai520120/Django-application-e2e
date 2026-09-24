import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Page Object of the admin panel.
 *
 * A user row is found by the cell holding their username, and every action
 * is taken inside that row. The locator then depends neither on row order
 * nor on the fact that a Roles link also lives in the site header.
 */
export class PanelPage {
  constructor(readonly page: Page) {}

  /**
   * The list is paginated (10 rows), so a user is found through `?q=`
   * instead of hoping they happen to land on the first page.
   */
  async goto(query?: string): Promise<void> {
    const url = query ? `/manage/?q=${encodeURIComponent(query)}` : "/manage/";
    await this.page.goto(url);
    await expect(this.heading).toBeVisible();
  }

  get searchBox(): Locator {
    return this.page.getByRole("searchbox");
  }

  /** The same, but by hand through the search form, which checks it too. */
  async search(query: string): Promise<void> {
    await this.searchBox.fill(query);
    await this.page.getByRole("button", { name: "Search" }).click();
    await expect(this.heading).toBeVisible();
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: "Users" });
  }

  get status(): Locator {
    return this.page.getByRole("status");
  }

  /** The table row whose username matches in full. */
  row(username: string): Locator {
    return this.page
      .getByRole("row")
      .filter({ has: this.page.getByRole("cell", { name: username, exact: true }) });
  }

  /** A role badge inside the user row. */
  roleBadge(username: string, role: string): Locator {
    return this.row(username).getByText(role, { exact: true });
  }

  /**
   * Activity is read from the button rather than the column: an active user
   * is offered Deactivate, a switched-off one is offered Activate.
   */
  toggleButton(username: string): Locator {
    return this.row(username).getByRole("button");
  }

  async isActive(username: string): Promise<boolean> {
    return (await this.toggleButton(username).innerText()) === "Deactivate";
  }

  async toggleActive(username: string): Promise<void> {
    await this.toggleButton(username).click();
  }

  // --- roles form ------------------------------------------------------------

  async openRoles(username: string): Promise<void> {
    // Narrow the list down to this user first: every row carries a Roles
    // link, and on another page of the list it simply will not be there.
    await this.goto(username);
    await this.row(username).getByRole("link", { name: "Roles" }).click();
    await expect(
      this.page.getByRole("heading", { name: `Roles of user ${username}` }),
    ).toBeVisible();
  }

  roleCheckbox(role: string): Locator {
    return this.page.getByRole("checkbox", { name: role, exact: true });
  }

  async saveRoles(): Promise<void> {
    await this.page.getByRole("button", { name: "Save" }).click();
  }

  async cancelRoles(): Promise<void> {
    await this.page.getByRole("link", { name: "Cancel" }).click();
  }

  /** Bring the role set of a user to the wanted one and save. */
  async setRoles(username: string, roles: string[]): Promise<void> {
    await this.openRoles(username);

    for (const role of ["admin", "user"]) {
      const checkbox = this.roleCheckbox(role);
      if (roles.includes(role)) {
        await checkbox.check();
      } else {
        await checkbox.uncheck();
      }
    }

    await this.saveRoles();
  }

  // --- Roles and Audit pages ---------------------------------------------------

  async gotoRoles(): Promise<void> {
    await this.page.goto("/manage/roles/");
    await expect(
      this.page.getByRole("heading", { name: "Roles", exact: true }),
    ).toBeVisible();
  }

  /** Member-count cell of a role: the second column of the Roles table. */
  roleMembersCell(role: string): Locator {
    return this.page
      .getByRole("row")
      .filter({ has: this.page.getByRole("cell", { name: role, exact: true }) })
      .getByRole("cell")
      .last();
  }

  async roleMembers(role: string): Promise<number> {
    return Number(await this.roleMembersCell(role).innerText());
  }

  async gotoAudit(): Promise<void> {
    await this.page.goto("/manage/audit/");
    await expect(
      this.page.getByRole("heading", { name: "Audit: role changes" }),
    ).toBeVisible();
  }

  /**
   * The freshest log record. The model orders by `["-created_at", "-id"]`,
   * so this is the first row of the table body.
   */
  get lastAuditRow(): Locator {
    return this.page.getByRole("rowgroup").last().getByRole("row").first();
  }

  // --- creating a user ---------------------------------------------------------

  async openCreateUser(): Promise<void> {
    // Like openRoles, this gets to the list itself instead of assuming the
    // caller is already there: the panel fixture no longer navigates.
    await this.goto();
    await this.page.getByRole("link", { name: "+ New user" }).click();
    await expect(
      this.page.getByRole("heading", { name: "New user" }),
    ).toBeVisible();
  }

  async fillNewUser(data: {
    username: string;
    password: string;
    email?: string;
    roles?: string[];
  }): Promise<void> {
    await this.page.getByLabel("Username").fill(data.username);
    if (data.email) {
      await this.page.getByLabel("Email").fill(data.email);
    }
    for (const role of data.roles ?? []) {
      await this.roleCheckbox(role).check();
    }
    await this.page.getByLabel("Password:", { exact: true }).fill(data.password);
    await this.page.getByLabel("Password confirmation").fill(data.password);
  }

  async clickCreate(): Promise<void> {
    await this.page.getByRole("button", { name: "Create" }).click();
  }
}
