import { expect, test, uniqueName } from "./support/fixtures";

/**
 * The admin panel in a browser.
 *
 * Roles and activity are exercised on the `demo_user` demo account, so
 * every test puts it back into the original state: the role set
 * `["user"]` and an active account. Runs are single-threaded, so the
 * state never races.
 */
const TARGET = "demo_user";

test.describe("Panel: roles", () => {
  test.afterEach(async ({ panel }) => {
    await panel.setRoles(TARGET, ["user"]);
  });

  test("an admin grants a role and it shows up in the list", async ({ panel }) => {
    await test.step("the user starts with the user role only", async () => {
      await panel.goto(TARGET);
      await expect(panel.roleBadge(TARGET, "user")).toBeVisible();
      await expect(panel.roleBadge(TARGET, "admin")).toHaveCount(0);
    });

    await test.step("tick the admin role and save", async () => {
      await panel.openRoles(TARGET);
      await panel.roleCheckbox("admin").check();
      await panel.saveRoles();
    });

    await test.step("the role is visible in the user row", async () => {
      await expect(panel.status).toContainText("updated");
      await expect(panel.roleBadge(TARGET, "admin")).toBeVisible();
      await expect(panel.roleBadge(TARGET, "user")).toBeVisible();
    });
  });

  test("an admin revokes a role and it disappears from the list", async ({ panel }) => {
    await test.step("revoke the only role", async () => {
      await panel.openRoles(TARGET);
      await panel.roleCheckbox("user").uncheck();
      await panel.saveRoles();
    });

    await test.step("the role badge is gone", async () => {
      await expect(panel.status).toContainText("updated");
      await expect(panel.roleBadge(TARGET, "user")).toHaveCount(0);
    });
  });

  test("cancelling the roles form changes nothing", async ({ panel }) => {
    await panel.openRoles(TARGET);

    await test.step("tick admin but leave through Cancel", async () => {
      await panel.roleCheckbox("admin").check();
      await panel.cancelRoles();
    });

    await test.step("the roles are unchanged", async () => {
      await expect(panel.heading).toBeVisible();
      await panel.goto(TARGET);
      await expect(panel.roleBadge(TARGET, "admin")).toHaveCount(0);
      await expect(panel.roleBadge(TARGET, "user")).toBeVisible();
    });
  });

  test("an admin cannot strip the admin role from themselves", async ({ panel }) => {
    await panel.openRoles("demo_admin");

    await test.step("try to remove our own only admin role", async () => {
      await panel.roleCheckbox("admin").uncheck();
      await panel.saveRoles();
    });

    await test.step("the form refuses and explains why", async () => {
      await expect(
        panel.page.getByText("You cannot take the admin role from yourself"),
      ).toBeVisible();
    });

    await panel.cancelRoles();
    await panel.goto("demo_admin");
    await expect(panel.roleBadge("demo_admin", "admin")).toBeVisible();
  });
});

test.describe("Panel: activity", () => {
  // Tests are retried in CI: if a run dies between switching the user off
  // and back on, the account has to return to the active state by itself.
  test.afterEach(async ({ panel }) => {
    await panel.goto(TARGET);
    if (!(await panel.isActive(TARGET))) {
      await panel.toggleActive(TARGET);
    }
  });

  test("deactivating a user and switching them back on", async ({ panel }) => {
    await panel.goto(TARGET);
    expect(await panel.isActive(TARGET)).toBe(true);

    await test.step("switch the user off", async () => {
      await panel.toggleActive(TARGET);

      await expect(panel.status).toContainText("disabled");
      await expect(panel.toggleButton(TARGET)).toHaveText("Activate");
    });

    await test.step("switch them back on", async () => {
      await panel.toggleActive(TARGET);

      await expect(panel.status).toContainText("enabled");
      await expect(panel.toggleButton(TARGET)).toHaveText("Deactivate");
    });
  });
});

test.describe("Panel: audit log and counters", () => {
  test.afterEach(async ({ panel }) => {
    await panel.setRoles(TARGET, ["user"]);
  });

  test("granting and revoking a role both land in the audit log", async ({ panel }) => {
    await panel.setRoles(TARGET, ["admin", "user"]);

    await test.step("the top log row: who did what, with which role, to whom", async () => {
      await panel.gotoAudit();
      const row = panel.lastAuditRow;

      await expect(
        row.getByRole("cell", { name: "demo_admin", exact: true }),
      ).toBeVisible();
      await expect(
        row.getByRole("cell", { name: "granted", exact: true }),
      ).toBeVisible();
      await expect(row.getByRole("cell", { name: "admin", exact: true })).toBeVisible();
      await expect(row.getByRole("cell", { name: TARGET, exact: true })).toBeVisible();
    });

    await test.step("revoking a role is written as its own record", async () => {
      await panel.setRoles(TARGET, ["user"]);
      await panel.gotoAudit();
      const row = panel.lastAuditRow;

      await expect(row.getByRole("cell", { name: "revoked", exact: true })).toBeVisible();
      await expect(row.getByRole("cell", { name: "admin", exact: true })).toBeVisible();
      await expect(row.getByRole("cell", { name: TARGET, exact: true })).toBeVisible();
    });
  });

  test("the counter on the Roles page follows a granted role", async ({ panel }) => {
    await panel.gotoRoles();
    const before = await panel.roleMembers("admin");

    await test.step("after granting, the admin role holds one more member", async () => {
      await panel.setRoles(TARGET, ["admin", "user"]);
      await panel.gotoRoles();
      await expect(panel.roleMembersCell("admin")).toHaveText(String(before + 1));
    });

    await test.step("after revoking, the counter comes back", async () => {
      await panel.setRoles(TARGET, ["user"]);
      await panel.gotoRoles();
      await expect(panel.roleMembersCell("admin")).toHaveText(String(before));
    });
  });
});

test.describe("Panel: creating a user", () => {
  test("an admin creates a user and grants a role right away", async ({ panel }) => {
    // The panel deliberately cannot delete users, so a unique name is the
    // only way to keep this test repeatable.
    const username = uniqueName("e2e").replace(/-/g, "_");

    await panel.openCreateUser();
    await panel.fillNewUser({
      username,
      password: "E2e-Strong-Pass-42",
      email: `${username}@example.com`,
      roles: ["user"],
    });
    await panel.clickCreate();

    await test.step("the user shows up in the list with the granted role", async () => {
      await expect(panel.status).toContainText("created");
      await panel.search(username);
      await expect(panel.row(username)).toBeVisible();
      await expect(panel.roleBadge(username, "user")).toBeVisible();
    });
  });

  test("a password that is too simple is refused", async ({ panel }) => {
    const username = uniqueName("weak").replace(/-/g, "_");

    await panel.openCreateUser();
    await panel.fillNewUser({ username, password: "52012000" });
    await panel.clickCreate();

    await test.step("the form explains the problem and creates no user", async () => {
      await expect(
        panel.page.getByText("This password is entirely numeric"),
      ).toBeVisible();

      // After the refusal we are still on the form, so reach the list by URL.
      await panel.goto(username);
      await expect(panel.page.getByText("Nothing found")).toBeVisible();
      await expect(panel.row(username)).toHaveCount(0);
    });
  });
});
