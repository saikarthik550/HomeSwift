from flask import Flask, jsonify, request, render_template
import requests
import logging

app = Flask(__name__)

# Environment variables for sensitive information
WELL_KNOWN_ENDPOINT = "https://api.sandbox.natwest.com/.well-known/openid-configuration"
CLIENT_ID = '4gxPBr17K2fMRhwHjyf9XqHcvvKvduG2encPVV6Q0E0='
CLIENT_SECRET = 'DbVckKuXVrK7hShvvC8644bLedsKaY1Xvw0m4K3aoxA='
REDIRECT_URL = "https://70947a22-95b0-44b9-9e6f-670c8893baed.example.org/redirect"
API_URL_PREFIX = "https://ob.sandbox.natwest.com"
PSU_USERNAME = "123456789012@70947a22-95b0-44b9-9e6f-670c8893baed.example.org"

logging.basicConfig(level=logging.DEBUG)

def get_token_endpoint():
    try:
        response = requests.get(WELL_KNOWN_ENDPOINT)
        response.raise_for_status()
        data = response.json()
        return data.get("token_endpoint"), data.get("authorization_endpoint")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error retrieving well known endpoint: {e}")
        return None, None

def get_access_token(token_endpoint):
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "accounts"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        response = requests.post(token_endpoint, data=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error retrieving access token: {e}")
        return None

def get_consent_id(api_url_prefix, access_token):
    url = f"{api_url_prefix}/open-banking/v3.1/aisp/account-access-consents"
    payload = {
        "Data": {

            "Permissions": [
                "ReadAccountsDetail",
                "ReadBalances",
                "ReadTransactionsCredits",
                "ReadTransactionsDebits",
                "ReadTransactionsDetail",
                "ReadCreditScore",
                "ReadAccountsBasic",
                "ReadTransactionsDetailed"

            ]
        },
        "Risk": {}
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["Data"]["ConsentId"]
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error posting account request: {e}")
        app.logger.error(f"Response content: {e.response.content}")
        return None

def approve_consent_programmatically(authorization_endpoint, consent_id):
    url = (f"{authorization_endpoint}?client_id={CLIENT_ID}&response_type=code id_token"
           f"&scope=openid accounts&redirect_uri={REDIRECT_URL}&request={consent_id}"
           f"&authorization_mode=AUTO_POSTMAN&authorization_result=APPROVED"
           f"&authorization_username={PSU_USERNAME}&authorization_accounts=*")
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("redirectUri")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error approving consent: {e}")
        return None

def exchange_code_for_token(token_endpoint, authorization_code):
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URL,
        "grant_type": "authorization_code",
        "code": authorization_code
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        response = requests.post(token_endpoint, data=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error exchanging code for access token: {e}")
        return None

def get_customer_details(api_url_prefix, access_token, customer_id, id_scheme):
    url = f"{api_url_prefix}/zerocode/globalopenfinancechallenge.com/customer/v2/customers/{customer_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    params = {
        "idScheme": id_scheme
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error retrieving customer details: {e}")
        return None

def political_exposure_screening(api_url_prefix, access_token, first_name, surname, country_code):
    url = f"{api_url_prefix}/zerocode/globalopenfinancechallenge.com/screening/1.0.0/politically-exposed-persons/status"
    payload = {
        "countryOfResidenceCode": country_code,
        "name": {
            "firstName": first_name,
            "surname": surname
        }
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error performing political exposure screening: {e}")
        return None


def get_transaction_details(api_url_prefix, access_token, account_id):
    url = f"{api_url_prefix}/open-banking/v3.1/aisp/accounts/{account_id}/transactions"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # Log the request details
    app.logger.debug(f"Request URL: {url}")
    app.logger.debug(f"Request Headers: {headers}")

    try:
        response = requests.get(url, headers=headers)

        # Log the response details
        app.logger.debug(f"Response Status Code: {response.status_code}")
        app.logger.debug(f"Response Headers: {response.headers}")
        app.logger.debug(f"Response Body: {response.text}")

        response.raise_for_status()
        data = response.json()
        return data.get('Data', {}).get('Transaction', [])
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error retrieving transaction details: {e}")
        if e.response is not None:
            app.logger.error(f"Response Content: {e.response.content}")
        return []


@app.route('/')
def index():
    token_endpoint, authorization_endpoint = get_token_endpoint()
    if not token_endpoint or not authorization_endpoint:
        return jsonify({"error": "Failed to retrieve endpoints"}), 500

    access_token = get_access_token(token_endpoint)
    if not access_token:
        return jsonify({"error": "Failed to retrieve access token"}), 500

    consent_id = get_consent_id(API_URL_PREFIX, access_token)
    if not consent_id:
        return jsonify({"error": "Failed to retrieve consent ID"}), 500

    redirect_uri = approve_consent_programmatically(authorization_endpoint, consent_id)
    if not redirect_uri:
        return jsonify({"error": "Failed to approve consent"}), 500

    # Extract authorization code from redirect_uri
    authorization_code = None
    try:
        fragment = redirect_uri.split('#')[1]
        params = fragment.split('&')
        for param in params:
            key, value = param.split('=')
            if key == 'code':
                authorization_code = value
                break
    except Exception as e:
        app.logger.error(f"Error extracting authorization code: {e}")
        return jsonify({"error": "Failed to extract authorization code"}), 500

    if not authorization_code:
        return jsonify({"error": "Authorization code not found"}), 500

    api_access_token = exchange_code_for_token(token_endpoint, authorization_code)
    if not api_access_token:
        return jsonify({"error": "Failed to exchange code for access token"}), 500

    # Fetch credit score
    credit_score_url = f"{API_URL_PREFIX}/open-banking/v3.1/aisp/accounts/credit-score"
    credit_score_headers = {
        "Authorization": f"Bearer {api_access_token}"
    }
    try:
        credit_score_response = requests.get(credit_score_url, headers=credit_score_headers)
        credit_score_response.raise_for_status()
        credit_score_data = credit_score_response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error retrieving credit score: {e}")
        credit_score_data = {"error": str(e)}

    # Fetch customer details
    customer_id = '1122334455'  # Example customer ID
    id_scheme = 'customerIdentificationNumber'  # Example ID scheme
    customer_details = get_customer_details(API_URL_PREFIX, api_access_token, customer_id, id_scheme)
    if not customer_details:
        customer_details = {"error": "Failed to retrieve customer details"}
    else:
        customer_details = {
            "name": customer_details["data"]["name"]["fullLegalName"],
            "address": customer_details["data"]["address"]["line1"],
            "email": customer_details["data"]["contactDetails"]["emailAddress"],
            "phone": customer_details["data"]["contactDetails"]["mobilePhoneNumber"],
            "home_ownership": customer_details["data"]["insightDetails"]["homeOwnership"]
        }

    # Perform political exposure screening
    first_name = 'MIKHAIL'  # Example first name
    surname = 'KARPUSHIN'  # Example surname
    country_code = 'GB'  # Example country code
    political_exposure = political_exposure_screening(API_URL_PREFIX, api_access_token, first_name, surname, country_code)
    if not political_exposure:
        political_exposure = {"error": "Failed to perform political exposure screening"}
    else:
        political_status = "Failure" if political_exposure["hitsCount"] > 0 else "Successful"

    # Fetch transaction details
    account_id = '40debdad-1572-4ad9-bcdb-95d40b738e76'  # Example account ID
    transaction_details = get_transaction_details(API_URL_PREFIX, api_access_token, account_id)
    if not transaction_details:
        transaction_details = {"error": "Failed to retrieve transaction details"}

    return render_template('index.html',
                           credit_score=credit_score_data,
                           customer_details=customer_details,
                           political_status=political_status,
                           transaction_details=transaction_details)

if __name__ == '__main__':
    app.run(debug=True)
