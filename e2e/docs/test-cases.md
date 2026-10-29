# Test cases

Generated from `tools/test_cases.json` by `python tools/create_test_case_issues.py --markdown`. Do not edit by hand.

## TC-01. Anonymous user is sent to the sign-in page

**Preconditions:** Not signed in

**Steps:**

1. Open the home page /

**Expected result:** The address becomes /login/?next=/ and the "Sign in" heading is shown.

**Automated test:** `tests/test_login.py::test_01_anonymous_user_is_sent_to_sign_in`

## TC-02. User signs in with valid credentials

**Preconditions:** Not signed in. Account demo_user / demo-password-123 exists

**Steps:**

1. Open /login/
2. Enter username demo_user and password demo-password-123
3. Click "Sign in"

**Expected result:** The home page opens with the heading "You are signed in as demo_user". The role "user" is listed.

**Automated test:** `tests/test_login.py::test_02_user_signs_in_with_valid_credentials`

## TC-03. Sign-in with a wrong password is rejected

**Preconditions:** Not signed in

**Steps:**

1. Open /login/
2. Enter username demo_user and password wrong-password
3. Click "Sign in"

**Expected result:** The user stays on /login/. The error "Please enter a correct username and password" is shown.

**Automated test:** `tests/test_login.py::test_03_wrong_password_is_rejected`

## TC-04. Unknown username gets the same error as a wrong password

**Preconditions:** Not signed in

**Steps:**

1. Sign in as demo_user with a wrong password and note the error text
2. Sign in as no_such_user_here with any password

**Expected result:** Both error texts are exactly the same, so the page does not reveal which usernames exist.

**Automated test:** `tests/test_login.py::test_04_unknown_username_gets_the_same_error`

## TC-05. Deactivated user cannot sign in

**Preconditions:** Not signed in. Account demo_inactive is switched off

**Steps:**

1. Open /login/
2. Enter username demo_inactive and password demo-password-123
3. Click "Sign in"

**Expected result:** The user stays on /login/ and the sign-in error is shown.

**Automated test:** `tests/test_login.py::test_05_deactivated_user_cannot_sign_in`

## TC-06. User signs out

**Preconditions:** Signed in as demo_user

**Steps:**

1. Click "Sign out" in the header
2. Open the home page /

**Expected result:** The home page is not shown: the address becomes /login/?next=/.

**Automated test:** `tests/test_login.py::test_06_user_signs_out`

## TC-07. Header link "Files" opens the file manager

**Preconditions:** Signed in as demo_user

**Steps:**

1. Open the home page /
2. Click "Files" in the header

**Expected result:** The address becomes /files/ and the "Files" heading is shown.

**Automated test:** `tests/test_login.py::test_07_header_link_opens_file_manager`

## TC-08. Regular user gets "access denied" on the admin panel

**Preconditions:** Signed in as demo_user (no admin role)

**Steps:**

1. Open /manage/

**Expected result:** The page "403 — access denied" is shown instead of the user list.

**Automated test:** `tests/test_access.py::test_08_regular_user_gets_403_on_admin_panel`

## TC-09. Admin opens the admin panel

**Preconditions:** Signed in as demo_admin

**Steps:**

1. Open /manage/

**Expected result:** The "Users" page opens with the user list; demo_admin is in it.

**Automated test:** `tests/test_access.py::test_09_admin_opens_admin_panel`

## TC-10. Regular user does not see admin links in the header

**Preconditions:** Signed in as demo_user

**Steps:**

1. Open the home page /
2. Look at the links in the header

**Expected result:** "Files" is shown. "Users", "Roles" and "Audit" are not shown.

**Automated test:** `tests/test_access.py::test_10_regular_user_does_not_see_admin_links`

## TC-11. Anonymous user cannot open the file manager

**Preconditions:** Not signed in

**Steps:**

1. Open /files/

**Expected result:** The address becomes /login/?next=/files/; no files are shown.

