import { expect, test, uniqueName } from "./support/fixtures";

/** The app limit. In CI it is set to the same value as in docker-compose. */
const maxFileSize = Number(process.env.E2E_MAX_FILE_SIZE ?? 5 * 1024 * 1024);

function textFile(name: string, content: string) {
  return { name, mimeType: "text/plain", buffer: Buffer.from(content, "utf-8") };
}

test.describe("Files", () => {
  test("uploading a file makes it show up in the listing", async ({
    fileManager,
    workspace,
  }) => {
    // A deliberately non-ASCII name: uploads must survive one end to end.
    const name = `${uniqueName("отчёт")}.txt`;

    await fileManager.uploadFiles([textFile(name, "report contents")]);

    await expect(fileManager.status).toContainText("Uploaded files: 1");
    await expect(fileManager.entryLink(name)).toBeVisible();
    await expect(fileManager.row(name)).toContainText("file");

    await fileManager.goto(workspace);
  });

  test("uploading several files at once", async ({ fileManager, workspace }) => {
    const first = `${uniqueName("first")}.txt`;
    const second = `${uniqueName("second")}.txt`;

    await fileManager.uploadFiles([
      textFile(first, "one"),
      textFile(second, "two"),
    ]);

    await expect(fileManager.status).toContainText("Uploaded files: 2");
    await expect(fileManager.entryLink(first)).toBeVisible();
    await expect(fileManager.entryLink(second)).toBeVisible();

    await fileManager.goto(workspace);
  });

  test("renaming a file", async ({ fileManager, workspace }) => {
    const before = `${uniqueName("before")}.txt`;
    const after = `${uniqueName("after")}.txt`;

    await fileManager.uploadFiles([textFile(before, "payload")]);
    await fileManager.renameEntry(before, after);

    await expect(fileManager.entryLink(after)).toBeVisible();
    await expect(fileManager.entryLink(before)).toHaveCount(0);

    await fileManager.goto(workspace);
  });

  test("downloading a file", async ({ fileManager, workspace }) => {
    const name = `${uniqueName("download")}.txt`;
    await fileManager.uploadFiles([textFile(name, "useful payload")]);

    const download = await test.step("click the file name", async () => {
      const waiter = fileManager.page.waitForEvent("download");
      await fileManager.entryLink(name).click();
      return waiter;
    });

    expect(download.suggestedFilename()).toBe(name);

    await fileManager.goto(workspace);
  });

  test("deleting a file asks for confirmation", async ({ fileManager, workspace }) => {
    const name = `${uniqueName("delete")}.txt`;
    await fileManager.uploadFiles([textFile(name, "payload")]);

    await test.step("cancel first", async () => {
      await fileManager.deleteEntry(name, false);
      await expect(fileManager.entryLink(name)).toBeVisible();
    });

    await test.step("then confirm", async () => {
      await fileManager.deleteEntry(name);
      await expect(fileManager.entryLink(name)).toHaveCount(0);
    });

    await fileManager.goto(workspace);
  });

  test("a file over the limit is refused with a clear error", async ({
    fileManager,
    workspace,
  }) => {
    const name = `${uniqueName("oversized")}.bin`;
    const oversized = Buffer.alloc(maxFileSize + 1024, 1);

    await fileManager.uploadFiles([
      { name, mimeType: "application/octet-stream", buffer: oversized },
    ]);

    await expect(fileManager.status).toContainText("larger than the allowed");
    await expect(fileManager.entryLink(name)).toHaveCount(0);

    await fileManager.goto(workspace);
  });

  test("a file with a taken name does not overwrite the existing one", async ({
    fileManager,
    workspace,
  }) => {
    const name = `${uniqueName("duplicate")}.txt`;

    await fileManager.uploadFiles([textFile(name, "first version")]);
    await fileManager.uploadFiles([textFile(name, "second version")]);

    await expect(fileManager.status).toContainText("already exists");
    await expect(fileManager.entryLink(name)).toHaveCount(1);

    await fileManager.goto(workspace);
  });
});
