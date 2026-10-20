*** Settings ***
Documentation    Verify authenticated Robot Framework access to the local Flask API.
Library    Collections
Library    RequestsLibrary

*** Variables ***
${BASE_URL}    http://127.0.0.1:5000
${ADMIN_EMAIL}    %{LIBRARY_ADMIN_EMAIL}
${ADMIN_PASSWORD}    %{LIBRARY_ADMIN_PASSWORD}

*** Test Cases ***
Admin Can Access Authenticated API
    Create Session    library    ${BASE_URL}
    ${credentials}=    Create Dictionary    email=${ADMIN_EMAIL}    password=${ADMIN_PASSWORD}
    ${login_response}=    POST On Session    library    /login    data=${credentials}    allow_redirects=${False}
    Should Be Equal As Integers    ${login_response.status_code}    302
    Log    Login succeeded.
    ${api_response}=    GET On Session    library    /api/automation/logs
    Should Be Equal As Integers    ${api_response.status_code}    200
    Log    Authenticated API access succeeded.