**Automated test:** `tests/test_access.py::test_11_anonymous_user_cannot_open_file_manager`

## TC-12. Admin finds a user by search

**Preconditions:** Signed in as demo_admin. Demo users demo_user01…demo_user10 exist

**Steps:**

1. Open /manage/
2. Type demo_user05 in the search field
3. Click "Search"

**Expected result:** demo_user05 is in the list. Other users, for example demo_user06, are not.

**Automated test:** `tests/test_users.py::test_12_admin_finds_user_by_search`

## TC-13. Admin creates a new user

**Preconditions:** Signed in as demo_admin

**Steps:**

1. Open /manage/users/new/
2. Enter a new unique username
3. Enter the password E2e-Strong-Pass-42 twice
4. Click "Create"

**Expected result:** The message "User <username> created." is shown. The user is found by search in the list.

**Automated test:** `tests/test_users.py::test_13_admin_creates_user`

## TC-14. New user can sign in

**Preconditions:** An admin has created a new user with a known password

**Steps:**

1. Open /login/
2. Enter the new user's username and password
3. Click "Sign in"

**Expected result:** The home page opens with "You are signed in as <username>".

**Automated test:** `tests/test_users.py::test_14_new_user_can_sign_in`

## TC-15. Password made only of digits is rejected

**Preconditions:** Signed in as demo_admin

**Steps:**

1. Open /manage/users/new/
2. Enter a new unique username and the password 52012000 twice
3. Click "Create"
4. Search for that username in /manage/

**Expected result:** The form shows "This password is entirely numeric." The search finds nothing: the user was not created.

**Automated test:** `tests/test_users.py::test_15_numeric_password_is_rejected`

## TC-16. Deactivated user cannot sign in any more

**Preconditions:** Signed in as demo_admin. A new active user exists

**Steps:**

1. Open /manage/ and find the user
2. Click "Deactivate" in the user's row
3. In another browser, try to sign in as that user

**Expected result:** The message "User <username> disabled." is shown and the button changes to "Activate". The sign-in fails with the sign-in error.

**Automated test:** `tests/test_users.py::test_16_deactivated_user_cannot_sign_in`

## TC-17. Admin grants the admin role

**Preconditions:** Signed in as demo_admin. A new user without roles exists

**Steps:**

1. Open /manage/ and click "Roles" in the user's row
2. Tick "admin"
3. Click "Save"

**Expected result:** The message "Roles of <username> updated" is shown. The user's row shows the "admin" role.

**Automated test:** `tests/test_roles.py::test_17_admin_grants_admin_role`

## TC-18. Admin revokes a role

**Preconditions:** Signed in as demo_admin. A new user with the "user" role exists

**Steps:**

1. Open the user's roles form
2. Untick "user"
3. Click "Save"

**Expected result:** The user's row no longer shows the "user" role.

**Automated test:** `tests/test_roles.py::test_18_admin_revokes_role`

## TC-19. Cancel on the roles form changes nothing

**Preconditions:** Signed in as demo_admin. A new user without roles exists

**Steps:**

1. Open the user's roles form
2. Tick "admin"
3. Click "Cancel" instead of "Save"

**Expected result:** The user still has no "admin" role.

**Automated test:** `tests/test_roles.py::test_19_cancel_on_roles_form_changes_nothing`

## TC-20. Admin cannot remove the admin role from themselves

**Preconditions:** Signed in as demo_admin

**Steps:**

1. Open the roles form of demo_admin
2. Untick "admin"
3. Click "Save"

**Expected result:** The error "You cannot take the admin role from yourself…" is shown. demo_admin keeps the "admin" role.

**Automated test:** `tests/test_roles.py::test_20_admin_cannot_remove_own_admin_role`

## TC-21. Role change is written to the audit log

**Preconditions:** Signed in as demo_admin. A new user without roles exists

**Steps:**

1. Grant the "user" role to the new user
2. Open /manage/audit/

