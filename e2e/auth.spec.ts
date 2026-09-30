import { expect, test as anonymous } from "@playwright/test";

import { test } from "./support/fixtures";

anonymous.describe("Section access", () => {
  anonymous("an anonymous visitor is sent to login instead of seeing files", async ({ page }) => {
    await page.goto("/files/");

    await expect(page).toHaveURL("/login/?next=/files/");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  anonymous("an anonymous visitor cannot open a nested folder by direct link", async ({
    page,
  }) => {
    await page.goto("/files/?path=docs");

    await expect(page).toHaveURL(/\/login\//);
  });

  anonymous("bad credentials are refused without revealing whether the user exists", async ({
    page,
  }) => {
    await page.goto("/login/");

    await page.getByLabel("Username").fill("demo_admin");
    await page.getByLabel("Password").fill("definitely-not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    const wrongPassword = await page.getByRole("listitem").first().innerText();

    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(wrongPassword).toContain("Please enter a correct");

    await page.getByLabel("Username").fill("no-such-user-here");
    await page.getByLabel("Password").fill("definitely-not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    const unknownUser = await page.getByRole("listitem").first().innerText();

    // Identical texts mean the response never tells whether the login exists.
    expect(unknownUser).toBe(wrongPassword);
  });
});

test.describe("Login and moving into the section", () => {
  test("after login the header carries a link to the files", async ({ fileManager }) => {
    const { page } = fileManager;

    await test.step("go back to the home page", async () => {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: /You are signed in as/ })).toBeVisible();
    });

    await test.step("open the file manager from the header", async () => {
      await page.getByRole("link", { name: "Files", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Files" })).toBeVisible();
      await expect(page).toHaveURL(/\/files\//);
    });
  });
});
