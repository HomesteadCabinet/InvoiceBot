from google_auth_oauthlib.flow import InstalledAppFlow
# This file is used to generate a token.json file for the gmail and sheets api credentials
# Should be run once to generate the token.json file

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets'
]

flow = InstalledAppFlow.from_client_secrets_file('client.json', SCOPES)

creds = flow.run_local_server(port=0, open_browser=False)

with open('token.json', 'w') as token:
    token.write(creds.to_json())