**Expected result:** The newest record shows: who = demo_admin, action = granted, role = user, to whom = the new user.

**Automated test:** `tests/test_roles.py::test_21_role_change_is_written_to_audit_log`

## TC-22. Roles page counts a new member

**Preconditions:** Signed in as demo_admin. A new user without roles exists

**Steps:**

1. Open /manage/roles/ and note the number of users in "admin"
2. Grant the "admin" role to the new user
3. Open /manage/roles/ again

**Expected result:** The number of users in "admin" has grown by exactly 1.

**Automated test:** `tests/test_roles.py::test_22_roles_page_counts_new_member`

## TC-23. Create a nested folder and come back by breadcrumbs

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Create a folder
2. Open it
3. Click the working folder's name in the breadcrumbs
4. Click "Root" in the breadcrumbs

**Expected result:** 1: the folder is in the list. 2: it shows "Folder is empty." 3: the working folder is open and the new folder is in it. 4: the root is open and the working folder is in it.

**Automated test:** `tests/test_folders.py::test_23_create_nested_folder_and_go_back_by_breadcrumbs`

## TC-24. Folder with a taken name is not created twice

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Create a folder
2. Create a folder with the same name again

**Expected result:** A message with "already exists" is shown. There is only one folder with that name.

**Automated test:** `tests/test_folders.py::test_24_folder_with_taken_name_is_not_created_twice`

## TC-25. Cancelling folder deletion keeps the folder

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Create a folder
2. Click "Delete" next to it
3. On the confirmation page click "Cancel"

**Expected result:** The folder is still in the list.

**Automated test:** `tests/test_folders.py::test_25_cancelling_folder_deletion_keeps_folder`

## TC-26. Deleting a folder removes it with its contents

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Create a folder and upload a file into it
2. Go back to the working folder and click "Delete" next to the new folder
3. Click "Delete" on the confirmation page

**Expected result:** Step 2: a warning says the folder will be deleted with everything inside. Step 3: "Deleted: <name>." is shown and the folder is gone.

**Automated test:** `tests/test_folders.py::test_26_deleting_folder_removes_its_contents`

## TC-27. Rename a folder

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Create a folder
2. Click "Rename" next to it
3. Enter a new name and click "Save"

**Expected result:** "Renamed to <new name>." is shown. Only the new name is in the list.

**Automated test:** `tests/test_folders.py::test_27_rename_folder`

## TC-28. Upload a file with a Cyrillic name

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Choose a text file named like "отчёт.txt" in "Upload files"
2. Click "Upload"

**Expected result:** "Uploaded files: 1." is shown. The file is in the list with the correct name and type "file".

**Automated test:** `tests/test_files.py::test_28_upload_file_with_cyrillic_name`

## TC-29. Upload several files at once

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Choose two text files together in "Upload files"
2. Click "Upload"

**Expected result:** "Uploaded files: 2." is shown. Both files are in the list.

**Automated test:** `tests/test_files.py::test_29_upload_several_files_at_once`

## TC-30. Download returns the same file

**Preconditions:** Signed in. A file with known content is uploaded to the working folder

**Steps:**

1. Click the file name

**Expected result:** The browser downloads a file with the same name and the same content.

**Automated test:** `tests/test_files.py::test_30_download_returns_same_file`

## TC-31. Rename a file

**Preconditions:** Signed in. A file is uploaded to the working folder

**Steps:**

1. Click "Rename" next to the file
2. Enter a new name and click "Save"

**Expected result:** Only the new name is in the list.

**Automated test:** `tests/test_files.py::test_31_rename_file`

## TC-32. Delete a file after confirmation

**Preconditions:** Signed in. A file is uploaded to the working folder

**Steps:**

1. Click "Delete" next to the file
2. Click "Delete" on the confirmation page

**Expected result:** "Deleted: <name>." is shown and the file is gone from the list.

**Automated test:** `tests/test_files.py::test_32_delete_file_after_confirmation`

