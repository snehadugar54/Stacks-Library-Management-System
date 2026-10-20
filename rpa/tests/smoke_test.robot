*** Settings ***
Documentation    Robot Framework environment smoke test

*** Test Cases ***
Robot Environment Is Working
    Log    Robot Framework is working
    Should Be Equal    ${1}    ${1}