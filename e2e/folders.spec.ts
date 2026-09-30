import { expect, test, uniqueName } from "./support/fixtures";

test.describe("Folders", () => {
  test("creating a nested folder and walking back through the breadcrumbs", async ({
    fileManager,
    workspace,
  }) => {
    const nested = uniqueName("nested");

    await test.step("create a folder inside the working one", async () => {
      await fileManager.createFolder(nested);
      await expect(fileManager.entryLink(nested)).toBeVisible();
    });

    await test.step("step into it", async () => {
      await fileManager.openFolder(nested);
      await expect(fileManager.page.getByText("Folder is empty")).toBeVisible();
    });

    await test.step("use a breadcrumb to return to the parent folder", async () => {
      await fileManager.page.getByRole("link", { name: workspace, exact: true }).click();
      await expect(fileManager.breadcrumbCurrent).toHaveText(workspace);
      await expect(fileManager.entryLink(nested)).toBeVisible();
    });

    await test.step("return to the root", async () => {
      await fileManager.goToRootCrumb();
      await expect(fileManager.entryLink(workspace)).toBeVisible();
    });
  });

  test("a folder with a taken name is not created twice", async ({
    fileManager,
    workspace,
  }) => {
    const name = uniqueName("duplicate");

    await fileManager.createFolder(name);
    await expect(fileManager.entryLink(name)).toBeVisible();

    await test.step("creating it again shows a clear error", async () => {
      await fileManager.createFolder(name);

      await expect(fileManager.status).toContainText("already exists");
      await expect(fileManager.entryLink(name)).toHaveCount(1);
    });

    await fileManager.goto(workspace);
  });

  test("deleting a folder requires confirmation", async ({ fileManager, workspace }) => {
    const name = uniqueName("to-be-deleted");
    await fileManager.createFolder(name);

    await test.step("cancelling leaves the folder in place", async () => {
      await fileManager.deleteEntry(name, false);
      await expect(fileManager.entryLink(name)).toBeVisible();
    });

    await test.step("confirming removes it", async () => {
      await fileManager.deleteEntry(name);
      await expect(fileManager.status).toContainText("Deleted");
      await expect(fileManager.entryLink(name)).toHaveCount(0);
    });

    await fileManager.goto(workspace);
  });

  test("deleting a folder takes its contents with it", async ({
    fileManager,
    workspace,
  }) => {
    const folder = uniqueName("with-contents");

    await fileManager.createFolder(folder);
    await fileManager.openFolder(folder);
    await fileManager.uploadFiles([
      {
        name: "inside.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("inside the folder"),
      },
    ]);
    await expect(fileManager.entryLink("inside.txt")).toBeVisible();

    await test.step("the confirmation page warns about the contents", async () => {
      await fileManager.goto(workspace);
      await fileManager.page.getByRole("link", { name: `Delete ${folder}` }).click();

      await expect(fileManager.page.getByTestId("recursive-warning")).toBeVisible();
    });

    await test.step("after confirming the folder is gone", async () => {
      await fileManager.page.getByRole("button", { name: "Delete" }).click();

      await expect(fileManager.entryLink(folder)).toHaveCount(0);
    });
  });

  test("renaming a folder", async ({ fileManager, workspace }) => {
    const before = uniqueName("before");
    const after = uniqueName("after");

    await fileManager.createFolder(before);
    await fileManager.renameEntry(before, after);

    await expect(fileManager.status).toContainText("Renamed");
    await expect(fileManager.entryLink(after)).toBeVisible();
    await expect(fileManager.entryLink(before)).toHaveCount(0);

    await fileManager.goto(workspace);
  });
});
