import os
import urllib.parse
from flask import Flask, request, redirect, make_response

app = Flask(__name__)

COGNITO_CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
# e.g. "cognito-usekarma.auth.us-east-1.amazoncognito.com"
COGNITO_DOMAIN = os.environ["COGNITO_DOMAIN"]
# e.g. "https://grafana.usekarma.dev/"
LOGOUT_REDIRECT = os.environ.get("LOGOUT_REDIRECT", "https://localhost/")

@app.route("/healthz")
def healthz():
  return "ok", 200


@app.route("/logout")
def logout():
  """
  1. Clear ALB auth cookies in the browser.
  2. Redirect to Cognito Hosted UI /logout endpoint with client_id + logout_uri.
  """
  # Build Cognito logout URL
  logout_uri = LOGOUT_REDIRECT
  cognito_logout = (
    f"https://{COGNITO_DOMAIN}/logout"
    f"?client_id={urllib.parse.quote(COGNITO_CLIENT_ID)}"
    f"&logout_uri={urllib.parse.quote(logout_uri, safe='')}"
  )

  resp = make_response(redirect(cognito_logout))

  # Aggressively nuke possible ALB auth cookies.
  # AWS typically uses names like AWSELBAuthSessionCookie-0, etc.
  for cookie_name in request.cookies.keys():
    if cookie_name.startswith("AWSELBAuthSessionCookie"):
      resp.set_cookie(
        cookie_name,
        "",
        max_age=0,
        expires=0,
        path="/",
        secure=True,
        httponly=True,
      )

  # If you later add any app-specific session cookies, clear them here too.
  return resp


if __name__ == "__main__":
  # For local testing only; in ECS we’ll run via gunicorn
  app.run(host="0.0.0.0", port=8080)
