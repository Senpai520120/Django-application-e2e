import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Page Object of the audit page.
 *
 */
export class AuditPage {
  constructor(readonly page: Page) {}

  async goto(query?: string): Promise<void> {
    const url = query ? `/manage/audit/?q=${encodeURIComponent(query)}` : "/manage/audit/";
    await this.page.goto(url);
    await expect(this.page.getByRole("heading", { name: "Audit: role changes" })).toBeVisible();
  }

}
