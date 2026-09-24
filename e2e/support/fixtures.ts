import { test as base, expect, type Page } from "@playwright/test";

import { PanelPage } from "./panel.page";
import { FileManagerPage } from "./file-manager.page";
import { AuditPage } from "./audit.page";


/** Аккаунты из seed_demo_users. Пароль общий, переопределяется через env. */
const password = process.env.E2E_PASSWORD ?? "demo-password-123";
const admin_user = process.env.E2E_ADMINUSERNAME ?? "demo_admin";
const simple_user = process.env.E2E_SIMPLE_USERNAME ?? "demo_user";
const inactive_user = process.env.E2E_INACTIVE_USERNAME ?? "demo_inactive";

export const users = {
  admin: { username: admin_user, password },
  user: { username: simple_user, password },
  inactive: { username: inactive_user, password },
} as const;

export function uniqueName(prefix: string): string {
  const stamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 7);
  return `${prefix}-${stamp}-${random}`;
}

export async function loginAs(
  page: Page,
  account: { username: string; password: string },
): Promise<void> {
  await page.goto("/login/");
  await page.getByLabel("Username").fill(account.username);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /You are signed in as/ })).toBeVisible();
}

export async function login(page: Page): Promise<void> {
  await loginAs(page, users.admin);
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}

type Fixtures = {
  /** page с уже активной сессией админа. */
  signedIn: Page;
  fileManager: FileManagerPage;
  /** Список пользователей /manage/. */
  panel: PanelPage;
  /** Аудит /manage/audit/. */
  audit: AuditPage;
  workspace: string;
};

export const test = base.extend<Fixtures>({
  signedIn: async ({ page }, use) => {
    await login(page);
    await use(page);
  },

  panel: async ({ signedIn }, use) => {
    await use(new PanelPage(signedIn));
  },

  audit: async ({ signedIn }, use) => {
    await use(new AuditPage(signedIn));
  },

  fileManager: async ({ signedIn }, use) => {
    await use(new FileManagerPage(signedIn));
  },

  workspace: async ({ fileManager }, use, testInfo) => {
      const folder = uniqueName(testInfo.title.replace(/[^a-zA-Z0-9]+/g, "-"));

      await fileManager.goto();
      await fileManager.createFolder(folder);
      await fileManager.openFolder(folder);

      await use(folder);

      await fileManager.removeIfExists(folder);
    }
});

export { expect };