## TC-33. File one byte over the size limit is rejected

**Preconditions:** Signed in. An empty working folder is open in /files/. The size limit is known (5 MB in docker-compose)

**Steps:**

1. Choose a file 1 byte bigger than the limit
2. Click "Upload"

**Expected result:** A message with "is larger than the allowed" is shown. The file is not in the list.

**Automated test:** `tests/test_files.py::test_33_file_over_size_limit_is_rejected`

## TC-34. File with a taken name is not overwritten

**Preconditions:** Signed in. An empty working folder is open in /files/

**Steps:**

1. Upload same_name.txt with the text "first version"
2. Upload another same_name.txt with the text "second version"
3. Download same_name.txt

**Expected result:** Step 2 shows a message with "already exists". The downloaded file contains "first version".

**Automated test:** `tests/test_files.py::test_34_file_with_taken_name_is_not_overwritten`

## TC-35. Regular user cannot change roles by a direct request

**Preconditions:** Signed in as demo_user (no admin role). The roles form is hidden from this user

**Steps:**

1. Send the roles form of demo_user straight to the server (POST /manage/users/<id>/roles/) with the admin role ticked and a valid CSRF token

**Expected result:** The server answers 403 with the page "403 — access denied". demo_user still has no admin role.

**Automated test:** `tests/test_access.py::test_35_regular_user_cannot_change_roles_by_direct_request`

## TC-36. Regular user cannot switch a user off by a direct request

**Preconditions:** Signed in as demo_user. Another active user exists

**Steps:**

1. Send "Deactivate" for that user straight to the server (POST /manage/users/<id>/toggle-active/) with a valid CSRF token

**Expected result:** The server answers 403 with the page "403 — access denied". The user is still active.

**Automated test:** `tests/test_access.py::test_36_regular_user_cannot_deactivate_user_by_direct_request`

## TC-37. Admin cannot switch off their own account

**Preconditions:** Signed in as demo_admin

**Steps:**

1. Open /manage/ and find demo_admin
2. Click "Deactivate" in the demo_admin row

**Expected result:** The message "You cannot switch yourself off." is shown. demo_admin stays active.

**Automated test:** `tests/test_users.py::test_37_admin_cannot_deactivate_themselves`

## TC-38. Signed-in user loses access as soon as they are switched off

**Preconditions:** A user is signed in in one browser. An admin is signed in in another browser

**Steps:**

1. Admin: click "Deactivate" for that user
2. User: open the home page /

**Expected result:** The user is sent to /login/?next=/ without signing out by hand.

**Automated test:** `tests/test_users.py::test_38_deactivated_user_is_signed_out_at_once`

## TC-39. Revoking a role is written to the audit log

**Preconditions:** Signed in as demo_admin. A user with the "user" role exists

**Steps:**

1. Untick "user" in the user's roles form and save
2. Open /manage/audit/

**Expected result:** The newest record shows: who = demo_admin, action = revoked, role = user, to whom = the user.

**Automated test:** `tests/test_roles.py::test_39_role_revoke_is_written_to_audit_log`

## TC-41. File exactly at the size limit is accepted

**Preconditions:** Signed in. An empty working folder is open in /files/. The size limit is known (5 MB in docker-compose)

**Steps:**

1. Choose a file exactly as big as the limit
2. Click "Upload"

**Expected result:** "Uploaded files: 1." is shown and the file is in the list. Together with TC-33 this checks both sides of the limit.

**Automated test:** `tests/test_files.py::test_41_file_exactly_at_size_limit_is_accepted`

## TC-42. Path that climbs out of the storage is refused

**Preconditions:** Signed in as demo_user

**Steps:**

1. Open /files/?path=../..

**Expected result:** The server answers 400. No file list is shown.

**Automated test:** `tests/test_files.py::test_42_path_outside_storage_is_refused`

## TC-43. Sign-in does not send the user to another site

**Preconditions:** Not signed in

