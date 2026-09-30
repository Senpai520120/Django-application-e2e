import { expect, test, uniqueName, login, loginAs, logout } from "./support/fixtures";

test.describe("User Management", () => {

  test("create new user", async ({ panel, audit }) => {
    const username = uniqueName("e2e").replace(/-/g, "_");
    const password = "E2e-Strong-Pass-42";
    const email = `${username}@example.com`;
    // login as admin and create a new user
    await panel.goto();
    await panel.openCreateUser();
    await panel.fillNewUser({
      username: username,
      password: password,
      email: email
    });
    await panel.clickCreate();
    await expect(panel.status).toContainText("created");

    // logout and login as the new user to verify that the account works
    await logout(panel.page);
    await loginAs(panel.page, {username: username, password: password});

    // logout and login as admin again to clean up
    await logout(panel.page);
    await login(panel.page);
    await panel.goto();
    await panel.search(username);

    await audit.goto();

  });


});
