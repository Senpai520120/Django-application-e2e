import { test, expect } from '@playwright/test';

test.describe('Playwright demo', () => {

    test('Create new user and verify login', async ({ page }) => {
        // login as admin
        await page.goto('http://localhost:8000/login/');
        await page.getByRole('textbox', { name: 'Username' }).click();
        await page.getByRole('textbox', { name: 'Username' }).fill('demo_admin');
        await page.getByRole('textbox', { name: 'Password' }).click();
        await page.getByRole('textbox', { name: 'Password' }).fill('demo-password-123');
        await page.getByRole('button', { name: 'Sign in' }).click();
        // create new user
        const username = 'demo-user-test-' + Math.floor(Math.random() * 100000);

        await page.getByRole('link', { name: 'Users', exact: true }).click();
        await page.getByRole('link', { name: '+ New user' }).click();
        await page.getByRole('textbox', { name: 'Username:' }).click();
        await page.getByRole('textbox', { name: 'Username:' }).fill(username);
        await page.getByRole('textbox', { name: 'Email:' }).click();
        await page.getByRole('textbox', { name: 'Email:' }).fill(`${username}@sample.com`);
        await page.getByRole('textbox', { name: 'Password:' }).click();
        await page.getByRole('textbox', { name: 'Password:' }).fill('demo-password-123');
        await page.getByRole('textbox', { name: 'Password confirmation:' }).click();
        await page.getByRole('textbox', { name: 'Password confirmation:' }).fill('demo-password-123');
        await page.getByRole('button', { name: 'Create' }).click();
        // logout
        await page.getByRole('button', { name: 'Sign out' }).click();
        // login as new user
        await page.getByRole('textbox', { name: 'Username' }).click();
        await page.getByRole('textbox', { name: 'Username' }).fill(username);
        await page.getByRole('textbox', { name: 'Password' }).click();
        await page.getByRole('textbox', { name: 'Password' }).fill('demo-password-123');
        await page.getByRole('button', { name: 'Sign in' }).click();
        // verify that the new user is logged in
        await expect(page.getByRole('heading')).toContainText(`You are signed in as ${username}`);
        // logout
        await page.getByRole('button', { name: 'Sign out' }).click();
    });
});