**Steps:**

1. Open /login/?next=https://evil.example/
2. Sign in as demo_user

**Expected result:** The home page of the app opens. The address is not evil.example.

**Automated test:** `tests/test_login.py::test_43_sign_in_does_not_send_user_to_another_site`

## TC-44. Anonymous user is sent to Keycloak and comes back

**Preconditions:** SSO stack (docker-compose.sso.yml). Not signed in

**Steps:**

1. Open /files/
2. Sign in to Keycloak as demo_admin

**Expected result:** The Keycloak sign-in form opens first. After it the app opens /files/.

**Automated test:** `tests/test_sso.py::test_44_anonymous_user_is_sent_to_keycloak_and_back`

## TC-45. Keycloak session signs in to the app (SSO)

**Preconditions:** SSO stack (docker-compose.sso.yml). Not signed in

**Steps:**

1. Open the Keycloak account page /realms/myapp/account
2. Sign in as demo_user
3. Open the app's home page /

**Expected result:** The home page shows "You are signed in as demo_user" without a second sign-in form.

**Automated test:** `tests/test_sso.py::test_45_keycloak_session_signs_in_to_the_app`

## TC-46. Signing out of the app ends the Keycloak session

**Preconditions:** SSO stack (docker-compose.sso.yml). Signed in as demo_user

**Steps:**

1. Click "Sign out"
2. Open the Keycloak account page
3. Open the app's home page /

**Expected result:** Both the Keycloak account page and the app ask to sign in again.

**Automated test:** `tests/test_sso.py::test_46_sign_out_ends_the_keycloak_session`

## TC-47. Keycloak rejects a wrong password

**Preconditions:** SSO stack (docker-compose.sso.yml). Not signed in

**Steps:**

1. Open /
2. Enter demo_user and wrong-password in the Keycloak form

**Expected result:** Keycloak shows "Invalid username or password." The app does not open.

**Automated test:** `tests/test_sso.py::test_47_wrong_password_is_rejected_by_keycloak`

## TC-48. Account switched off in Keycloak cannot sign in

**Preconditions:** SSO stack (docker-compose.sso.yml). kc_disabled is disabled in Keycloak

**Steps:**

1. Open /
2. Sign in to Keycloak as kc_disabled

**Expected result:** Keycloak says the account is disabled. The app does not open.

**Automated test:** `tests/test_sso.py::test_48_account_disabled_in_keycloak_cannot_sign_in`

## TC-49. User switched off in the panel cannot sign in through Keycloak

**Preconditions:** SSO stack (docker-compose.sso.yml). demo_inactive is enabled in Keycloak and switched off in the app

**Steps:**

1. Open /
2. Sign in to Keycloak as demo_inactive
3. Open / again

**Expected result:** Both times the app shows "Sign-in failed" at /login/failed/, with no redirect loop.

**Automated test:** `tests/test_sso.py::test_49_user_switched_off_in_the_panel_cannot_sign_in`

## TC-50. New Keycloak user gets the "user" role

**Preconditions:** SSO stack (docker-compose.sso.yml). kc_newcomer exists only in Keycloak

**Steps:**

1. Sign in as kc_newcomer
2. Open /manage/

**Expected result:** The home page lists the role "user". /manage/ answers 403.

**Automated test:** `tests/test_sso.py::test_50_new_keycloak_user_gets_the_user_role`

## TC-51. Role given in the panel survives the next sign-in

**Preconditions:** SSO stack (docker-compose.sso.yml). kc_promoted has signed in once

**Steps:**

1. As admin, give kc_promoted the admin role in the panel
2. kc_promoted signs out and signs in through Keycloak again
3. Open /manage/

**Expected result:** The home page lists the role "admin". /manage/ opens.

**Automated test:** `tests/test_sso.py::test_51_role_given_in_the_panel_survives_the_next_sign_in`

## TC-52. AD person signs in with the AD password

