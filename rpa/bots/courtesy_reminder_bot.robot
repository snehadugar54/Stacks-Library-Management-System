*** Settings ***
Documentation    Run and verify the courtesy reminder automation through the Flask API.
Library    Collections
Library    RequestsLibrary

*** Variables ***
${BASE_URL}    http://127.0.0.1:5000
${ADMIN_EMAIL}    %{LIBRARY_ADMIN_EMAIL}
${ADMIN_PASSWORD}    %{LIBRARY_ADMIN_PASSWORD}

*** Test Cases ***
Run Courtesy Reminder Automation
    Create Session    library    ${BASE_URL}
    Login As Admin
    ${automation_response}=    POST On Session    library    /api/automation/courtesy
    Should Be Equal As Integers    ${automation_response.status_code}    200
    ${automation_data}=    Evaluate    $automation_response.json()
    ${processed}=    Get From Dictionary    ${automation_data}    processed
    ${results}=    Get From Dictionary    ${automation_data}    results
    Log    Courtesy automation summary: ${automation_data}[message]
    ${successful}=    Set Variable    ${0}
    ${failed}=    Set Variable    ${0}
    IF    ${processed} == 0
        Log    No upcoming loans due today or tomorrow.
    ELSE
        FOR    ${record}    IN    @{results}
            ${member_name}=    Get From Dictionary    ${record}    member_name
            ${member_email}=    Get From Dictionary    ${record}    member_email
            ${book_title}=    Get From Dictionary    ${record}    book_title
            ${due_on}=    Get From Dictionary    ${record}    due_on
            ${status}=    Get From Dictionary    ${record}    status
            ${email_status}=    Get From Dictionary    ${record}    email_status
            Log    Processed courtesy record: member=${member_name}; email=${member_email}; book=${book_title}; due_date=${due_on}; status=${status}; email_status=${email_status}
            Should Be Equal    ${status}    SUCCESS
            ${successful}=    Evaluate    ${successful} + 1
        END
    END
    ${logs_response}=    GET On Session    library    /api/automation/logs
    Should Be Equal As Integers    ${logs_response.status_code}    200
    ${automation_logs}=    Evaluate    $logs_response.json()
    Verify Processed Courtesy Records Are Logged    ${results}    ${automation_logs}
    Log    COURTESY REMINDER AUTOMATION COMPLETE\nRecords processed: ${processed}\nSuccessful: ${successful}\nFailed: ${failed}

*** Keywords ***
Login As Admin
    ${credentials}=    Create Dictionary    email=${ADMIN_EMAIL}    password=${ADMIN_PASSWORD}
    ${login_response}=    POST On Session    library    /login    data=${credentials}    allow_redirects=${False}
    Should Be Equal As Integers    ${login_response.status_code}    302
    Log    Login succeeded.

Verify Processed Courtesy Records Are Logged
    [Arguments]    ${results}    ${automation_logs}
    FOR    ${record}    IN    @{results}
        ${loan_id}=    Get From Dictionary    ${record}    loan_id
        ${expected_status}=    Get From Dictionary    ${record}    status
        ${matching_log_found}=    Set Variable    ${False}
        FOR    ${log_record}    IN    @{automation_logs}
            ${logged_loan_id}=    Get From Dictionary    ${log_record}    loan_id
            IF    ${logged_loan_id} == ${loan_id}
                ${matching_log_found}=    Set Variable    ${True}
                ${logged_status}=    Get From Dictionary    ${log_record}    status
                Should Be Equal    ${logged_status}    ${expected_status}
                BREAK
            END
        END
        Should Be True    ${matching_log_found}    msg=No automation log was found for processed courtesy loan ${loan_id}.
    END
