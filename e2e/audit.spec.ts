import { expect, test } from "./support/fixtures";


test.describe("User Management", () => {

  test("Create new user, grant roles, check audit log", async ({ panel, audit }) => {
    const username = "testuser_" + Math.random().toString(36).substring(2, 8);
    const role = "user";

    await panel.page.getByRole('link', { name: 'Users', exact: true }).click();
    await panel.openCreateUser();
    await panel.fillNewUser({
      username: username,
      password: "TestPassword123",
    })
    await panel.clickCreate();
    await panel.setRoles(username, [role]);
    await panel.gotoAudit();
    const auditRow = await panel.lastAuditRow;
    await expect(auditRow.getByRole("cell", { name: username, exact: true })).toBeVisible();
    await expect(auditRow.getByRole("cell", { name: "granted", exact: true })).toBeVisible();
    await expect(auditRow.getByRole("cell", { name: role, exact: true })).toBeVisible();

  });

});