**Preconditions:** AD stack (docker-compose.ad.yml). The test adds a person to AD

**Steps:**

1. Add a person to AD
2. Sign in as them with the AD password
3. Open /manage/

**Expected result:** The app shows their username and the role "user". /manage/ answers 403.

**Automated test:** `tests/test_ad.py::test_52_ad_person_signs_in_with_the_ad_password`

## TC-53. AD email works as the username

**Preconditions:** AD stack (docker-compose.ad.yml). The test adds a person to AD

**Steps:**

1. Add a person with an email to AD
2. On the Keycloak form type the email instead of the username

**Expected result:** The app shows the person's AD username.

**Automated test:** `tests/test_ad.py::test_53_ad_person_signs_in_with_the_email`

## TC-54. Account switched off in AD cannot sign in

**Preconditions:** AD stack (docker-compose.ad.yml). The test adds a person to AD

**Steps:**

1. Add a person to AD and disable the account there
2. Sign in as them with the right password

**Expected result:** Keycloak shows an error and the app stays closed.

**Automated test:** `tests/test_ad.py::test_54_account_switched_off_in_ad_cannot_sign_in`

## TC-55. Password set in AD works at once

**Preconditions:** AD stack (docker-compose.ad.yml). The test adds a person to AD

**Steps:**

1. Add a person to AD
2. Reset their password in AD
3. Sign in with the old password
4. Sign in with the new password

**Expected result:** The old password is refused; the new one lets the person in.

**Automated test:** `tests/test_ad.py::test_55_password_set_in_ad_works_at_once`

## TC-56. User made in the panel is found by the AD email

**Preconditions:** AD stack (docker-compose.ad.yml). The test adds a person to AD with an email

**Steps:**

1. As admin, create a user in the panel with another username and the same email
2. Sign in as the AD person

**Expected result:** The panel says the person is in Active Directory. The AD sign-in lands in the user made in the panel.

**Automated test:** `tests/test_ad.py::test_56_user_made_in_the_panel_is_found_by_the_ad_email`

## TC-57. Another user signs in after sign-out

**Preconditions:** SSO stack (docker-compose.sso.yml)

**Steps:**

1. Sign in through Keycloak as demo_user
2. Sign out
3. Sign in through Keycloak as demo_admin

**Expected result:** The app shows demo_admin with the role "admin", not demo_user.

**Automated test:** `tests/test_sso.py::test_57_another_user_signs_in_after_sign_out`

## TC-58. Account unknown to Keycloak cannot sign in

**Preconditions:** SSO stack (docker-compose.sso.yml)

**Steps:**

1. Open /
2. In the Keycloak form enter a username Keycloak does not have
3. As admin, search for that username in the panel

**Expected result:** Keycloak shows "Invalid username or password." and stays on its form. The panel finds nothing.

**Automated test:** `tests/test_sso.py::test_58_account_unknown_to_keycloak_cannot_sign_in`

## TC-59. Cookies of another app on localhost do not break sign-out

**Preconditions:** SSO stack (docker-compose.sso.yml). The app is opened at localhost:8000; the browser has another app's csrftoken and sessionid for localhost

**Steps:**

1. Sign in through Keycloak as demo_user
2. The other app writes new csrftoken and sessionid
3. Press Sign out

**Expected result:** No CSRF 403: the Keycloak form is shown. The other app's cookies keep their values.

**Automated test:** `tests/test_sso.py::test_59_cookies_of_another_app_on_localhost_do_not_break_sign_out`

## TC-60. App sign-in opens the Keycloak account console

**Preconditions:** SSO stack (docker-compose.sso.yml). Not signed in

**Steps:**

1. Sign in to the app through Keycloak as demo_user
2. Open the Keycloak account console http://localhost:8080/realms/myapp/account

**Expected result:** The console opens at once with "Personal info", without the sign-in form.

**Automated test:** `tests/test_sso.py::test_60_app_sign_in_opens_the_keycloak_account_console`
